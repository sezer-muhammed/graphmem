"""GraphMem core operations — shared by the MCP server, CLI, and web API.

All functions take/return plain Python data. Embeddings are generated inside
the database (ONNX model, see EMBED_MODEL) — no external API, no local model.
"""
import decimal
import json

import oracledb

from .db import connect

EMBED_MODEL = "ALL_MINILM_L12_V2"
DEDUP_DISTANCE = 0.30   # cosine distance below this = probable duplicate
BRIEF_COLS = "name, domain, kind, title, summary, status"

_conn = None


class DBUnavailable(RuntimeError):
    """Raised when the Oracle ADB can't be reached (e.g. Always-Free idle-stop)."""


def db():
    global _conn
    if _conn is not None:
        try:
            _conn.ping()
            return _conn
        except Exception:
            _conn = None
    try:
        _conn = connect()
    except Exception as exc:
        raise DBUnavailable(
            "cannot reach the memory database. If this is the Always-Free ADB it "
            "may be waking from idle — retry shortly, or run "
            "`python -m graphmem.keepalive`. Original error: " + str(exc)) from exc
    return _conn


def embed_expr(bind_name: str) -> str:
    return f"VECTOR_EMBEDDING({EMBED_MODEL} USING :{bind_name} AS DATA)"


def embed_text(title, summary, tags):
    parts = [title or ""]
    if summary:
        parts.append(summary)
    if tags:
        parts.append("tags: " + ", ".join(tags))
    return " — ".join(parts)


def lob(v):
    return v.read() if isinstance(v, oracledb.LOB) else v


