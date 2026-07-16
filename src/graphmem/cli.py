#!/usr/bin/env python3
"""graphmem CLI — the same operations as the MCP server, from your shell.

Examples:
  graphmem recall "how do I reopen the website"
  graphmem search --domain env
  graphmem get my-server
  graphmem remember my-idea ideas idea "Title" "One-line summary" --tags a,b
  graphmem link my-idea graphmem-project relates_to -w 0.7
  graphmem walk graphmem-project -d 2
  graphmem stats
  graphmem init-db          # fresh database: apply schema + load ONNX model
"""
import argparse
import json
import sys

from . import core

# Windows console defaults to cp1252 and crashes on non-ASCII output
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def p(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(prog="graphmem",
                                 description="knowledge-graph memory CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("recall", help="semantic search")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--domain", default="")
    s.add_argument("--no-neighbors", action="store_true")

    s = sub.add_parser("search", help="keyword/filter search")
    s.add_argument("text", nargs="?", default="")
    s.add_argument("--domain", default="")
    s.add_argument("--kind", default="")
    s.add_argument("--status", default="")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("get", help="full node + edges")
    s.add_argument("name")

    s = sub.add_parser("remember", help="store a node")
    s.add_argument("name")
    s.add_argument("domain")
    s.add_argument("kind")
    s.add_argument("title")
    s.add_argument("summary")
    s.add_argument("--body", default="")
    s.add_argument("--tags", default="", help="comma-separated")
    s.add_argument("--attrs", default="", help='JSON object, e.g. \'{"port":80}\'')
    s.add_argument("--source", default="cli")
    s.add_argument("--sensitivity", default="private")
    s.add_argument("--confidence", type=float, default=0.8)
    s.add_argument("--force", action="store_true")

    s = sub.add_parser("link", help="connect two nodes")
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("rel")
    s.add_argument("-w", "--weight", type=float, default=0.5)
    s.add_argument("--note", default="")

    s = sub.add_parser("walk", help="graph traversal")
    s.add_argument("start")
    s.add_argument("-d", "--depth", type=int, default=2)
    s.add_argument("--min-weight", type=float, default=0.0)
    s.add_argument("--rel", default="")

    s = sub.add_parser("update", help="patch a node")
    s.add_argument("name")
    s.add_argument("--title", default="")
    s.add_argument("--summary", default="")
    s.add_argument("--body", default="")
    s.add_argument("--status", default="")
    s.add_argument("--add-tags", default="")
    s.add_argument("--attrs", default="", help="JSON object; merged into existing attrs")
    s.add_argument("--verified", action="store_true")

    s = sub.add_parser("forget", help="archive (or --hard delete) a node")
    s.add_argument("name")
    s.add_argument("--hard", action="store_true")

    s = sub.add_parser("vocab", help="list/add domains, kinds, rels")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add"])
    s.add_argument("--category", default="")
    s.add_argument("--value", default="")
    s.add_argument("--description", default="")
    s.add_argument("--inverse", default="")

    sub.add_parser("stats", help="graph overview")

    sub.add_parser("init-db", help="fresh DB: apply schema + load ONNX embed model")

    s = sub.add_parser("export", help="dump whole graph to JSON (stdout or file)")
    s.add_argument("-o", "--out", default="")
    s.add_argument("--include-secret", action="store_true")

    s = sub.add_parser("import", help="import a graphmem-export-v1 JSON dump")
    s.add_argument("file")

    a = ap.parse_args()

    if a.cmd == "recall":
        p(core.recall(a.query, a.k, a.domain, not a.no_neighbors))
    elif a.cmd == "search":
        p(core.search(a.text, a.domain, a.kind, a.status, a.limit))
    elif a.cmd == "get":
        p(core.get(a.name))
    elif a.cmd == "remember":
        tags = [t.strip() for t in a.tags.split(",") if t.strip()] or None
        attrs = json.loads(a.attrs) if a.attrs else None
        p(core.remember(a.name, a.domain, a.kind, a.title, a.summary, a.body,
                        tags, attrs, None, a.sensitivity, a.source,
                        a.confidence, a.force))
    elif a.cmd == "link":
        p(core.link(a.src, a.dst, a.rel, a.weight, a.note))
    elif a.cmd == "walk":
        p(core.walk(a.start, a.depth, a.min_weight, a.rel))
    elif a.cmd == "update":
        tags = [t.strip() for t in a.add_tags.split(",") if t.strip()] or None
        attrs = json.loads(a.attrs) if a.attrs else None
        p(core.update(a.name, a.title, a.summary, a.body, a.status, -1.0,
                      tags, attrs, a.verified))
    elif a.cmd == "forget":
        p(core.forget(a.name, a.hard))
    elif a.cmd == "vocab":
        p(core.vocab(a.action, a.category, a.value, a.description, a.inverse))
    elif a.cmd == "stats":
        p(core.stats())
    elif a.cmd == "init-db":
        from .initdb import init_db
        init_db()
    elif a.cmd == "export":
        data = core.export_graph(a.include_secret)
        if a.out:
            with open(a.out, "w") as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            print(f"wrote {a.out}: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
        else:
            p(data)
    elif a.cmd == "import":
        with open(a.file) as f:
            p(core.import_graph(json.load(f)))
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
