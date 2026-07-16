"""Connection + env handling for GraphMem (Oracle ADB, thin mode)."""
import os

import oracledb


def find_env() -> str:
    """Locate the .env file, in order: $GRAPHMEM_ENV, ~/.graphmem/.env
    (standard per-user location, install-method independent), else walk up
    from this file to the repo root (editable-install layout)."""
    explicit = os.environ.get("GRAPHMEM_ENV")
    if explicit:
        return explicit
    home_env = os.path.expanduser("~/.graphmem/.env")
    if os.path.exists(home_env):
        return home_env
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        candidate = os.path.join(d, ".env")
        if os.path.exists(candidate):
            return candidate
        d = os.path.dirname(d)
    raise FileNotFoundError(
        "no .env found — create ~/.graphmem/.env (see .env.example), "
        "or point GRAPHMEM_ENV at one")


def load_env(path: str | None = None) -> dict:
    env = {}
    with open(path or find_env()) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def connect(env: dict | None = None) -> oracledb.Connection:
    env = env or load_env()
    return oracledb.connect(
        user=env["ADB_USER"],
        password=env["ADB_PASSWORD"],
        dsn=env["ADB_DSN"],
        config_dir=env["ADB_WALLET_DIR"],
        wallet_location=env["ADB_WALLET_DIR"],
        wallet_password=env["ADB_WALLET_PASSWORD"],
    )
