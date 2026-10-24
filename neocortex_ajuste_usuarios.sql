-- ============================================================
-- Ajuste na tabela usuarios: alinhar faixa_etaria, ocupacao e
-- turno com o novo formulário de onboarding
--
-- ATENÇÃO — rode UMA vez, em banco SEM usuários.
-- Os valores antigos de faixa_etaria/ocupacao não são compatíveis com as novas
-- regras, e ocupacao é APAGADA (dá lugar a trabalha/estuda). Antes, este arquivo
-- fazia TRUNCATE usuarios CASCADE sem avisar; agora ele PARA com um erro se
-- houver qualquer usuário, em vez de apagar dados. Para limpar de propósito um
-- banco de teste, rode você mesmo:  TRUNCATE usuarios CASCADE;
-- ============================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM usuarios) THEN
        RAISE EXCEPTION
            'neocortex_ajuste_usuarios.sql abortado: a tabela usuarios tem dados. '
            'Este ajuste apaga a coluna ocupacao. Faça backup/migre os dados ou, se for só teste, rode TRUNCATE usuarios CASCADE;';
    END IF;
END $$;

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
