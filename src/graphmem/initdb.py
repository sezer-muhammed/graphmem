"""One-shot initialization for a fresh database: schema + in-DB ONNX model.

Idempotent — safe to re-run (existing objects are skipped).
"""
import os
import re

from .db import connect

# Oracle's prebuilt, augmented all-MiniLM-L12-v2 (public OML-Resources bucket)
ONNX_URI = ("https://adwc4pm.objectstorage.us-ashburn-1.oci.customer-oci.com/"
            "p/eLddQappgBJ7jNi6Guz9m9LOtYe2u8LWY19GfgU8flFK4N9YgP4kTlrE9Px3pE12/"
            "n/adwc4pm/b/OML-Resources/o/all_MiniLM_L12_v2.onnx")
MODEL_NAME = "ALL_MINILM_L12_V2"
SKIP_ERRORS = ("ORA-00955", "ORA-02264", "ORA-00001")  # already exists


def init_db():
    conn = connect()
    cur = conn.cursor()

    sql_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    sql = re.sub(r"--[^\n]*", "", open(sql_path).read())
    ok = skip = 0
    for st in (s.strip() for s in sql.split(";") if s.strip()):
        try:
            cur.execute(st)
            ok += 1
        except Exception as e:
            if any(code in str(e) for code in SKIP_ERRORS):
                skip += 1
            else:
                raise
    conn.commit()
    print(f"schema: {ok} applied, {skip} already existed")

    cur.execute("SELECT COUNT(*) FROM user_mining_models WHERE model_name = :m",
                m=MODEL_NAME)
    if cur.fetchone()[0]:
        print(f"onnx model {MODEL_NAME}: already loaded")
    else:
        print(f"loading onnx model {MODEL_NAME} (~100 MB, may take a minute)...")
        cur.execute("""
            BEGIN
              DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD(
                model_name => :m, credential => NULL, uri => :u,
                metadata => JSON('{"function":"embedding","embeddingOutput":"embedding","input":{"input":["DATA"]}}')
              );
            END;""", m=MODEL_NAME, u=ONNX_URI)
        print("onnx model loaded")

    cur.execute(f"""SELECT ROUND(VECTOR_DISTANCE(
        VECTOR_EMBEDDING({MODEL_NAME} USING 'hello world' AS DATA),
        VECTOR_EMBEDDING({MODEL_NAME} USING 'hi there' AS DATA), COSINE), 3)
        FROM dual""")
    print(f"embedding smoke test distance: {cur.fetchone()[0]} — init OK")
    conn.close()
