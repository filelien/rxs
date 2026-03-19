-- ============================================================
--  RAXUS — Base MySQL applicative
--  Stocke TOUT ce qui se passe sur la plateforme
-- ============================================================

CREATE DATABASE IF NOT EXISTS raxus_app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE raxus_app;

-- ── Utilisateurs ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id            VARCHAR(36)  NOT NULL PRIMARY KEY,
  username      VARCHAR(100) NOT NULL UNIQUE,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role          ENUM('admin','dba','analyst','viewer') NOT NULL DEFAULT 'viewer',
  full_name     VARCHAR(255),
  avatar_url    VARCHAR(500),
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  last_login_at DATETIME,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_username (username),
  INDEX idx_email (email),
  INDEX idx_role (role)
);

-- ── Connexions aux bases de données ──────────────────────────
CREATE TABLE IF NOT EXISTS db_connections (
  id               VARCHAR(36)  NOT NULL PRIMARY KEY,
  name             VARCHAR(200) NOT NULL UNIQUE,
  db_type          ENUM('oracle','mysql','postgresql','mongodb','redis','sqlite') NOT NULL,
  host             VARCHAR(500) NOT NULL,
  port             INT,
  database_name    VARCHAR(200),
  username         VARCHAR(200),
  credentials_enc  TEXT         NOT NULL,  -- AES chiffré
  description      TEXT,
  enabled          BOOLEAN NOT NULL DEFAULT TRUE,
  ssh_tunnel       BOOLEAN NOT NULL DEFAULT FALSE,
  ssh_host         VARCHAR(500),
  ssh_port         INT DEFAULT 22,
  ssh_user         VARCHAR(200),
  ssh_key_enc      TEXT,
  last_tested_at   DATETIME,
  last_test_ok     BOOLEAN,
  last_test_ms     INT,
  created_by       VARCHAR(36),
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_db_type (db_type),
  INDEX idx_enabled (enabled),
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- ── Historique des requêtes SQL ───────────────────────────────
CREATE TABLE IF NOT EXISTS query_history (
  id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  query_uuid    VARCHAR(36)  NOT NULL UNIQUE,
  user_id       VARCHAR(36)  NOT NULL,
  connection_id VARCHAR(36)  NOT NULL,
  sql_text      TEXT         NOT NULL,
  sql_hash      VARCHAR(64),              -- SHA256 pour déduplication
  status        ENUM('success','error','timeout','blocked') NOT NULL,
  row_count     INT DEFAULT 0,
  duration_ms   INT DEFAULT 0,
  error_msg     TEXT,
  risk_level    ENUM('safe','warn','admin_required','blocked') DEFAULT 'safe',
  executed_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_connection_id (connection_id),
  INDEX idx_executed_at (executed_at),
  INDEX idx_duration_ms (duration_ms),
  INDEX idx_status (status),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (connection_id) REFERENCES db_connections(id) ON DELETE CASCADE
);

-- ── Requêtes sauvegardées ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_queries (
  id            VARCHAR(36)  NOT NULL PRIMARY KEY,
  user_id       VARCHAR(36)  NOT NULL,
  connection_id VARCHAR(36),
  name          VARCHAR(300) NOT NULL,
  description   TEXT,
  sql_text      TEXT         NOT NULL,
  tags          JSON,
  is_public     BOOLEAN NOT NULL DEFAULT FALSE,
  run_count     INT NOT NULL DEFAULT 0,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ── Métriques de monitoring (time-series) ────────────────────
CREATE TABLE IF NOT EXISTS metrics (
  id            BIGINT    NOT NULL AUTO_INCREMENT PRIMARY KEY,
  connection_id VARCHAR(36),
  server_id     VARCHAR(100),
  metric_name   VARCHAR(200) NOT NULL,
  metric_value  DOUBLE    NOT NULL,
  labels        JSON,
  collected_at  DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_conn_metric_time (connection_id, metric_name, collected_at),
  INDEX idx_server_time (server_id, collected_at),
  INDEX idx_collected_at (collected_at)
);

-- ── Alertes ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rules (
  id                VARCHAR(36)  NOT NULL PRIMARY KEY,
  name              VARCHAR(300) NOT NULL,
  metric_name       VARCHAR(200) NOT NULL,
  condition_op      ENUM('>','<','==','!=','>=','<=') NOT NULL,
  threshold         DOUBLE NOT NULL,
  duration_minutes  INT NOT NULL DEFAULT 1,
  severity          ENUM('info','warning','critical') NOT NULL DEFAULT 'warning',
  notify_channels   JSON,                -- ["email","slack","webhook"]
  cooldown_minutes  INT NOT NULL DEFAULT 30,
  connection_id     VARCHAR(36),
  server_id         VARCHAR(100),
  enabled           BOOLEAN NOT NULL DEFAULT TRUE,
  created_by        VARCHAR(36),
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
  id            BIGINT    NOT NULL AUTO_INCREMENT PRIMARY KEY,
  rule_id       VARCHAR(36) NOT NULL,
  connection_id VARCHAR(36),
  server_id     VARCHAR(100),
  severity      ENUM('info','warning','critical') NOT NULL,
  metric_name   VARCHAR(200),
  metric_value  DOUBLE,
  threshold     DOUBLE,
  message       TEXT NOT NULL,
  status        ENUM('active','resolved','acknowledged') NOT NULL DEFAULT 'active',
  fired_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at   DATETIME,
  ack_by        VARCHAR(36),
  INDEX idx_status (status),
  INDEX idx_fired_at (fired_at),
  FOREIGN KEY (rule_id) REFERENCES alert_rules(id) ON DELETE CASCADE
);

-- ── Audit logs (append-only) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
  id              BIGINT    NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id         VARCHAR(36),
  username        VARCHAR(100),
  user_role       VARCHAR(50),
  action          VARCHAR(200) NOT NULL,   -- e.g. "query.execute"
  resource_type   VARCHAR(100),            -- "connection","query","task"...
  resource_id     VARCHAR(200),
  request_ip      VARCHAR(45),
  user_agent      TEXT,
  payload_summary TEXT,
  result          ENUM('success','failure','blocked') NOT NULL DEFAULT 'success',
  risk_score      TINYINT UNSIGNED NOT NULL DEFAULT 0,
  duration_ms     INT,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_action (action),
  INDEX idx_risk_score (risk_score),
  INDEX idx_created_at (created_at),
  INDEX idx_result (result)
);

-- ── Tâches planifiées ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
  id            VARCHAR(36)  NOT NULL PRIMARY KEY,
  name          VARCHAR(300) NOT NULL,
  type          ENUM('SQL_SCRIPT','PYTHON_SCRIPT','BACKUP','ANALYZE','REPORT') NOT NULL,
  connection_id VARCHAR(36),
  server_id     VARCHAR(100),
  payload       JSON,
  status        ENUM('pending','running','success','failed','cancelled') NOT NULL DEFAULT 'pending',
  created_by    VARCHAR(36),
  started_at    DATETIME,
  finished_at   DATETIME,
  duration_ms   INT,
  output        TEXT,
  error_msg     TEXT,
  retry_count   TINYINT NOT NULL DEFAULT 0,
  max_retries   TINYINT NOT NULL DEFAULT 2,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_status (status),
  INDEX idx_created_at (created_at),
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS schedules (
  id            VARCHAR(36)  NOT NULL PRIMARY KEY,
  name          VARCHAR(300) NOT NULL,
  task_type     VARCHAR(50)  NOT NULL,
  connection_id VARCHAR(36),
  payload       JSON,
  cron_expr     VARCHAR(100) NOT NULL,
  timezone      VARCHAR(100) NOT NULL DEFAULT 'UTC',
  enabled       BOOLEAN NOT NULL DEFAULT TRUE,
  paused        BOOLEAN NOT NULL DEFAULT FALSE,
  next_run_at   DATETIME,
  last_run_at   DATETIME,
  run_count     INT NOT NULL DEFAULT 0,
  created_by    VARCHAR(36),
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_next_run (next_run_at),
  INDEX idx_enabled (enabled)
);

-- ── Sessions de chat IA ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
  id            VARCHAR(36)  NOT NULL PRIMARY KEY,
  user_id       VARCHAR(36)  NOT NULL,
  connection_id VARCHAR(36),
  title         VARCHAR(500),
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_msg_at   DATETIME,
  INDEX idx_user_id (user_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id            BIGINT    NOT NULL AUTO_INCREMENT PRIMARY KEY,
  session_id    VARCHAR(36) NOT NULL,
  role          ENUM('user','assistant','system') NOT NULL,
  content       TEXT NOT NULL,
  sql_generated TEXT,
  intent        VARCHAR(100),
  duration_ms   INT,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_session_id (session_id),
  FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

-- ── Serveurs monitorés (agents) ───────────────────────────────
CREATE TABLE IF NOT EXISTS servers (
  id            VARCHAR(100) NOT NULL PRIMARY KEY,  -- server_id de l'agent
  hostname      VARCHAR(300),
  ip_address    VARCHAR(45),
  description   TEXT,
  secret_key_hash VARCHAR(64),  -- SHA256 du secret_key pour validation
  status        ENUM('online','offline','unknown') NOT NULL DEFAULT 'unknown',
  last_seen_at  DATETIME,
  agent_version VARCHAR(50),
  os_info       JSON,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Workflows if-then ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workflow_rules (
  id                VARCHAR(36)  NOT NULL PRIMARY KEY,
  name              VARCHAR(300) NOT NULL,
  trigger_metric    VARCHAR(200) NOT NULL,
  trigger_condition VARCHAR(10)  NOT NULL,
  trigger_value     DOUBLE NOT NULL,
  connection_id     VARCHAR(36),
  server_id         VARCHAR(100),
  action_type       VARCHAR(100) NOT NULL,
  action_payload    JSON,
  cooldown_minutes  INT NOT NULL DEFAULT 30,
  enabled           BOOLEAN NOT NULL DEFAULT TRUE,
  last_fired_at     DATETIME,
  fire_count        INT NOT NULL DEFAULT 0,
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Utilisateur admin par défaut ──────────────────────────────
INSERT IGNORE INTO users (id, username, email, password_hash, role, full_name)
VALUES (
  'usr-admin-001',
  'admin',
  'admin@raxus.io',
  SHA2('Admin@Raxus2025!', 256),
  'admin',
  'Administrateur Raxus'
);
