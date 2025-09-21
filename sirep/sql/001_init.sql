-- SQL de referência (ajuste nomes de tipos conforme MySQL/SQLite)
-- SQLite: 
CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  numero_plano TEXT NOT NULL UNIQUE,
  gifug TEXT,
  razao_social TEXT,
  situacao_atual TEXT,
  situacao_anterior TEXT,
  dias_em_atraso INTEGER,
  tipo TEXT,
  dt_situacao_atual DATE,
  saldo NUMERIC(18,2),
  cmb_ajuste TEXT,
  justificativa TEXT,
  matricula TEXT,
  dt_parcela_atraso DATE,
  representacao TEXT,
  status TEXT NOT NULL,
  tipo_parcelamento TEXT,
  saldo_total NUMERIC(18,2),
  created_at DATETIME,
  updated_at DATETIME
);
CREATE INDEX IF NOT EXISTS ix_plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS ix_plans_situacao_atual ON plans(situacao_atual);

-- MySQL (InnoDB/utf8mb4):
-- CREATE TABLE plans (
--   id INT AUTO_INCREMENT PRIMARY KEY,
--   numero_plano VARCHAR(30) NOT NULL UNIQUE,
--   gifug VARCHAR(10),
--   razao_social VARCHAR(255),
--   situacao_atual VARCHAR(20),
--   situacao_anterior VARCHAR(20),
--   dias_em_atraso INT,
--   tipo VARCHAR(30),
--   dt_situacao_atual DATE,
--   saldo DECIMAL(18,2),
--   cmb_ajuste VARCHAR(50),
--   justificativa TEXT,
--   matricula VARCHAR(30),
--   dt_parcela_atraso DATE,
--   representacao VARCHAR(50),
--   status VARCHAR(20) NOT NULL,
--   tipo_parcelamento VARCHAR(20),
--   saldo_total DECIMAL(18,2),
--   created_at DATETIME,
--   updated_at DATETIME,
--   UNIQUE KEY uq_plans_numero (numero_plano),
--   KEY ix_plans_status (status),
--   KEY ix_plans_situacao_atual (situacao_atual)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS plan_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contexto TEXT NOT NULL,
  numero_plano TEXT,
  treatment_id INTEGER,
  etapa_numero INTEGER,
  etapa_nome TEXT,
  status TEXT NOT NULL,
  mensagem TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_plan_logs_contexto ON plan_logs(contexto);
CREATE INDEX IF NOT EXISTS ix_plan_logs_created_at ON plan_logs(created_at);