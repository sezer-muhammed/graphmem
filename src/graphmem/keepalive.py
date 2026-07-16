"""Daily keep-alive: touch the DB so Always Free ADB never idles 7 days.
If stopped, start it via OCI instance principal (needs ADB_OCID + oci pkg).
Run: python -m graphmem.keepalive"""
import sys
import time

from .db import connect, load_env


def touch():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM dual")
    cur.fetchone()
    conn.close()


def ensure_started():
    import oci
    env = load_env()
    ocid = env.get("ADB_OCID")
    if not ocid:
        return False
    region = env.get("ADB_REGION") or "us-ashburn-1"
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    client = oci.database.DatabaseClient(config={"region": region}, signer=signer)
    state = client.get_autonomous_database(ocid).data.lifecycle_state
    if state == "STOPPED":
        print("DB stopped — starting...")
        client.start_autonomous_database(ocid)
        for _ in range(60):
            time.sleep(20)
            if client.get_autonomous_database(ocid).data.lifecycle_state == "AVAILABLE":
                return True
        return False
    return state == "AVAILABLE"


if __name__ == "__main__":
    try:
        touch()
        print("keepalive OK")
    except Exception as e:
        print(f"direct touch failed ({e}); checking lifecycle...")
        if ensure_started():
            touch()
            print("keepalive OK (after start)")
        else:
            print("keepalive FAILED")
            sys.exit(1)
