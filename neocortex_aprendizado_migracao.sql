-- ============================================================
-- NEOCORTEX — Migração do núcleo de aprendizado
--
-- ADITIVA e IDEMPOTENTE: pode rodar várias vezes e roda por cima do
-- banco que já existe, sem apagar nenhum dado.
--
--   psql -d neocortex -f neocortex_aprendizado_migracao.sql
--
-- O que muda e por quê:
--
-- 1. eventos_execucao: passa a aceitar os eventos que o app realmente
--    gera (criou, reagendou, cancelou, desfez_conclusao) e ganha a
--    coluna "detalhe" (horário antigo/novo), necessária para comparar
--    PLANEJADO x REALIZADO e medir adiamentos.
--
-- 2. recomendacoes: ganha id_tarefa (qual tarefa foi recomendada) e
--    tipo. Sem isso, a reação do usuário (aceitou/recusou/adiou/
--    ignorou) não tem como ser ligada à recomendação que a originou.
--
-- 3. padroes_comportamentais: ganha fonte (declarado x observado),
--    confianca e evidencias. O que a pessoa DISSE (onboarding) fica
--    separado do que ela FAZ (calculado pelo sistema).
--
-- 4. memorias: ganha chave, origem, evidencias, ativa e atualizado_em.
--    Uma memória superada não é apagada: fica inativa (histórico
--    preservado) e a nova entra como ativa.
--
-- 5. metricas: índice único para o cálculo poder ser regravado sem
--    inflar a tabela a cada conclusão de tarefa.
-- ============================================================

-- ------------------------------------------------------------
-- 1. eventos_execucao
-- ------------------------------------------------------------
ALTER TABLE eventos_execucao
    DROP CONSTRAINT IF EXISTS eventos_execucao_tipo_evento_check;

ALTER TABLE eventos_execucao
    ADD CONSTRAINT eventos_execucao_tipo_evento_check
    CHECK (tipo_evento IN (
        'iniciou', 'pausou', 'retomou', 'concluiu', 'adiou',
        'criou', 'reagendou', 'cancelou', 'desfez_conclusao'
    ));

ALTER TABLE eventos_execucao ADD COLUMN IF NOT EXISTS detalhe JSONB;

CREATE INDEX IF NOT EXISTS idx_eventos_execucao_tarefa_data
    ON eventos_execucao(id_tarefa, data_hora);

-- ------------------------------------------------------------
-- 2. recomendacoes
-- ------------------------------------------------------------
ALTER TABLE recomendacoes
    ADD COLUMN IF NOT EXISTS id_tarefa INTEGER
        REFERENCES tarefas(id_tarefa) ON DELETE SET NULL;

ALTER TABLE recomendacoes
    ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'geral';

CREATE INDEX IF NOT EXISTS idx_recomendacoes_usuario
    ON recomendacoes(id_usuario, criado_em);
CREATE INDEX IF NOT EXISTS idx_recomendacoes_tarefa
    ON recomendacoes(id_tarefa);
CREATE INDEX IF NOT EXISTS idx_resultados_recomendacao
    ON resultados_recomendacoes(id_recomendacao);

-- ------------------------------------------------------------
-- 3. padroes_comportamentais
-- ------------------------------------------------------------
ALTER TABLE padroes_comportamentais
    ADD COLUMN IF NOT EXISTS fonte TEXT NOT NULL DEFAULT 'declarado';
ALTER TABLE padroes_comportamentais
    ADD COLUMN IF NOT EXISTS confianca TEXT;
ALTER TABLE padroes_comportamentais
    ADD COLUMN IF NOT EXISTS evidencias INTEGER;

-- Se a coluna "fonte" já existir sem valor padrão (ex.: criada por outra migração),
-- garante que todo padrão novo (como a energia declarada no onboarding) nasça 'declarado'.
UPDATE padroes_comportamentais SET fonte = 'declarado' WHERE fonte IS NULL;
ALTER TABLE padroes_comportamentais ALTER COLUMN fonte SET DEFAULT 'declarado';
ALTER TABLE padroes_comportamentais ALTER COLUMN fonte SET NOT NULL;

ALTER TABLE padroes_comportamentais
    DROP CONSTRAINT IF EXISTS padroes_comportamentais_fonte_check;
ALTER TABLE padroes_comportamentais
    ADD CONSTRAINT padroes_comportamentais_fonte_check
    CHECK (fonte IN ('declarado', 'observado'));

ALTER TABLE padroes_comportamentais
    DROP CONSTRAINT IF EXISTS padroes_comportamentais_confianca_check;
ALTER TABLE padroes_comportamentais
    ADD CONSTRAINT padroes_comportamentais_confianca_check
    CHECK (confianca IS NULL OR confianca IN ('baixa', 'media', 'alta'));

CREATE INDEX IF NOT EXISTS idx_padroes_usuario_tipo
    ON padroes_comportamentais(id_usuario, tipo_padrao);

-- ------------------------------------------------------------
-- 4. memorias
-- ------------------------------------------------------------
ALTER TABLE memorias ADD COLUMN IF NOT EXISTS chave TEXT;
ALTER TABLE memorias ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'declarado';
ALTER TABLE memorias ADD COLUMN IF NOT EXISTS evidencias INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memorias ADD COLUMN IF NOT EXISTS ativa BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE memorias
    ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- no máximo UMA memória ativa por (usuário, chave); as superadas ficam inativas
CREATE UNIQUE INDEX IF NOT EXISTS uq_memorias_chave_ativa
    ON memorias(id_usuario, chave)
    WHERE ativa AND chave IS NOT NULL;

-- ------------------------------------------------------------
-- 5. metricas
-- ------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_metricas_usuario_nome_periodo
    ON metricas(id_usuario, nome_metrica, periodo_referencia);

-- ------------------------------------------------------------
-- 6. tarefas (consultas de status/período usadas pelo aprendizado)
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_tarefas_usuario_status
    ON tarefas(id_usuario, status);
