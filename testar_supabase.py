"""
NEOCORTEX — Teste de fumaça no Supabase

Coloque este arquivo na MESMA pasta do db.py e rode:

    python testar_supabase.py

O que ele faz:
  1. Conecta usando o seu .env (o mesmo caminho que o app usa).
  2. Confere fuso horário e quantidade de tabelas.
  3. Roda um mini-fluxo REAL com as funções do db.py: cria um usuário de
     teste, uma tarefa, conclui, grava chat, memória, métrica e ação pendente.
  4. APAGA tudo que criou no final (o usuário de teste é removido e o
     ON DELETE CASCADE leva junto os dados dele).

Não altera nenhum arquivo do projeto.
"""

import sys
from datetime import datetime, timedelta

import psycopg2


def dica_para_erro_de_conexao(erro):
    """Traduz os erros mais comuns de conexão no Supabase."""
    texto = str(erro)
    if ("could not translate host name" in texto
            or "Network is unreachable" in texto
            or "Cannot assign requested address" in texto
            or "No route to host" in texto):
        return ("O DB_HOST parece ser a conexão DIRETA (db.xxxx.supabase.co), que usa IPv6 "
                "e muitas redes só têm IPv4. Use o host do Session pooler "
                "(aws-...pooler.supabase.com) e a porta 5432.")
    if "Tenant or user not found" in texto:
        return ("Com o pooler, o DB_USER precisa ser 'postgres.' + o ID do projeto "
                "(ex.: postgres.abcdefghijklmnop), e não só 'postgres'.")
    if "password authentication failed" in texto:
        return ("Senha incorreta. Confira o DB_PASSWORD (é a senha do BANCO que você criou "
                "com o projeto; dá para redefinir em Project Settings > Database).")
    if "timeout" in texto.lower() or "timed out" in texto.lower():
        return "Tempo esgotado: confira DB_HOST/DB_PORT e se a internet está funcionando."
    return None


# ------------------------------------------------------------
# 1. Conexão (o db.py abre o pool assim que é importado)
# ------------------------------------------------------------
print("=" * 60)
print("NEOCORTEX - teste do banco no Supabase")
print("=" * 60)

try:
    import db
except psycopg2.OperationalError as erro:
    print("[ERRO] Não consegui conectar ao banco.\n")
    print(str(erro).strip())
    dica = dica_para_erro_de_conexao(erro)
    if dica:
        print("\nDICA:", dica)
    sys.exit(1)

resultados = []   # (ok, descricao)


def passo(ok, descricao, detalhe=""):
    resultados.append(ok)
    marca = "[OK]  " if ok else "[ERRO]"
    print(f"{marca} {descricao}" + (f"  ->  {detalhe}" if detalhe else ""))


cfg = db.CONFIG_BANCO
passo(True, "Conexão aberta", f"host={cfg['host']}  porta={cfg['port']}  usuário={cfg['user']}")

# ------------------------------------------------------------
# 2. Fuso horário, SSL e tabelas
# ------------------------------------------------------------
with db.conectar() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version() AS v")
        print("       Servidor:", cur.fetchone()["v"].split(",")[0])

        cur.execute("SHOW timezone")
        fuso = cur.fetchone()["TimeZone"]
        passo(fuso == "America/Sao_Paulo", "Fuso horário da conexão do app",
              f"{fuso}" + ("" if fuso == "America/Sao_Paulo"
                           else "  (esperado America/Sao_Paulo: rode o PASSO 0 do .sql e reinicie o app)"))

        try:
            cur.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            linha = cur.fetchone()
            if linha is not None:
                passo(bool(linha["ssl"]), "Conexão criptografada (SSL)")
        except psycopg2.Error:
            conn.rollback()

        cur.execute("""SELECT count(*) AS n FROM information_schema.tables
                       WHERE table_schema = 'public' AND table_type = 'BASE TABLE'""")
        n = cur.fetchone()["n"]
        passo(n == 23, "Tabelas no schema public", f"{n} (esperado 23)")

