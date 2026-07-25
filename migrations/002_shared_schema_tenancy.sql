-- GraphMem v2 shared-schema tenancy foundation (Oracle ADB 26ai).
-- Review/run manually after backup and clone rehearsal. Restart-safe DDL.
SET DEFINE OFF;

DECLARE
  PROCEDURE ddl_if_missing(p_sql CLOB, p_missing_code NUMBER) IS
  BEGIN EXECUTE IMMEDIATE p_sql;
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != p_missing_code THEN RAISE; END IF;
  END;
BEGIN
  ddl_if_missing('CREATE TABLE schema_migration (
    version VARCHAR2(64) PRIMARY KEY, applied_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    checksum VARCHAR2(128) NOT NULL)', -955);
  ddl_if_missing('CREATE TABLE app_user (
    id VARCHAR2(64) PRIMARY KEY, issuer VARCHAR2(255) NOT NULL,
    subject VARCHAR2(255) NOT NULL, email VARCHAR2(320),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT app_user_identity_uq UNIQUE (issuer, subject))', -955);
  ddl_if_missing('CREATE TABLE tenant (
    id VARCHAR2(64) PRIMARY KEY, name VARCHAR2(200) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL)', -955);
  ddl_if_missing('CREATE TABLE tenant_membership (
    tenant_id VARCHAR2(64) NOT NULL REFERENCES tenant(id),
    user_id VARCHAR2(64) NOT NULL REFERENCES app_user(id),
    role VARCHAR2(16) NOT NULL CHECK (role IN (''owner'',''member'',''viewer'')),
    CONSTRAINT tenant_membership_pk PRIMARY KEY (tenant_id,user_id))', -955);
  ddl_if_missing('CREATE TABLE graph (
    tenant_id VARCHAR2(64) NOT NULL REFERENCES tenant(id),
    id VARCHAR2(64) NOT NULL, name VARCHAR2(200) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT graph_pk PRIMARY KEY (tenant_id,id))', -955);
END;
/

DECLARE
  PROCEDURE add_col(p_table VARCHAR2, p_column VARCHAR2, p_type VARCHAR2) IS n NUMBER;
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tab_columns
      WHERE table_name=UPPER(p_table) AND column_name=UPPER(p_column);
    IF n=0 THEN EXECUTE IMMEDIATE 'ALTER TABLE '||p_table||' ADD ('||p_column||' '||p_type||')'; END IF;
  END;
BEGIN
  add_col('node','tenant_id','VARCHAR2(64)');
  add_col('node','graph_id','VARCHAR2(64)');
  add_col('edge','tenant_id','VARCHAR2(64)');
  add_col('edge','graph_id','VARCHAR2(64)');
  add_col('vocabulary','tenant_id','VARCHAR2(64)');
  add_col('vocabulary','graph_id','VARCHAR2(64)');
END;
/

MERGE INTO tenant t USING (SELECT 'legacy-local' id FROM dual) s
ON (t.id=s.id) WHEN NOT MATCHED THEN INSERT(id,name) VALUES(s.id,'Legacy local tenant');
MERGE INTO graph g USING (SELECT 'legacy-local' tenant_id,'default' id FROM dual) s
ON (g.tenant_id=s.tenant_id AND g.id=s.id)
WHEN NOT MATCHED THEN INSERT(tenant_id,id,name) VALUES(s.tenant_id,s.id,'Default graph');
UPDATE node SET tenant_id='legacy-local',graph_id='default'
 WHERE tenant_id IS NULL OR graph_id IS NULL;
UPDATE edge SET tenant_id='legacy-local',graph_id='default'
 WHERE tenant_id IS NULL OR graph_id IS NULL;
UPDATE vocabulary SET tenant_id='legacy-local',graph_id='default'
 WHERE tenant_id IS NULL OR graph_id IS NULL;
COMMIT;

DECLARE n NUMBER;
BEGIN
  SELECT COUNT(*) INTO n FROM edge e
   WHERE NOT EXISTS (SELECT 1 FROM node s WHERE s.id=e.src AND
     s.tenant_id=e.tenant_id AND s.graph_id=e.graph_id)
      OR NOT EXISTS (SELECT 1 FROM node d WHERE d.id=e.dst AND
     d.tenant_id=e.tenant_id AND d.graph_id=e.graph_id);
  IF n != 0 THEN RAISE_APPLICATION_ERROR(-20001,'cross-scope/orphan edges found'); END IF;
