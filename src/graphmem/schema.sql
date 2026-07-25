-- GraphMem schema v1 — Oracle ADB 26ai
-- Everything is a node; edges are typed, directed, weighted (Markov walk).
-- vocabulary keeps open-ended domain/kind/rel values consistent.

CREATE TABLE app_user (
    id          VARCHAR2(64)  PRIMARY KEY,
    issuer      VARCHAR2(255) NOT NULL,
    subject     VARCHAR2(255) NOT NULL,
    email       VARCHAR2(320),
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT app_user_identity_uq UNIQUE (issuer, subject)
);

CREATE TABLE tenant (
    id          VARCHAR2(64)  PRIMARY KEY,
    name        VARCHAR2(200) NOT NULL,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE tenant_membership (
    tenant_id   VARCHAR2(64) NOT NULL REFERENCES tenant(id),
    user_id     VARCHAR2(64) NOT NULL REFERENCES app_user(id),
    role        VARCHAR2(16) NOT NULL CHECK (role IN ('owner','member','viewer')),
    CONSTRAINT tenant_membership_pk PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE graph (
    tenant_id   VARCHAR2(64) NOT NULL REFERENCES tenant(id),
    id          VARCHAR2(64) NOT NULL,
    name        VARCHAR2(200) NOT NULL,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT graph_pk PRIMARY KEY (tenant_id, id)
);

INSERT INTO tenant(id,name) VALUES ('legacy-local','Legacy local tenant');
INSERT INTO graph(tenant_id,id,name) VALUES ('legacy-local','default','Default graph');

CREATE TABLE vocabulary (
    tenant_id    VARCHAR2(64) DEFAULT 'legacy-local' NOT NULL,
    graph_id     VARCHAR2(64) DEFAULT 'default' NOT NULL,
    category     VARCHAR2(10)  NOT NULL CHECK (category IN ('domain','kind','rel')),
    value        VARCHAR2(64)  NOT NULL,
    description  VARCHAR2(400),
    inverse_rel  VARCHAR2(64),           -- rels only: part_of -> has_part; NULL = symmetric or n/a
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT vocabulary_pk PRIMARY KEY (tenant_id, graph_id, category, value),
    CONSTRAINT vocabulary_graph_fk FOREIGN KEY (tenant_id, graph_id)
      REFERENCES graph(tenant_id, id)
);

CREATE TABLE node (
    id            RAW(16)       DEFAULT SYS_GUID() PRIMARY KEY,
    tenant_id     VARCHAR2(64)   DEFAULT 'legacy-local' NOT NULL,
    graph_id      VARCHAR2(64)   DEFAULT 'default' NOT NULL,
    name          VARCHAR2(128) NOT NULL,             -- graph-scoped stable slug
    domain        VARCHAR2(64)  NOT NULL,
    kind          VARCHAR2(64)  NOT NULL,
    title         VARCHAR2(400) NOT NULL,
    summary       VARCHAR2(2000),
    body          CLOB,
    attrs         JSON,
    tags          JSON,
    aliases       JSON,
    status        VARCHAR2(16)  DEFAULT 'active' NOT NULL
                  CHECK (status IN ('active','wip','idea','archived')),
    sensitivity   VARCHAR2(16)  DEFAULT 'private' NOT NULL
                  CHECK (sensitivity IN ('public','private','secret')),
    source        VARCHAR2(400),
    confidence    NUMBER(3,2)   DEFAULT 0.8 CHECK (confidence BETWEEN 0 AND 1),
    last_verified TIMESTAMP,
    created_at    TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at    TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
    embedding     VECTOR(384, FLOAT32),               -- all-MiniLM-L12-v2 dims
    CONSTRAINT node_graph_fk FOREIGN KEY (tenant_id, graph_id)
      REFERENCES graph(tenant_id, id),
    CONSTRAINT node_scope_name_uq UNIQUE (tenant_id, graph_id, name),
    CONSTRAINT node_scope_id_uq UNIQUE (tenant_id, graph_id, id)
);

CREATE INDEX node_domain_ix ON node (tenant_id, graph_id, domain);
CREATE INDEX node_kind_ix   ON node (tenant_id, graph_id, kind);
CREATE INDEX node_status_ix ON node (tenant_id, graph_id, status);

CREATE TABLE edge (
    id              RAW(16)      DEFAULT SYS_GUID() PRIMARY KEY,
    tenant_id       VARCHAR2(64) DEFAULT 'legacy-local' NOT NULL,
    graph_id        VARCHAR2(64) DEFAULT 'default' NOT NULL,
    src             RAW(16)      NOT NULL,
    dst             RAW(16)      NOT NULL,
    rel             VARCHAR2(64) NOT NULL,
    weight          NUMBER(3,2)  DEFAULT 0.5 NOT NULL CHECK (weight BETWEEN 0 AND 1),
    note            VARCHAR2(1000),
    created_at      TIMESTAMP    DEFAULT SYSTIMESTAMP NOT NULL,
    last_reinforced TIMESTAMP,
    CONSTRAINT edge_uniq UNIQUE (tenant_id, graph_id, src, dst, rel),
    CONSTRAINT edge_no_self CHECK (src != dst),
    CONSTRAINT edge_graph_fk FOREIGN KEY (tenant_id, graph_id)
      REFERENCES graph(tenant_id, id),
    CONSTRAINT edge_src_scope_fk FOREIGN KEY (tenant_id, graph_id, src)
      REFERENCES node(tenant_id, graph_id, id) ON DELETE CASCADE,
    CONSTRAINT edge_dst_scope_fk FOREIGN KEY (tenant_id, graph_id, dst)
      REFERENCES node(tenant_id, graph_id, id) ON DELETE CASCADE
);

CREATE INDEX edge_src_ix ON edge (tenant_id, graph_id, src);
CREATE INDEX edge_dst_ix ON edge (tenant_id, graph_id, dst);

-- Oracle Text keyword index over title+summary+body comes after data model
-- settles (CTX_DDL multi-column datastore); v1 keyword search uses
-- UPPER(title/summary) LIKE + JSON_EXISTS(tags) which is fine at small scale.

-- Seed vocabulary (open-ended — INSERT adds more at any time, no migration)
INSERT INTO vocabulary (category, value, description) VALUES ('domain','github','Repos, PRs, issues, code hosting');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','design','Design language, UI/UX, templates');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','plan','Plans and roadmaps');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','engineering','Technical knowledge, infra, how things work');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','ideas','Raw ideas, sparks, maybes');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','saas','External services, pricing, accounts');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','env','Environments, servers, topology (no plaintext secrets!)');
INSERT INTO vocabulary (category, value, description) VALUES ('domain','personal','About the user: preferences, context');