# ------------------------------------------------------------
# 3. Mini-fluxo real com as funções do db.py
# ------------------------------------------------------------
id_usuario = None
try:
    email = f"teste_supabase_{datetime.now():%Y%m%d%H%M%S}@neocortex.invalid"
    id_usuario = db.cadastrar_usuario(
        "Teste Supabase", email, "senha-de-teste-123",
        "18-24", True, False, "manha",
    )
    passo(isinstance(id_usuario, int), "Cadastro de usuário (INSERT + RETURNING)", f"id_usuario={id_usuario}")

    passo(db.verificar_login(email, "senha-de-teste-123") is not None,
          "Login com bcrypt")

    inicio = datetime.now() + timedelta(hours=1)
    id_tarefa = db.criar_tarefa(id_usuario, "Tarefa de teste", inicio, inicio + timedelta(hours=1),
                                categoria="estudo")
    passo(isinstance(id_tarefa, int), "Criar tarefa (grava também o evento 'criou')", f"id_tarefa={id_tarefa}")

    db.marcar_tarefa_concluida(id_tarefa, id_usuario)
    tarefa = db.buscar_tarefa(id_tarefa, id_usuario)
    passo(tarefa["status"] == "concluida", "Concluir tarefa", f"status={tarefa['status']}")

    # O teste mais importante do fuso: o relógio do banco (concluido_em) tem que
    # bater com o relógio do Python (datetime.now) usado pelo restante do app.
    diferenca = abs((tarefa["concluido_em"] - datetime.now()).total_seconds())
    passo(diferenca < 300, "Relógio do banco = relógio do app",
          f"diferença de {diferenca / 3600:.1f} h" + ("" if diferenca < 300 else
          "  (o fuso do banco e o do seu computador não batem)"))

    eventos = {e["tipo_evento"] for e in db.listar_eventos_execucao(id_tarefa, id_usuario)}
    passo({"criou", "concluiu"} <= eventos, "Histórico de eventos (JSONB incluso)", ", ".join(sorted(eventos)))

    db.registrar_interacao(id_usuario, "Olá do teste", autor="assistente")
    chat = db.listar_interacoes(id_usuario)
    passo(len(chat) == 1 and chat[0]["autor"] == "assistente", "Chat com coluna 'autor'")

    db.salvar_acoes_pendentes(id_usuario, [{"acao": "criar_tarefa", "titulo": "ação de teste"}])
    pend = db.buscar_acoes_pendentes(id_usuario)
    passo(pend is not None and pend[0]["acao"] == "criar_tarefa", "Ação pendente (coluna JSONB)")

    r1 = db.substituir_memoria(id_usuario, "chave_teste", "valor A", "media", 1)
    r2 = db.substituir_memoria(id_usuario, "chave_teste", "valor B", "alta", 2)
    ativas = db.listar_memorias_ativas(id_usuario)
    passo((r1, r2) == ("criada", "substituida") and len(ativas) == 1,
          "Memória: 1 ativa por chave (índice único parcial)", f"{r1} -> {r2}")

    m1 = db.salvar_metrica_unica(id_usuario, "metrica_teste", 1.5, "2026-W41")
    m2 = db.salvar_metrica_unica(id_usuario, "metrica_teste", 2.5, "2026-W41")
    passo(m1 == m2, "Métrica regravada sem duplicar (ON CONFLICT)")

    try:
        db.criar_tarefa(id_usuario, "Inválida", inicio, inicio - timedelta(hours=1))
        passo(False, "Regra CHECK data_fim > data_inicio", "o banco ACEITOU uma tarefa inválida")
    except psycopg2.errors.CheckViolation:
        passo(True, "Regra CHECK data_fim > data_inicio bloqueia dado inválido")

except Exception as erro:
    passo(False, "Fluxo de teste interrompido por erro", f"{type(erro).__name__}: {erro}")

finally:
    # ----------------------------------------------------------
    # 4. Limpeza: remove o usuário de teste (CASCADE apaga o resto)
    # ----------------------------------------------------------
    if id_usuario is not None:
        try:
            db.excluir_usuario(id_usuario)
            sobrou = db.buscar_usuario(id_usuario)
            passo(sobrou is None, "Limpeza: usuário de teste e dados apagados")
        except Exception as erro:
            passo(False, "Limpeza do usuário de teste falhou", f"{type(erro).__name__}: {erro}")
            print(f"       Apague manualmente no SQL Editor:  DELETE FROM usuarios WHERE id_usuario = {id_usuario};")

print("=" * 60)
falhas = resultados.count(False)
if falhas == 0:
    print(f"TUDO CERTO: {len(resultados)} verificações passaram.")
else:
    print(f"ATENÇÃO: {falhas} de {len(resultados)} verificações falharam (veja os [ERRO] acima).")
print("=" * 60)
sys.exit(1 if falhas else 0)
