-- ============================================================
-- NEOCORTEX — Tabelas novas (adicionadas por cima do schema
-- original já existente no banco). NÃO recria as 6 tabelas
-- originais — elas já existem e continuam intactas.
-- ============================================================

-- ------------------------------------------------------------
-- 7. COMPROMISSOS
-- ------------------------------------------------------------
CREATE TABLE compromissos (
 id_compromisso SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 titulo TEXT NOT NULL,
 tipo TEXT CHECK (tipo IN ('aula','consulta','reuniao','evento','outro')),
 data_inicio TIMESTAMP NOT NULL,
 data_fim TIMESTAMP NOT NULL,
 local TEXT,
 criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK (data_fim > data_inicio)
);

-- ------------------------------------------------------------
-- 8. OBJETIVOS
-- ------------------------------------------------------------
CREATE TABLE objetivos (
 id_objetivo SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 titulo TEXT NOT NULL,
 descricao TEXT,
 prazo TIMESTAMP,
 status TEXT NOT NULL DEFAULT 'em_andamento'
 CHECK (status IN ('em_andamento','concluido','pausado','cancelado')),
 criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 9. HABITOS
-- ------------------------------------------------------------
CREATE TABLE habitos (
 id_habito SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 nome TEXT NOT NULL,
 frequencia_desejada TEXT,
 criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 10. PREFERENCIAS
-- ------------------------------------------------------------
CREATE TABLE preferencias (
 id_preferencia SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 chave TEXT NOT NULL,
 valor TEXT NOT NULL,
 UNIQUE (id_usuario, chave)
);

-- ------------------------------------------------------------
-- 11. DISPONIBILIDADES
-- ------------------------------------------------------------
CREATE TABLE disponibilidades (
 id_disponibilidade SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 dia_semana TEXT NOT NULL CHECK (dia_semana IN
 ('segunda','terca','quarta','quinta','sexta','sabado','domingo')),
 hora_inicio TEXT NOT NULL,
 hora_fim TEXT NOT NULL,
 disponivel BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------
-- 12. EVENTOS_EXECUCAO
-- ------------------------------------------------------------
CREATE TABLE eventos_execucao (
 id_evento SERIAL PRIMARY KEY,
 id_tarefa INTEGER NOT NULL REFERENCES tarefas(id_tarefa) ON DELETE CASCADE,
 tipo_evento TEXT NOT NULL CHECK (tipo_evento IN ('iniciou','pausou','retomou','concluiu','adiou')),
 data_hora TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 13. METRICAS
-- ------------------------------------------------------------
CREATE TABLE metricas (
 id_metrica SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 nome_metrica TEXT NOT NULL,
 valor NUMERIC(10,2) NOT NULL,
 periodo_referencia TEXT,
 calculado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 14. MEMORIAS
-- ------------------------------------------------------------
CREATE TABLE memorias (
 id_memoria SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 conteudo TEXT NOT NULL,
 confianca TEXT CHECK (confianca IN ('baixa','media','alta')),
 criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 15. RESTRICOES
-- ------------------------------------------------------------
CREATE TABLE restricoes (
 id_restricao SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 descricao TEXT NOT NULL,
 dia_semana TEXT CHECK (dia_semana IN
 ('segunda','terca','quarta','quinta','sexta','sabado','domingo')),
 hora_inicio TEXT,
 hora_fim TEXT
);

-- ------------------------------------------------------------
-- 16. DECISOES
-- ------------------------------------------------------------
CREATE TABLE decisoes (
 id_decisao SERIAL PRIMARY KEY,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 contexto TEXT,
 criterios_usados TEXT,
 decisao_tomada TEXT NOT NULL,
 criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 17. RECOMENDACOES
-- ------------------------------------------------------------
CREATE TABLE recomendacoes (
 id_recomendacao SERIAL PRIMARY KEY,
 id_decisao INTEGER REFERENCES decisoes(id_decisao) ON DELETE SET NULL,
 id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
 conteudo TEXT NOT NULL,
 criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 18. RESULTADOS_RECOMENDACOES
-- ------------------------------------------------------------
CREATE TABLE resultados_recomendacoes (
 id_resultado SERIAL PRIMARY KEY,
 id_recomendacao INTEGER NOT NULL REFERENCES recomendacoes(id_recomendacao) ON DELETE CASCADE,
 acao_usuario TEXT CHECK (acao_usuario IN ('aceitou','recusou','ignorou','adiou')),
 resultado TEXT,
 registrado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 19. TAREFA_PLANEJAMENTO
-- ------------------------------------------------------------
CREATE TABLE tarefa_planejamento (
 id_planejamento SERIAL PRIMARY KEY,
 id_tarefa INTEGER NOT NULL REFERENCES tarefas(id_tarefa) ON DELETE CASCADE,
 duracao_estimada_min INTEGER,
 prioridade TEXT CHECK (prioridade IN ('baixa','media','alta')),
 esforco TEXT CHECK (esforco IN ('baixo','medio','alto'))
);

-- ------------------------------------------------------------
-- 20. TAREFA_OBJETIVOS (associação N:N)
-- ------------------------------------------------------------
CREATE TABLE tarefa_objetivos (
 id_tarefa INTEGER NOT NULL REFERENCES tarefas(id_tarefa) ON DELETE CASCADE,
 id_objetivo INTEGER NOT NULL REFERENCES objetivos(id_objetivo) ON DELETE CASCADE,
 PRIMARY KEY (id_tarefa, id_objetivo)
);

-- ------------------------------------------------------------
-- 21. TAREFA_DEPENDENCIAS (auto-relacionamento N:N)
-- ------------------------------------------------------------
CREATE TABLE tarefa_dependencias (
 id_tarefa INTEGER NOT NULL REFERENCES tarefas(id_tarefa) ON DELETE CASCADE,
 id_tarefa_dependente INTEGER NOT NULL REFERENCES tarefas(id_tarefa) ON DELETE CASCADE,
 PRIMARY KEY (id_tarefa, id_tarefa_dependente),
 CHECK (id_tarefa <> id_tarefa_dependente)
);

-- ------------------------------------------------------------
-- Índices das tabelas novas
-- ------------------------------------------------------------
CREATE INDEX idx_compromissos_usuario ON compromissos(id_usuario, data_inicio);
CREATE INDEX idx_objetivos_usuario ON objetivos(id_usuario);
CREATE INDEX idx_eventos_execucao_tarefa ON eventos_execucao(id_tarefa);
CREATE INDEX idx_metricas_usuario ON metricas(id_usuario);
CREATE INDEX idx_memorias_usuario ON memorias(id_usuario);
