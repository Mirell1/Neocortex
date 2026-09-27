-- ============================================================
-- NEOCORTEX — Migração para o Assistente de IA
--
-- Por quê: interacoes_chat guardava só mensagens do usuário (a rota
-- do assistente nunca chamava uma IA de verdade). Agora que ela
-- passa a gerar e salvar respostas também, o histórico precisa saber
-- quem escreveu cada linha — senão o ai.py não consegue reconstruir
-- a conversa com os papéis certos (user/model) pro Gemini.
--
-- É uma migração aditiva: roda por cima do banco que já existe,
-- não recria nem apaga nada. Linhas antigas recebem 'usuario' por
-- padrão (o que já é verdade pra elas).
-- ============================================================

ALTER TABLE interacoes_chat
    ADD COLUMN autor TEXT NOT NULL DEFAULT 'usuario'
    CHECK (autor IN ('usuario', 'assistente'));
