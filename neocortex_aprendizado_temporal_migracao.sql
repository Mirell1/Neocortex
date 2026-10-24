-- Aditiva; executar depois das migrações de aprendizado e cronômetro.
CREATE TABLE IF NOT EXISTS estado_aprendizado (
    id_usuario INTEGER PRIMARY KEY REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    versao TEXT NOT NULL,
    calculado_em TIMESTAMP NOT NULL,
    valido_ate TIMESTAMP NOT NULL,
    detalhes JSONB NOT NULL,
    CHECK (valido_ate > calculado_em)
);
CREATE INDEX IF NOT EXISTS idx_tarefas_usuario_conclusao
    ON tarefas(id_usuario, concluido_em) WHERE status = 'concluida';
CREATE INDEX IF NOT EXISTS idx_tarefas_usuario_fim
    ON tarefas(id_usuario, data_fim);