END;
/

DECLARE
  PROCEDURE drop_constraint_if_exists(p_table VARCHAR2,p_name VARCHAR2) IS n NUMBER;
  BEGIN SELECT COUNT(*) INTO n FROM user_constraints
    WHERE table_name=UPPER(p_table) AND constraint_name=UPPER(p_name);
    IF n>0 THEN EXECUTE IMMEDIATE 'ALTER TABLE '||p_table||' DROP CONSTRAINT '||p_name; END IF;
  END;
  PROCEDURE ddl_if_exists(p_sql CLOB) IS
  BEGIN EXECUTE IMMEDIATE p_sql; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF; END;
BEGIN
  -- v1 declared node.name UNIQUE without naming it. Resolve the generated
  -- constraint by its exact one-column shape; never guess a SYS_C name.
  FOR r IN (
    SELECT c.constraint_name
      FROM user_constraints c JOIN user_cons_columns cc
        ON cc.constraint_name=c.constraint_name
     WHERE c.table_name='NODE' AND c.constraint_type='U'
     GROUP BY c.constraint_name
    HAVING COUNT(*)=1 AND MAX(cc.column_name)='NAME'
  ) LOOP
    EXECUTE IMMEDIATE 'ALTER TABLE node DROP CONSTRAINT '||r.constraint_name;
  END LOOP;
  drop_constraint_if_exists('edge','EDGE_UNIQ');
  drop_constraint_if_exists('vocabulary','VOCABULARY_PK');
  ddl_if_exists('CREATE UNIQUE INDEX node_scope_id_uq ON node(tenant_id,graph_id,id)');
  ddl_if_exists('CREATE UNIQUE INDEX node_scope_name_uq ON node(tenant_id,graph_id,name)');
  ddl_if_exists('CREATE UNIQUE INDEX edge_scope_uq ON edge(tenant_id,graph_id,src,dst,rel)');
  ddl_if_exists('CREATE UNIQUE INDEX vocabulary_scope_uq ON vocabulary(tenant_id,graph_id,category,value)');
END;
/

ALTER TABLE node MODIFY (tenant_id NOT NULL, graph_id NOT NULL);
ALTER TABLE edge MODIFY (tenant_id NOT NULL, graph_id NOT NULL);
ALTER TABLE vocabulary MODIFY (tenant_id NOT NULL, graph_id NOT NULL);

DECLARE
  PROCEDURE add_constraint(p_table VARCHAR2,p_name VARCHAR2,p_clause CLOB) IS n NUMBER;
  BEGIN SELECT COUNT(*) INTO n FROM user_constraints WHERE constraint_name=UPPER(p_name);
    IF n=0 THEN EXECUTE IMMEDIATE 'ALTER TABLE '||p_table||' ADD CONSTRAINT '||p_name||' '||p_clause; END IF;
  END;
BEGIN
  add_constraint('node','node_graph_fk',
    'FOREIGN KEY (tenant_id,graph_id) REFERENCES graph(tenant_id,id)');
  add_constraint('edge','edge_graph_fk',
    'FOREIGN KEY (tenant_id,graph_id) REFERENCES graph(tenant_id,id)');
  add_constraint('edge','edge_src_scope_fk',
    'FOREIGN KEY (tenant_id,graph_id,src) REFERENCES node(tenant_id,graph_id,id) ON DELETE CASCADE');
  add_constraint('edge','edge_dst_scope_fk',
    'FOREIGN KEY (tenant_id,graph_id,dst) REFERENCES node(tenant_id,graph_id,id) ON DELETE CASCADE');
  add_constraint('vocabulary','vocabulary_graph_fk',
    'FOREIGN KEY (tenant_id,graph_id) REFERENCES graph(tenant_id,id)');
  add_constraint('vocabulary','vocabulary_scope_pk',
    'PRIMARY KEY (tenant_id,graph_id,category,value)');
END;
/

MERGE INTO schema_migration m
USING (SELECT '002_shared_schema_tenancy' version,
 'review-before-use-sha256-required' checksum FROM dual) s
ON (m.version=s.version)
WHEN NOT MATCHED THEN INSERT(version,checksum) VALUES(s.version,s.checksum);
COMMIT;
