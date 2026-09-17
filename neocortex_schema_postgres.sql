-- ============================================================
-- NEOCORTEX — Schema do Banco de Dados (PostgreSQL)
-- Convertido a partir da versão SQLite.
--
-- Principais diferenças pro SQLite:
--   - SQLite "INTEGER PRIMARY KEY AUTOINCREMENT" vira SERIAL
--     (o Postgres cria uma sequência própria pra gerar os ids)
--   - SQLite "DATETIME" vira TIMESTAMP
--   - Foreign keys são sempre aplicadas por padrão no Postgres
--     (no SQLite precisava do PRAGMA foreign_keys = ON)
-- ============================================================

-- ------------------------------------------------------------
-- 1. USUARIOS
-- ------------------------------------------------------------
CREATE TABLE usuarios (
    id_usuario      SERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    senha_hash      TEXT NOT NULL,
    faixa_etaria    TEXT NOT NULL CHECK (faixa_etaria IN ('14-18','18-30','30-50+')),
    ocupacao        TEXT NOT NULL CHECK (ocupacao IN ('trabalha','estuda','nenhum')),
    turno           TEXT CHECK (turno IN ('manha','tarde','noite','personalizado')),
    data_cadastro   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 2. HOBBIES (catálogo) + USUARIO_HOBBIES (associação N:N)
-- ------------------------------------------------------------
CREATE TABLE hobbies (
    id_hobby        SERIAL PRIMARY KEY,
    nome            TEXT NOT NULL UNIQUE
);

CREATE TABLE usuario_hobbies (
    id_usuario      INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    id_hobby        INTEGER NOT NULL REFERENCES hobbies(id_hobby) ON DELETE CASCADE,
    PRIMARY KEY (id_usuario, id_hobby)
);

-- ------------------------------------------------------------
-- 3. TAREFAS
-- ------------------------------------------------------------
CREATE TABLE tarefas (
    id_tarefa       SERIAL PRIMARY KEY,
    id_usuario      INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    categoria       TEXT CHECK (categoria IN ('trabalho','estudo','hobby','pessoal','saude','outro')),
    data_inicio     TIMESTAMP NOT NULL,
    data_fim        TIMESTAMP NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente','em_andamento','concluida','cancelada')),
    cor             TEXT,
    origem          TEXT NOT NULL DEFAULT 'manual'
                        CHECK (origem IN ('manual','ia_sugestao','chat_inicial')),
    criado_em       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    concluido_em    TIMESTAMP,  -- preenchido só quando o usuário marca como concluída;
                                 -- fica NULL até lá. É o que alimenta o dashboard de produtividade.
    CHECK (data_fim > data_inicio)
);

-- ------------------------------------------------------------
-- 4. ROTINA_FIXA
-- ------------------------------------------------------------
CREATE TABLE rotina_fixa (
    id_rotina       SERIAL PRIMARY KEY,
    id_usuario      INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    dia_semana      TEXT NOT NULL CHECK (dia_semana IN
                        ('segunda','terca','quarta','quinta','sexta','sabado','domingo')),
    descricao       TEXT NOT NULL,
    hora_inicio     TEXT NOT NULL,
    hora_fim        TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 5. INTERACOES_CHAT
-- ------------------------------------------------------------
CREATE TABLE interacoes_chat (
    id_interacao    SERIAL PRIMARY KEY,
    id_usuario      INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('texto','voz')),
    conteudo        TEXT NOT NULL,
    contexto        TEXT NOT NULL DEFAULT 'interacao_geral'
                        CHECK (contexto IN ('cadastro_inicial','interacao_geral')),
    data_hora       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 6. PADROES_COMPORTAMENTAIS
-- ------------------------------------------------------------
CREATE TABLE padroes_comportamentais (
    id_padrao       SERIAL PRIMARY KEY,
    id_usuario      INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    tipo_padrao     TEXT NOT NULL,
    valor           TEXT NOT NULL,
    calculado_em    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Índices
-- ------------------------------------------------------------
CREATE INDEX idx_tarefas_usuario_data ON tarefas(id_usuario, data_inicio);
CREATE INDEX idx_rotina_usuario ON rotina_fixa(id_usuario);
CREATE INDEX idx_interacoes_usuario ON interacoes_chat(id_usuario);