def jval(v):
    if v and isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def plain(v):
    """Recursively convert DB-native types (Decimal, nested JSON) to plain JSON-safe."""
    if isinstance(v, decimal.Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v


def node_row(r, cols):
    d = dict(zip(cols, (lob(v) for v in r)))
    for k in ("ATTRS", "TAGS", "ALIASES"):
        if k in d:
            d[k] = jval(d[k])
    return {k.lower(): plain(v) for k, v in d.items()}


def redact_secret(node):
    """Mask the body + attrs of a secret-sensitivity node for any public/UI
    surface. Title, summary, kind, and edges stay visible — only the sensitive
    values are hidden. Idempotent; returns the same dict for chaining."""
    if isinstance(node, dict) and node.get("sensitivity") == "secret":
        if node.get("body"):
            node["body"] = "[redacted — secret node]"
        if node.get("attrs"):
            node["attrs"] = {"_redacted": True}
    return node


def vocab_values(cur, category):
    cur.execute("SELECT value FROM vocabulary WHERE category = :c", c=category)
    return {r[0] for r in cur.fetchall()}


def check_vocab(cur, category, value):
    vals = vocab_values(cur, category)
    if value in vals:
        return True, value
    lower_map = {v.lower(): v for v in vals}
    if value.lower() in lower_map:
        return True, lower_map[value.lower()]
    return False, None


def edges_of(cur, node_id):
    cur.execute("""
        SELECT n1.name, e.rel, n2.name, e.weight, e.note
        FROM edge e JOIN node n1 ON n1.id = e.src JOIN node n2 ON n2.id = e.dst
        WHERE e.src = :i OR e.dst = :i""", i=node_id)
    return [{"src": a, "rel": rel, "dst": b, "weight": float(w), "note": note}
            for a, rel, b, w, note in cur.fetchall()]


def remember(name, domain, kind, title, summary, body="", tags=None, attrs=None,
             aliases=None, sensitivity="private", source="conversation",
             confidence=0.8, force=False):
    conn = db()
    cur = conn.cursor()

    ok, canon = check_vocab(cur, "domain", domain)
    if not ok:
        return {"error": f"unknown domain '{domain}'",
                "known": sorted(vocab_values(cur, "domain")),
                "hint": "add it via vocab add if genuinely new"}
    domain = canon
    ok, canon = check_vocab(cur, "kind", kind)
    if not ok:
        return {"error": f"unknown kind '{kind}'",
                "known": sorted(vocab_values(cur, "kind"))}
    kind = canon

    etext = embed_text(title, summary, tags)
    cur.execute(f"""
        SELECT name, title, ROUND(VECTOR_DISTANCE(embedding, {embed_expr('q')}, COSINE), 4) d
        FROM node WHERE status != 'archived'
        ORDER BY d FETCH FIRST 5 ROWS ONLY""", q=etext)
    near = [{"name": n, "title": t, "distance": float(d)} for n, t, d in cur.fetchall()]
    dupes = [x for x in near if x["distance"] < DEDUP_DISTANCE]
    if dupes and not force:
        return {"not_saved": "very similar node(s) exist — update/link instead, "
                             "or retry with force=true",
                "duplicates": dupes}

    try:
        cur.execute(f"""
            INSERT INTO node (name, domain, kind, title, summary, body, attrs, tags,
                              aliases, sensitivity, source, confidence, last_verified, embedding)
            VALUES (:name, :domain, :kind, :title, :summary, :body, :attrs, :tags,
                    :aliases, :sens, :source, :conf, SYSTIMESTAMP, {embed_expr('etext')})""",
            name=name, domain=domain, kind=kind, title=title, summary=summary,
            body=body or None, attrs=json.dumps(attrs) if attrs else None,
            tags=json.dumps(tags) if tags else None,
            aliases=json.dumps(aliases) if aliases else None,
            sens=sensitivity, source=source, conf=confidence, etext=etext)
    except oracledb.IntegrityError:
        return {"error": f"a node named '{name}' already exists — use update to "
                         "modify it, or choose a different name"}
    conn.commit()
    suggestions = [x for x in near if DEDUP_DISTANCE <= x["distance"] < 0.75]
    return {"saved": name, "link_suggestions": suggestions,
            "hint": "use link to connect related nodes" if suggestions else None}


def recall(query, k=5, domain="", include_neighbors=True):
    conn = db()
    cur = conn.cursor()
    where = "WHERE status != 'archived'"
    binds = {"q": query}
    if domain:
        where += " AND domain = :d"
        binds["d"] = domain
    cur.execute(f"""
        SELECT id, {BRIEF_COLS},
               ROUND(VECTOR_DISTANCE(embedding, {embed_expr('q')}, COSINE), 4) dist
        FROM node {where} ORDER BY dist FETCH FIRST {int(k)} ROWS ONLY""", **binds)
    cols = [c.strip().upper() for c in BRIEF_COLS.split(",")]
    hits = []
    for r in cur.fetchall():
        h = node_row(r[1:-1], cols)
        h["distance"] = float(r[-1])
        if include_neighbors:
            h["edges"] = edges_of(cur, r[0])
        hits.append(h)
    return {"query": query, "hits": hits}


def search(text="", domain="", kind="", status="", limit=20):
    conn = db()
    cur = conn.cursor()
    where, binds = ["1=1"], {}
    if text:
        where.append("""(UPPER(name) LIKE :t OR UPPER(title) LIKE :t
                         OR UPPER(summary) LIKE :t OR UPPER(aliases) LIKE :t)""")
        binds["t"] = f"%{text.upper()}%"
    for col, val in (("domain", domain), ("kind", kind), ("status", status)):
        if val:
            where.append(f"{col} = :{col}")
            binds[col] = val
    cur.execute(f"""SELECT {BRIEF_COLS} FROM node WHERE {' AND '.join(where)}
                    ORDER BY updated_at DESC FETCH FIRST {int(limit)} ROWS ONLY""", **binds)
    cols = [c.strip().upper() for c in BRIEF_COLS.split(",")]
    return {"results": [node_row(r, cols) for r in cur.fetchall()]}


def get(name):
    conn = db()
    cur = conn.cursor()
    cur.execute("""SELECT id, name, domain, kind, title, summary, body, attrs, tags,
                          aliases, status, sensitivity, source, confidence,
                          TO_CHAR(last_verified,'YYYY-MM-DD') last_verified,
                          TO_CHAR(created_at,'YYYY-MM-DD') created_at,
                          TO_CHAR(updated_at,'YYYY-MM-DD') updated_at
                   FROM node WHERE name = :n""", n=name)
    r = cur.fetchone()
    if not r:
        return {"error": f"no node named '{name}'"}
    cols = ["ID", "NAME", "DOMAIN", "KIND", "TITLE", "SUMMARY", "BODY", "ATTRS",
            "TAGS", "ALIASES", "STATUS", "SENSITIVITY", "SOURCE", "CONFIDENCE",
            "LAST_VERIFIED", "CREATED_AT", "UPDATED_AT"]
    node = node_row(r, cols)
    node_id = node.pop("id")
    node["edges"] = edges_of(cur, node_id)
    return node


def link(src, dst, rel, weight=0.5, note=""):
    conn = db()
    cur = conn.cursor()
    ok, canon = check_vocab(cur, "rel", rel)
    if not ok:
        return {"error": f"unknown rel '{rel}'",
                "known": sorted(vocab_values(cur, "rel"))}
    try:
        cur.execute("""INSERT INTO edge (src, dst, rel, weight, note)
                       SELECT a.id, b.id, :rel, :w, :note FROM node a, node b
                       WHERE a.name = :src AND b.name = :dst""",
                    rel=canon, w=weight, note=note or None, src=src, dst=dst)
    except oracledb.IntegrityError:
        return {"error": "edge already exists (same src/dst/rel)"}
    if cur.rowcount == 0:
        return {"error": "src or dst node not found"}
    conn.commit()
    return {"linked": f"{src} -[{canon} w={weight}]-> {dst}"}


def walk(start, depth=2, min_weight=0.0, rel=""):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM node WHERE name = :n", n=start)
    r = cur.fetchone()
    if not r:
        return {"error": f"no node named '{start}'"}
    frontier, seen = {r[0]: None}, {r[0]}
    layers = []
    for hop in range(1, max(1, min(int(depth), 4)) + 1):
        if not frontier:
            break
        ids = list(frontier)
        binds = {f"i{j}": v for j, v in enumerate(ids)}
        ph = ",".join(f":i{j}" for j in range(len(ids)))
        relf = "AND e.rel = :rel" if rel else ""
        if rel:
            binds["rel"] = rel
        binds["w"] = min_weight
        cur.execute(f"""
            SELECT DISTINCT n2.name, n2.title, n2.domain, e.rel, e.weight, n2.id,
                   n1.name
            FROM edge e
            JOIN node n1 ON n1.id IN (e.src, e.dst) AND n1.id IN ({ph})
            JOIN node n2 ON n2.id IN (e.src, e.dst) AND n2.id != n1.id
            WHERE e.weight >= :w {relf} AND n2.status != 'archived'""", **binds)
        layer, nxt = [], {}
        for name2, title, dom, erel, w, nid, via in cur.fetchall():
            if nid in seen:
                continue
            seen.add(nid)
            nxt[nid] = None
            layer.append({"name": name2, "title": title, "domain": dom,
                          "rel": erel, "weight": float(w), "via": via})
        if layer:
            layers.append({"hop": hop, "nodes": layer})
        frontier = nxt
    return {"start": start, "layers": layers}


def update(name, title="", summary="", body="", status="", confidence=-1.0,
           add_tags=None, attrs=None, verified=False):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT title, summary, tags, attrs FROM node WHERE name = :n", n=name)
    r = cur.fetchone()
    if not r:
        return {"error": f"no node named '{name}'"}
    raw_tags = jval(lob(r[2]))
    old_title, old_summary, old_tags = r[0], r[1], raw_tags or []
    old_attrs = plain(jval(lob(r[3]))) or {}

    sets, binds = ["updated_at = SYSTIMESTAMP"], {"n": name}
    if title:
        sets.append("title = :title"); binds["title"] = title
    if summary:
        sets.append("summary = :summary"); binds["summary"] = summary
    if body:
        sets.append("body = :body"); binds["body"] = body
    if status:
        sets.append("status = :status"); binds["status"] = status
    if confidence >= 0:
        sets.append("confidence = :conf"); binds["conf"] = confidence
    if attrs:
        merged = {**old_attrs, **attrs}          # merge, don't clobber
        merged = {k: v for k, v in merged.items() if v is not None}  # None deletes a key
        sets.append("attrs = :attrs"); binds["attrs"] = json.dumps(merged)
    new_tags = old_tags
    if add_tags:
        new_tags = sorted(set(old_tags) | set(add_tags))
        sets.append("tags = :tags"); binds["tags"] = json.dumps(new_tags)
    if verified:
        sets.append("last_verified = SYSTIMESTAMP")
    if title or summary or add_tags:
        etext = embed_text(title or old_title, summary or old_summary, new_tags)
        sets.append(f"embedding = {embed_expr('etext')}")
        binds["etext"] = etext
    cur.execute(f"UPDATE node SET {', '.join(sets)} WHERE name = :n", **binds)
    conn.commit()
    return {"updated": name, "fields": [s.split(' =')[0] for s in sets]}


def forget(name, hard=False):
    conn = db()
    cur = conn.cursor()
    if hard:
        cur.execute("DELETE FROM node WHERE name = :n", n=name)
    else:
        cur.execute("""UPDATE node SET status = 'archived',
                       updated_at = SYSTIMESTAMP WHERE name = :n""", n=name)
    if cur.rowcount == 0:
        return {"error": f"no node named '{name}'"}
    conn.commit()
    return {("deleted" if hard else "archived"): name}


def vocab(action="list", category="", value="", description="", inverse_rel=""):
    conn = db()
    cur = conn.cursor()
    if action == "add":
        if not (category and value and description):
            return {"error": "add needs category, value, description"}
        try:
            cur.execute("""INSERT INTO vocabulary (category, value, description, inverse_rel)
                           VALUES (:c, :v, :d, :i)""",
                        c=category, v=value, d=description, i=inverse_rel or None)
            conn.commit()
            return {"added": f"{category}:{value}"}
        except oracledb.IntegrityError:
            return {"error": "already exists"}
    where, binds = "", {}
    if category:
        where = "WHERE category = :c"
        binds["c"] = category
    cur.execute(f"""SELECT category, value, description, inverse_rel
                    FROM vocabulary {where} ORDER BY category, value""", **binds)
    out = {}
    for c, v, d, inv in cur.fetchall():
        out.setdefault(c, []).append({"value": v, "description": d,
                                      **({"inverse": inv} if inv else {})})
    return out


def stats():
    conn = db()
    cur = conn.cursor()
    out = {}
    cur.execute("SELECT domain, COUNT(*) FROM node GROUP BY domain ORDER BY 2 DESC")
    out["nodes_by_domain"] = dict(cur.fetchall())
    cur.execute("SELECT status, COUNT(*) FROM node GROUP BY status")
    out["nodes_by_status"] = dict(cur.fetchall())
    cur.execute("SELECT rel, COUNT(*) FROM edge GROUP BY rel ORDER BY 2 DESC")
    out["edges_by_rel"] = dict(cur.fetchall())
    cur.execute("""SELECT name FROM node n WHERE NOT EXISTS
                   (SELECT 1 FROM edge e WHERE e.src = n.id OR e.dst = n.id)
                   AND status != 'archived' FETCH FIRST 20 ROWS ONLY""")
    out["orphans"] = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT name FROM node
                   WHERE (last_verified IS NULL OR last_verified < SYSTIMESTAMP - 90)
                   AND status = 'active' FETCH FIRST 20 ROWS ONLY""")
    out["stale_or_unverified"] = [r[0] for r in cur.fetchall()]
    return out


def graph_dump(include_archived=False):
    """Whole graph in one call — nodes (brief) + edges. Powers the web explorer."""
    conn = db()
    cur = conn.cursor()
    where = "" if include_archived else "WHERE status != 'archived'"
    cur.execute(f"""SELECT name, domain, kind, title, summary, status,
                           confidence, TO_CHAR(updated_at,'YYYY-MM-DD')
                    FROM node {where}""")
    nodes = [{"name": n, "domain": d, "kind": k, "title": t, "summary": s,
              "status": st, "confidence": float(c) if c is not None else None,
              "updated": u}
             for n, d, k, t, s, st, c, u in cur.fetchall()]
    ewhere = "" if include_archived else \
        "WHERE n1.status != 'archived' AND n2.status != 'archived'"
    cur.execute(f"""SELECT n1.name, n2.name, e.rel, e.weight, e.note
                    FROM edge e JOIN node n1 ON n1.id = e.src
                    JOIN node n2 ON n2.id = e.dst {ewhere}""")
    edges = [{"src": a, "dst": b, "rel": r, "weight": float(w), "note": nt}
             for a, b, r, w, nt in cur.fetchall()]
    return {"nodes": nodes, "edges": edges}


def export_graph(include_secret=False):
    """Full-fidelity JSON dump of nodes+edges+vocabulary for backup/transfer.
    secret-sensitivity node bodies are redacted unless include_secret=True."""
    conn = db()
    cur = conn.cursor()
    cur.execute("""SELECT name, domain, kind, title, summary, body, attrs, tags,
                          aliases, status, sensitivity, source, confidence,
                          TO_CHAR(last_verified,'YYYY-MM-DD"T"HH24:MI:SS'),
                          TO_CHAR(created_at,'YYYY-MM-DD"T"HH24:MI:SS'),
                          TO_CHAR(updated_at,'YYYY-MM-DD"T"HH24:MI:SS')
                   FROM node""")
    cols = ["NAME", "DOMAIN", "KIND", "TITLE", "SUMMARY", "BODY", "ATTRS", "TAGS",
            "ALIASES", "STATUS", "SENSITIVITY", "SOURCE", "CONFIDENCE",
            "LAST_VERIFIED", "CREATED_AT", "UPDATED_AT"]
    nodes = []
    for r in cur.fetchall():
        n = node_row(r, cols)
        if n["sensitivity"] == "secret" and not include_secret:
            n["body"] = "[REDACTED — export with include_secret to keep]"
            if n.get("attrs"):
                n["attrs"] = {"_redacted": True}
        nodes.append(n)
    cur.execute("""SELECT n1.name, n2.name, e.rel, e.weight, e.note,
                          TO_CHAR(e.created_at,'YYYY-MM-DD"T"HH24:MI:SS')
                   FROM edge e JOIN node n1 ON n1.id = e.src
                   JOIN node n2 ON n2.id = e.dst""")
    edges = [{"src": a, "dst": b, "rel": rel, "weight": float(w), "note": nt,
              "created_at": c} for a, b, rel, w, nt, c in cur.fetchall()]
    return {"format": "graphmem-export-v1", "nodes": nodes, "edges": edges,
            "vocabulary": vocab()}


def import_graph(data, mode="merge"):
    """Import a graphmem-export-v1 dump. mode='merge' skips existing names/edges;
    node embeddings are recomputed in-DB from title+summary+tags."""
    if data.get("format") != "graphmem-export-v1":
        return {"error": "not a graphmem-export-v1 dump"}
    conn = db()
    cur = conn.cursor()
    for cat, entries in (data.get("vocabulary") or {}).items():
        for e in entries:
            try:
                cur.execute("""INSERT INTO vocabulary (category, value, description, inverse_rel)
                               VALUES (:c, :v, :d, :i)""",
                            c=cat, v=e["value"], d=e.get("description"),
                            i=e.get("inverse"))
            except oracledb.IntegrityError:
                pass
    n_new = n_skip = 0
    for n in data.get("nodes", []):
        etext = embed_text(n["title"], n.get("summary"), n.get("tags"))
        try:
            cur.execute(f"""
                INSERT INTO node (name, domain, kind, title, summary, body, attrs,
                                  tags, aliases, status, sensitivity, source,
                                  confidence, embedding)
                VALUES (:name, :domain, :kind, :title, :summary, :body, :attrs,
                        :tags, :aliases, :status, :sens, :source, :conf,
                        {embed_expr('etext')})""",
                name=n["name"], domain=n["domain"], kind=n["kind"],
                title=n["title"], summary=n.get("summary"), body=n.get("body"),
                attrs=json.dumps(n["attrs"]) if n.get("attrs") else None,
                tags=json.dumps(n["tags"]) if n.get("tags") else None,
                aliases=json.dumps(n["aliases"]) if n.get("aliases") else None,
                status=n.get("status", "active"),
                sens=n.get("sensitivity", "private"), source=n.get("source"),
                conf=n.get("confidence", 0.8), etext=etext)
            n_new += 1
        except oracledb.IntegrityError:
            n_skip += 1
    e_new = e_skip = 0
    for e in data.get("edges", []):
        try:
            cur.execute("""INSERT INTO edge (src, dst, rel, weight, note)
                           SELECT a.id, b.id, :rel, :w, :note FROM node a, node b
                           WHERE a.name = :src AND b.name = :dst""",
                        rel=e["rel"], w=e.get("weight", 0.5), note=e.get("note"),
                        src=e["src"], dst=e["dst"])
            e_new += cur.rowcount
        except oracledb.IntegrityError:
            e_skip += 1
    conn.commit()
    return {"nodes_imported": n_new, "nodes_skipped": n_skip,
            "edges_imported": e_new, "edges_skipped": e_skip}
