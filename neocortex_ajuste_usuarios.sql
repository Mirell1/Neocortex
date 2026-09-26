-- ============================================================
-- Ajuste na tabela usuarios: alinhar faixa_etaria, ocupacao e
-- turno com o novo formulário de onboarding
-- ============================================================

-- AVISO: isso apaga as contas de teste existentes, porque os
-- valores antigos de faixa_etaria/ocupacao não são compatíveis
-- com as novas regras (CHECK constraints não aceitam dado velho
-- que não bate com a regra nova). Como são só contas de teste
-- no banco local, isso não é um problema real.
TRUNCATE usuarios CASCADE;

-- Nova faixa etária (bate com as opções do onboarding,
-- já sem a faixa 14-17 removida por decisão de LGPD)
ALTER TABLE usuarios DROP CONSTRAINT usuarios_faixa_etaria_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_faixa_etaria_check
    CHECK (faixa_etaria IN ('18-24','25-34','35-44','45+'));

-- Ocupação deixa de ser um valor único; trabalha e estuda
-- passam a ser independentes (dá pra ser os dois ao mesmo tempo)
ALTER TABLE usuarios DROP CONSTRAINT usuarios_ocupacao_check;
ALTER TABLE usuarios DROP COLUMN ocupacao;
ALTER TABLE usuarios ADD COLUMN trabalha BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN estuda BOOLEAN NOT NULL DEFAULT FALSE;

-- Turno ganha o valor "intermediario", que já existia no
-- onboarding mas não estava previsto no banco
ALTER TABLE usuarios DROP CONSTRAINT usuarios_turno_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_turno_check
    CHECK (turno IN ('manha','tarde','noite','intermediario','personalizado'));
