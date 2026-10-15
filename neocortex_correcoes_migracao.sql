-- ============================================================
-- NEOCORTEX — Migração de correções (índices + energia normalizada)
--
-- ADITIVA e IDEMPOTENTE: pode rodar quantas vezes quiser, em banco novo ou
-- em banco que já tem dados. Não apaga nada.
--
--   psql -d neocortex -f neocortex_correcoes_migracao.sql
--
-- 1. Índices para as consultas da agenda, do aprendizado e do motor de decisão.
--    (idx_tarefas_usuario_data, idx_tarefas_usuario_status e idx_compromissos_usuario
--    já existem nos outros arquivos de schema.)
-- 2. Tabela acoes_pendentes: guarda a ação que aguarda "confirma mesmo assim?"
--    (conflito de agenda), para o "sim" seguinte executá-la sem depender do modelo.
-- 3. A energia declarada passa a ser gravada sempre como manha | tarde | noite |
--    nao_sei. Valores antigos do cadastro ("Manhã", "Não sei") são convertidos,
--    senão decisao.py e aprendizado.py nunca reconheceriam o período.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Índices
-- ------------------------------------------------------------
-- tarefas abertas (recomendar_tarefa_agora, resolver_tmaterial de atraso)
CREATE INDEX IF NOT EXISTS idx_tarefas_abertas
    ON tarefas(id_usuario, data_fim)
    WHERE status IN ('pendente', 'em_andamento');

-- conclusões (periodo observado, métricas)
CREATE INDEX IF NOT EXISTS idx_tarefas_concluidas
    ON tarefas(id_usuario, concluido_em)
    WHERE status = 'concluida';

-- agenda: rotina, disponibilidade e restrições são lidas por dia da semana
CREATE INDEX IF NOT EXISTS idx_rotina_usuario_dia
    ON rotina_fixa(id_usuario, dia_semana);
CREATE INDEX IF NOT EXISTS idx_disponibilidades_usuario
    ON disponibilidades(id_usuario, dia_semana);
CREATE INDEX IF NOT EXISTS idx_restricoes_usuario
    ON restricoes(id_usuario, dia_semana);

-- decisões recentes (vincular sugestão à tarefa)
CREATE INDEX IF NOT EXISTS idx_decisoes_usuario
    ON decisoes(id_usuario, criado_em DESC);

-- histórico do chat (últimas mensagens por usuário e contexto)
CREATE INDEX IF NOT EXISTS idx_interacoes_usuario_contexto
    ON interacoes_chat(id_usuario, contexto, data_hora DESC);

-- planejamento, objetivos e dependências (db.enriquecer_tarefas)
CREATE INDEX IF NOT EXISTS idx_tarefa_planejamento_tarefa
    ON tarefa_planejamento(id_tarefa);
CREATE INDEX IF NOT EXISTS idx_tarefa_objetivos_objetivo
    ON tarefa_objetivos(id_objetivo);
CREATE INDEX IF NOT EXISTS idx_tarefa_dependencias_prerequisito
    ON tarefa_dependencias(id_tarefa_dependente);

-- ------------------------------------------------------------
-- 2. Ação pendente de confirmação (uma linha por usuário)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acoes_pendentes (
    id_usuario  INTEGER PRIMARY KEY REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    acoes       JSONB NOT NULL,
    criado_em   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 3. Energia declarada normalizada
-- ------------------------------------------------------------
UPDATE padroes_comportamentais
SET valor = CASE translate(lower(trim(valor)), 'ãÃ ', 'aa_')
                WHEN 'manha'   THEN 'manha'
                WHEN 'tarde'   THEN 'tarde'
                WHEN 'noite'   THEN 'noite'
                WHEN 'nao_sei' THEN 'nao_sei'
                ELSE valor
            END
WHERE tipo_padrao = 'energia'
  AND fonte = 'declarado';
