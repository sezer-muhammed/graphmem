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


@app.get("/api/graph")
def api_graph():
    return JSONResponse(core.graph_dump())


@app.get("/api/node/{name}")
def api_node(name: str):
    return JSONResponse(core.get(name))


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
