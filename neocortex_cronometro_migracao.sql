-- ============================================================
-- NEOCORTEX - migração do cronômetro opcional
--
-- COMO USAR: abra o SQL Editor do Supabase, COLE o comando abaixo (o conteúdo, não o nome do arquivo) e clique em Run.
-- Pode rodar de novo: é seguro.
--
-- tempo_execucao_s: segundos executados com o cronômetro, guardados na CONCLUSÃO da tarefa (base do bônus de pontos).
-- Fica na tarefa, e não nos eventos, porque a política de retenção apaga eventos com mais de 75 dias e os pontos não podem
-- diminuir com o tempo. NULL = tarefa que não foi cronometrada.
--
-- Sem esta migração o app NÃO quebra: o cronômetro funciona e só o bônus de pontos fica de fora.
-- ============================================================

ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS tempo_execucao_s INTEGER CHECK (tempo_execucao_s IS NULL OR tempo_execucao_s >= 0);