INSERT INTO vocabulary (category, value, description) VALUES ('kind','repo','A code repository');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','project','An ongoing effort');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','plan','A concrete plan');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','idea','An idea, not yet a plan');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','service','A running/deployable service');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','decision','A choice made, with reasoning');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','doc','A document or long-form note');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','snippet','Code or config worth keeping');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','person','A person or org');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','task','Something to do');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','reference','Pointer to an external resource');
INSERT INTO vocabulary (category, value, description) VALUES ('kind','fact','A discrete fact');

INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','relates_to','Generic association (symmetric)', NULL);
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','depends_on','Src needs dst', 'required_by');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','required_by','Dst needs src', 'depends_on');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','part_of','Src is a component of dst', 'has_part');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','has_part','Dst is a component of src', 'part_of');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','uses','Src makes use of dst', 'used_by');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','used_by','Dst makes use of src', 'uses');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','implements','Src realizes dst (idea/plan)', 'implemented_by');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','implemented_by','Dst realizes src', 'implements');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','inspired_by','Src grew out of dst', NULL);
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','deployed_on','Src runs on dst', 'hosts');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','hosts','Src runs dst', 'deployed_on');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','references','Src cites/points to dst', NULL);
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','supersedes','Src replaces dst (dst is stale)', 'superseded_by');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','superseded_by','Src is replaced by dst', 'supersedes');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','blocks','Src prevents dst from proceeding', 'blocked_by');
INSERT INTO vocabulary (category, value, description, inverse_rel) VALUES ('rel','blocked_by','Src is blocked by dst', 'blocks');

COMMIT;
