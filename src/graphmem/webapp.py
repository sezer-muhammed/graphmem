"""graphmem web explorer — browse, search, and Markov-walk the memory graph.

Run: GRAPHMEM_WEB_HOST=127.0.0.1 GRAPHMEM_WEB_PORT=8090 python -m graphmem.webapp

Auth: if GRAPHMEM_WEB_USER + GRAPHMEM_WEB_PASSWORD are set (in .env or the
environment), every route requires HTTP Basic auth. Unset = open (e.g. localhost).
"""
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import core
from .db import load_env

STATIC = os.path.join(os.path.dirname(__file__), "static")

try:
    _env = load_env()
except FileNotFoundError:
    _env = {}
WEB_USER = os.environ.get("GRAPHMEM_WEB_USER") or _env.get("GRAPHMEM_WEB_USER")
WEB_PASS = os.environ.get("GRAPHMEM_WEB_PASSWORD") or _env.get("GRAPHMEM_WEB_PASSWORD")

# Fail closed: a half-configured credential (only user OR only password) must
# never silently disable auth on a potentially public explorer.
if bool(WEB_USER) != bool(WEB_PASS):
    raise RuntimeError("graphmem web: set BOTH GRAPHMEM_WEB_USER and "
                       "GRAPHMEM_WEB_PASSWORD to require auth, or neither to run open")

_basic = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(_basic)):
    user_ok = secrets.compare_digest(credentials.username.encode(), WEB_USER.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), WEB_PASS.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="bad credentials",
                            headers={"WWW-Authenticate": "Basic"})


app = FastAPI(title="graphmem explorer",
              dependencies=[Depends(require_auth)] if (WEB_USER and WEB_PASS) else [])


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/tables")
def tables():
    return FileResponse(os.path.join(STATIC, "tables.html"))


@app.get("/diagram")
def diagram():
    return FileResponse(os.path.join(STATIC, "diagram.html"))


@app.get("/api/graph")
def api_graph():
    return JSONResponse(core.graph_dump())


@app.get("/api/node/{name}")
def api_node(name: str):
    # Public exposure guard: never serve raw secret values. redact_secret masks
    # BOTH body and attrs of a sensitivity=secret node; title/summary/edges stay
    # visible. Applied on every node-detail surface for consistency.
    return JSONResponse(core.redact_secret(core.get(name)))


@app.get("/api/recall")
def api_recall(q: str, k: int = 8):
    return JSONResponse(core.recall(q, k, include_neighbors=False))


@app.get("/api/walk/{name}")
def api_walk(name: str, depth: int = 2, min_weight: float = 0.0):
    return JSONResponse(core.walk(name, depth, min_weight))


@app.get("/api/stats")
def api_stats():
    return JSONResponse(core.stats())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,
                host=os.environ.get("GRAPHMEM_WEB_HOST", "127.0.0.1"),
                port=int(os.environ.get("GRAPHMEM_WEB_PORT", "8090")))
