-- ============================================================
-- NEOCORTEX — Migração para o Assistente de IA
--
-- Por quê: interacoes_chat guardava só mensagens do usuário. Agora o assistente
-- também grava as respostas, e o histórico precisa saber quem escreveu cada
-- linha — senão o ai.py não reconstrói a conversa com os papéis certos
-- (user/model) para o Gemini.
--
-- ADITIVA e IDEMPOTENTE (pode rodar de novo sem erro). Linhas antigas recebem
-- 'usuario' por padrão, o que já é verdade para elas.
-- ============================================================

ALTER TABLE interacoes_chat
    ADD COLUMN IF NOT EXISTS autor TEXT NOT NULL DEFAULT 'usuario';

ALTER TABLE interacoes_chat
    DROP CONSTRAINT IF EXISTS interacoes_chat_autor_check;
ALTER TABLE interacoes_chat
    ADD CONSTRAINT interacoes_chat_autor_check
    CHECK (autor IN ('usuario', 'assistente'));
