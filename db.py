"""
NEOCORTEX — Backend completo (PostgreSQL)

Camada responsável exclusivamente pelo acesso ao PostgreSQL.

Princípios:
- Reutilizar conexões por meio de pool.
- Usar parâmetros do psycopg2 em todas as consultas.
- Manter o isolamento por id_usuario nas operações relacionadas ao usuário.
- Preservar as funções já usadas pelo app.py.
- Separar estado atual, histórico, métricas, memória, decisões e resultados.
- Deixar as funções de consulta prontas para serem usadas pelo ai.py.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

import bcrypt
import psycopg2
import psycopg2.extras
from psycopg2.extras import Json
from dotenv import load_dotenv
from psycopg2 import pool


# ============================================================
# CONFIGURAÇÃO
# ============================================================

CONFIG_BANCO = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "neocortex"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

CONFIG_BANCO = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "neocortex"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}

def _inteiro_do_ambiente(nome, padrao):
    try:
        return max(1, int(os.getenv(nome, padrao)))
    except ValueError:
        return padrao


# ThreadedConnectionPool: o Flask atende cada requisição em uma thread, e o
# SimpleConnectionPool NÃO é seguro para isso. O teto é ajustável no .env
# (DB_POOL_MAX); acima dele, getconn() levanta PoolError.
POOL_CONEXOES = pool.ThreadedConnectionPool(
    1,
    _inteiro_do_ambiente("DB_POOL_MAX", 20),
    **CONFIG_BANCO,
    cursor_factory=psycopg2.extras.RealDictCursor,
    client_encoding="UTF8",
)


# ============================================================
# CONEXÃO
# ============================================================

@contextmanager
def conectar():
    """
    Pega uma conexão do pool e a devolve ao final da operação.

    Commit automático quando tudo termina corretamente.
    Rollback automático quando ocorre qualquer erro.
    """
    conn = POOL_CONEXOES.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        POOL_CONEXOES.putconn(conn, close=bool(conn.closed))


def criar_tabelas():
    """
    Cria o banco COMPLETO a partir do zero (banco novo e vazio).

    Executa, nesta ordem, o schema original e todas as migrações. Antes,
    só os dois primeiros arquivos rodavam, e um banco novo ficava com o
    schema antigo (sem usuarios.trabalha/estuda e sem interacoes_chat.autor),
    o que quebrava o cadastro e o chat.

    ATENÇÃO: o ajuste de usuários faz TRUNCATE em usuarios. Aqui isso é
    inofensivo porque a função só funciona em banco vazio (o primeiro
    CREATE TABLE já falha se as tabelas existirem). Em um banco que já
    tem dados, rode APENAS neocortex_aprendizado_migracao.sql (idempotente).
    """
    arquivos_schema = (
        BASE_DIR / "neocortex_schema_postgres.sql",
        BASE_DIR / "neocortex_novas_tabelas.sql",
        BASE_DIR / "neocortex_ajuste_usuarios.sql",
        BASE_DIR / "neocortex_ia_migracao.sql",
        BASE_DIR / "neocortex_aprendizado_migracao.sql",
        BASE_DIR / "neocortex_correcoes_migracao.sql",
    )

    with conectar() as conn:
        with conn.cursor() as cur:
            for caminho_schema in arquivos_schema:
                with caminho_schema.open("r", encoding="utf-8") as arquivo:
                    cur.execute(arquivo.read())


# ============================================================
# 1. USUÁRIOS / LOGIN
# ============================================================

def cadastrar_usuario(nome, email, senha, faixa_etaria, trabalha, estuda, turno=None, senha_hash=None):
    """
    Cadastra um usuário e retorna o id criado.

    Use 'senha' (texto) OU 'senha_hash' (bcrypt já calculado). O cadastro em
    várias telas guarda só o hash na sessão, nunca a senha em texto.
    """
    if senha_hash is None:
        senha_hash = bcrypt.hashpw(
            senha.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

    with conectar() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO usuarios
                        (nome, email, senha_hash, faixa_etaria, trabalha, estuda, turno)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_usuario
                    """,
                    (nome, email, senha_hash, faixa_etaria, trabalha, estuda, turno),
                )
                return cur.fetchone()["id_usuario"]
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise ValueError(
                    "Já existe um usuário cadastrado com esse e-mail."
                )


def verificar_login(email, senha):
    """Confere a senha e retorna os dados do usuário, ou None."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM usuarios WHERE email = %s",
                (email,),
            )
            linha = cur.fetchone()

    if linha is None:
        return None

    senha_correta = bcrypt.checkpw(
        senha.encode("utf-8"),
        linha["senha_hash"].encode("utf-8"),
    )
    return dict(linha) if senha_correta else None


def buscar_usuario(id_usuario):
    """Busca um usuário pelo id."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM usuarios WHERE id_usuario = %s",
                (id_usuario,),
            )
            linha = cur.fetchone()
    return dict(linha) if linha else None


COLUNAS_USUARIO_PERMITIDAS = {"nome"}


def atualizar_usuario(id_usuario, **campos):
    """Atualiza somente campos permitidos da tabela de usuários."""
    campos = {
        chave: valor
        for chave, valor in campos.items()
        if chave in COLUNAS_USUARIO_PERMITIDAS
    }
    if not campos:
        return 0

    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_usuario]

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE usuarios SET {colunas} WHERE id_usuario = %s",
                valores,
            )
            return cur.rowcount


def trocar_senha(id_usuario, nova_senha):
    """Gera novo hash e atualiza a senha do usuário."""
    novo_hash = bcrypt.hashpw(
        nova_senha.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE usuarios
                SET senha_hash = %s
                WHERE id_usuario = %s
                """,
                (novo_hash, id_usuario),
            )

def excluir_usuario(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
            return cur.rowcount

def email_existe(email):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM usuarios WHERE email = %s", (email,))
            return cur.fetchone() is not None

# ============================================================
# 2. HOBBIES
# ============================================================

def obter_ou_criar_hobby(nome):
    """Retorna o id do hobby, criando-o de forma atômica se necessário."""
    nome = nome.strip().lower()
    if not nome:
        raise ValueError("O nome do hobby não pode ser vazio.")

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hobbies (nome)
                VALUES (%s)
                ON CONFLICT (nome)
                DO UPDATE SET nome = EXCLUDED.nome
                RETURNING id_hobby
                """,
                (nome,),
            )
            return cur.fetchone()["id_hobby"]


def listar_hobbies_catalogo():
    """Lista o catálogo completo de hobbies."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hobbies ORDER BY nome"
            )
            linhas = cur.fetchall()
    return [dict(linha) for linha in linhas]


def associar_hobby(id_usuario, nome_hobby):
    """Associa um hobby existente ou recém-criado ao usuário."""
    id_hobby = obter_ou_criar_hobby(nome_hobby)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuario_hobbies (id_usuario, id_hobby)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (id_usuario, id_hobby),
            )


def remover_hobby(id_usuario, nome_hobby):
    """Remove a associação do hobby com o usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM usuario_hobbies
                WHERE id_usuario = %s
                  AND id_hobby = (
                      SELECT id_hobby
                      FROM hobbies
                      WHERE nome = %s
                  )
                """,
                (id_usuario, nome_hobby.strip().lower()),
            )


def listar_hobbies_usuario(id_usuario):
    """Lista os hobbies associados ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT h.id_hobby, h.nome
                FROM hobbies h
                JOIN usuario_hobbies uh
                  ON uh.id_hobby = h.id_hobby
                WHERE uh.id_usuario = %s
                ORDER BY h.nome
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()
    return [dict(linha) for linha in linhas]


# ============================================================
# 3. TAREFAS
# ============================================================

# Se a tarefa foi recomendada "para agora" (tipo 'tarefa_agora'), só conta
# como recomendação ACEITA se for concluída até N horas depois. Depois
# disso a conclusão provavelmente não tem relação com a recomendação.
JANELA_ACEITE_TAREFA_AGORA_H = 6


def _como_datetime(valor):
    """Aceita datetime ou texto ISO ('AAAA-MM-DDTHH:MM') e devolve datetime."""
    if valor is None or isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(str(valor))


def _registrar_evento(cur, id_tarefa, tipo_evento, detalhe=None):
    """Grava um evento de execução NA MESMA transação da mudança de estado."""
    cur.execute(
        """
        INSERT INTO eventos_execucao (id_tarefa, tipo_evento, detalhe)
        VALUES (%s, %s, %s)
        """,
        (id_tarefa, tipo_evento, Json(detalhe) if detalhe is not None else None),
    )


def _resolver_recomendacoes_da_tarefa(cur, id_tarefa, acao, resultado, so_se_recente=False):
    """
    Registra a REAÇÃO do usuário nas recomendações ainda sem resultado que
    apontam para esta tarefa (aceitou / recusou / adiou).

    Só mexe em recomendações sem resultado: uma reação já registrada nunca
    é sobrescrita por outra.
    """
    sql = """
        INSERT INTO resultados_recomendacoes (id_recomendacao, acao_usuario, resultado)
        SELECT r.id_recomendacao, %s, %s
        FROM recomendacoes r
        WHERE r.id_tarefa = %s
          AND NOT EXISTS (
              SELECT 1 FROM resultados_recomendacoes x
              WHERE x.id_recomendacao = r.id_recomendacao
          )
    """
    parametros = [acao, resultado, id_tarefa]
    if so_se_recente:
        sql += """
          AND (r.tipo <> 'tarefa_agora'
               OR LOCALTIMESTAMP - r.criado_em <= %s * INTERVAL '1 hour')
        """
        parametros.append(JANELA_ACEITE_TAREFA_AGORA_H)
    cur.execute(sql, parametros)

def apagar_eventos_antigos(dias=75):
    """[LGPD] Retenção automática: eventos_execucao não guarda histórico indefinido.
    75 dias fica no meio do intervalo (60-90) definido com o Matheus."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM eventos_execucao WHERE data_hora < NOW() - INTERVAL '%s days'",
                (dias,),
            )
            return cur.rowcount


def criar_tarefa(id_usuario, titulo, data_inicio, data_fim, categoria=None, descricao=None, origem="manual"):
    """Cria a tarefa e registra o evento 'criou' (mesma transação)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tarefas (id_usuario, titulo, data_inicio, data_fim, categoria, descricao, origem)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id_tarefa
                """,
                (id_usuario, titulo, data_inicio, data_fim, categoria, descricao, origem),
            )
            id_tarefa = cur.fetchone()["id_tarefa"]
            _registrar_evento(cur, id_tarefa, "criou", {"origem": origem})
            return id_tarefa


def listar_tarefas(id_usuario, status=None, data_inicio=None, data_fim=None, inicio_antes=None):
    """
    data_inicio: tarefas que COMEÇAM a partir de (>=).
    inicio_antes: tarefas que começam ANTES de (<) — com data_inicio, recorta um dia/mês.
    data_fim: tarefas que TERMINAM até (<=).
    """
    query = "SELECT * FROM tarefas WHERE id_usuario = %s"
    parametros = [id_usuario]
    if status:
        query += " AND status = %s"
        parametros.append(status)
    if data_inicio:
        query += " AND data_inicio >= %s"
        parametros.append(data_inicio)
    if inicio_antes:
        query += " AND data_inicio < %s"
        parametros.append(inicio_antes)
    if data_fim:
        query += " AND data_fim <= %s"
        parametros.append(data_fim)
    query += " ORDER BY data_inicio"

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


def listar_tarefas_janela(id_usuario, inicio, fim, status=None):
    """
    Tarefas que SOBREPÕEM a janela [inicio, fim) — é a semântica certa para
    "o que tenho hoje?". (listar_tarefas exige que a tarefa INTEIRA caiba
    entre as datas; com data_fim = '2026-10-01' ela compara com meia-noite
    e perde toda tarefa do próprio dia.)

    Sem 'status', canceladas ficam de fora.
    """
    query = """
        SELECT * FROM tarefas
        WHERE id_usuario = %s
          AND data_inicio < %s
          AND data_fim > %s
    """
    parametros = [id_usuario, fim, inicio]
    if status:
        query += " AND status = %s"
        parametros.append(status)
    else:
        query += " AND status <> 'cancelada'"
    query += " ORDER BY data_inicio"

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


def listar_tarefas_abertas(id_usuario, data_fim_minima=None, limite=200):
    """Tarefas pendentes/em andamento (opcionalmente com fim a partir de uma data)."""
    query = """
        SELECT * FROM tarefas
        WHERE id_usuario = %s AND status IN ('pendente', 'em_andamento')
    """
    parametros = [id_usuario]
    if data_fim_minima:
        query += " AND data_fim >= %s"
        parametros.append(data_fim_minima)
    query += " ORDER BY data_inicio LIMIT %s"
    parametros.append(limite)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


def buscar_tarefa(id_tarefa, id_usuario):
    """Busca uma tarefa garantindo que ela pertença ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM tarefas
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                """,
                (id_tarefa, id_usuario),
            )
            linha = cur.fetchone()
    return dict(linha) if linha else None


COLUNAS_TAREFA_PERMITIDAS = {
    "titulo",
    "descricao",
    "categoria",
    "data_inicio",
    "data_fim",
    "status",
    "cor",
}


def atualizar_tarefa(id_tarefa, id_usuario, **campos):
    """
    Atualiza somente campos permitidos de uma tarefa do usuário.

    Também alimenta o histórico (mesma transação):
      - horário mudou para DEPOIS  -> evento 'adiou'      (+ reação 'adiou')
      - horário mudou (outro caso) -> evento 'reagendou'
      - status virou 'cancelada'   -> evento 'cancelou'   (+ reação 'recusou')
    O evento guarda o horário antigo e o novo em "detalhe".
    """
    campos = {
        chave: valor
        for chave, valor in campos.items()
        if chave in COLUNAS_TAREFA_PERMITIDAS
    }
    if not campos:
        return 0

    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_tarefa, id_usuario]

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT data_inicio, data_fim, status
                FROM tarefas
                WHERE id_tarefa = %s AND id_usuario = %s
                FOR UPDATE
                """,
                (id_tarefa, id_usuario),
            )
            antes = cur.fetchone()
            if antes is None:
                return 0

            cur.execute(
                f"""
                UPDATE tarefas
                SET {colunas}
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                """,
                valores,
            )

            novo_inicio = _como_datetime(campos.get("data_inicio", antes["data_inicio"]))
            novo_fim = _como_datetime(campos.get("data_fim", antes["data_fim"]))
            if novo_inicio != antes["data_inicio"] or novo_fim != antes["data_fim"]:
                tipo = "adiou" if novo_inicio > antes["data_inicio"] else "reagendou"
                _registrar_evento(cur, id_tarefa, tipo, {
                    "de": {"inicio": antes["data_inicio"].isoformat(), "fim": antes["data_fim"].isoformat()},
                    "para": {"inicio": novo_inicio.isoformat(), "fim": novo_fim.isoformat()},
                })
                if tipo == "adiou":
                    _resolver_recomendacoes_da_tarefa(cur, id_tarefa, "adiou", "reagendada_para_depois")

            if campos.get("status") == "cancelada" and antes["status"] != "cancelada":
                _registrar_evento(cur, id_tarefa, "cancelou")
                _resolver_recomendacoes_da_tarefa(cur, id_tarefa, "recusou", "cancelada")

            return cur.rowcount


def cancelar_tarefa(id_tarefa, id_usuario):
    """Cancela (não apaga) a tarefa: o histórico dela continua servindo ao aprendizado."""
    return atualizar_tarefa(id_tarefa, id_usuario, status="cancelada")


def deletar_tarefa(id_tarefa, id_usuario):
    """
    Exclui somente uma tarefa pertencente ao usuário.

    Os eventos da tarefa somem junto (ON DELETE CASCADE), então a reação
    'recusou' é registrada ANTES de apagar: a recomendação e o resultado
    sobrevivem (recomendacoes.id_tarefa vira NULL).
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM tarefas WHERE id_tarefa = %s AND id_usuario = %s FOR UPDATE",
                (id_tarefa, id_usuario),
            )
            if cur.fetchone() is None:
                return 0
            _resolver_recomendacoes_da_tarefa(cur, id_tarefa, "recusou", "excluida")
            cur.execute(
                """
                DELETE FROM tarefas
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                """,
                (id_tarefa, id_usuario),
            )
            return cur.rowcount


def marcar_tarefa_concluida(id_tarefa, id_usuario):
    """
    Marca a tarefa como concluída e, na mesma transação, registra o evento
    'concluiu' e a reação 'aceitou' das recomendações ligadas a ela.

    Chamar de novo numa tarefa que já está concluída (duplo clique) não
    duplica evento nem altera concluido_em.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status FROM tarefas
                WHERE id_tarefa = %s AND id_usuario = %s
                FOR UPDATE
                """,
                (id_tarefa, id_usuario),
            )
            linha = cur.fetchone()
            if linha is None:
                return 0
            if linha["status"] == "concluida":
                return 1

            cur.execute(
                """
                UPDATE tarefas
                SET status = 'concluida',
                    concluido_em = CURRENT_TIMESTAMP
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                """,
                (id_tarefa, id_usuario),
            )
            _registrar_evento(cur, id_tarefa, "concluiu")
            _resolver_recomendacoes_da_tarefa(cur, id_tarefa, "aceitou", "concluida", so_se_recente=True)
            return 1


def desfazer_conclusao_tarefa(id_tarefa, id_usuario):
    """
    Volta a tarefa para pendente e remove a data de conclusão.

    Se ela estava concluída, registra 'desfez_conclusao' (o evento
    'concluiu' antigo não pode continuar valendo como conclusão real) e
    retira a reação 'aceitou' que a conclusão tinha gerado.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status FROM tarefas
                WHERE id_tarefa = %s AND id_usuario = %s
                FOR UPDATE
                """,
                (id_tarefa, id_usuario),
            )
            antes = cur.fetchone()
            if antes is None:
                return 0

            cur.execute(
                """
                UPDATE tarefas
                SET status = 'pendente',
                    concluido_em = NULL
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                """,
                (id_tarefa, id_usuario),
            )
            if antes["status"] == "concluida":
                _registrar_evento(cur, id_tarefa, "desfez_conclusao")
                cur.execute(
                    """
                    DELETE FROM resultados_recomendacoes
                    WHERE acao_usuario = 'aceitou'
                      AND resultado = 'concluida'
                      AND id_recomendacao IN (
                          SELECT id_recomendacao FROM recomendacoes WHERE id_tarefa = %s
                      )
                    """,
                    (id_tarefa,),
                )
            return 1


# ============================================================
# 4. ROTINA FIXA
# ============================================================

def adicionar_rotina(
    id_usuario,
    dia_semana,
    descricao,
    hora_inicio,
    hora_fim,
):
    """Adiciona uma atividade à rotina fixa."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rotina_fixa
                    (id_usuario, dia_semana, descricao, hora_inicio, hora_fim)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id_rotina
                """,
                (
                    id_usuario,
                    dia_semana,
                    descricao,
                    hora_inicio,
                    hora_fim,
                ),
            )
            return cur.fetchone()["id_rotina"]


def listar_rotina(id_usuario, dia_semana=None):
    """Lista a rotina fixa do usuário, podendo filtrar por dia."""
    query = "SELECT * FROM rotina_fixa WHERE id_usuario = %s"
    parametros = [id_usuario]

    if dia_semana:
        query += " AND dia_semana = %s"
        parametros.append(dia_semana)

    query += " ORDER BY dia_semana, hora_inicio"

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


COLUNAS_ROTINA_PERMITIDAS = {
    "dia_semana",
    "descricao",
    "hora_inicio",
    "hora_fim",
}


def atualizar_rotina(id_rotina, id_usuario, **campos):
    """Atualiza somente campos permitidos de uma rotina do usuário."""
    campos = {
        chave: valor
        for chave, valor in campos.items()
        if chave in COLUNAS_ROTINA_PERMITIDAS
    }
    if not campos:
        return 0

    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_rotina, id_usuario]

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE rotina_fixa
                SET {colunas}
                WHERE id_rotina = %s
                  AND id_usuario = %s
                """,
                valores,
            )
            return cur.rowcount


def deletar_rotina(id_rotina, id_usuario):
    """Exclui somente uma rotina pertencente ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rotina_fixa
                WHERE id_rotina = %s
                  AND id_usuario = %s
                """,
                (id_rotina, id_usuario),
            )
            return cur.rowcount


# ============================================================
# 5. INTERAÇÕES
# ============================================================

def registrar_interacao(
    id_usuario,
    conteudo,
    tipo="texto",
    contexto="interacao_geral",
    autor="usuario",
):
    """
    Registra uma mensagem/interação do usuário ou do assistente.

    autor: 'usuario' ou 'assistente' — necessário para o histórico do
    chat com IA saber quem escreveu cada mensagem (ver
    neocortex_ia_migracao.sql, que adiciona essa coluna).
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO interacoes_chat
                    (id_usuario, tipo, conteudo, contexto, autor)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id_interacao
                """,
                (id_usuario, tipo, conteudo, contexto, autor),
            )
            return cur.fetchone()["id_interacao"]


def listar_interacoes(id_usuario, contexto=None, limite=100):
    """Lista as interações mais recentes do usuário."""
    query = "SELECT * FROM interacoes_chat WHERE id_usuario = %s"
    parametros = [id_usuario]

    if contexto:
        query += " AND contexto = %s"
        parametros.append(contexto)

    query += " ORDER BY data_hora DESC, id_interacao DESC LIMIT %s"
    parametros.append(limite)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 6. PADRÕES COMPORTAMENTAIS
# ============================================================

def salvar_padrao(id_usuario, tipo_padrao, valor):
    """Cria ou atualiza um padrão comportamental do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_padrao
                FROM padroes_comportamentais
                WHERE id_usuario = %s
                  AND tipo_padrao = %s
                """,
                (id_usuario, tipo_padrao),
            )
            existente = cur.fetchone()

            if existente:
                cur.execute(
                    """
                    UPDATE padroes_comportamentais
                    SET valor = %s,
                        calculado_em = CURRENT_TIMESTAMP
                    WHERE id_padrao = %s
                    """,
                    (valor, existente["id_padrao"]),
                )
                return existente["id_padrao"]

            cur.execute(
                """
                INSERT INTO padroes_comportamentais
                    (id_usuario, tipo_padrao, valor)
                VALUES (%s, %s, %s)
                RETURNING id_padrao
                """,
                (id_usuario, tipo_padrao, valor),
            )
            return cur.fetchone()["id_padrao"]


def listar_padroes(id_usuario):
    """Lista os padrões comportamentais do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM padroes_comportamentais
                WHERE id_usuario = %s
                ORDER BY calculado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def obter_padrao(id_usuario, tipo_padrao):
    """Busca um padrão comportamental específico do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM padroes_comportamentais
                WHERE id_usuario = %s
                  AND tipo_padrao = %s
                """,
                (id_usuario, tipo_padrao),
            )
            linha = cur.fetchone()

    return dict(linha) if linha else None


def salvar_padrao_observado(id_usuario, tipo_padrao, valor, confianca, evidencias):
    """
    Cria ou atualiza um padrão OBSERVADO (calculado a partir do que o usuário
    fez), com confiança e quantidade de evidências. Fica separado do que o
    usuário declarou: os tipos observados têm nome próprio (ex.:
    'periodo_conclusao_observado' x 'energia', que é a declaração).
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_padrao FROM padroes_comportamentais
                WHERE id_usuario = %s AND tipo_padrao = %s
                """,
                (id_usuario, tipo_padrao),
            )
            existente = cur.fetchone()
            if existente:
                cur.execute(
                    """
                    UPDATE padroes_comportamentais
                    SET valor = %s, fonte = 'observado', confianca = %s,
                        evidencias = %s, calculado_em = CURRENT_TIMESTAMP
                    WHERE id_padrao = %s
                    """,
                    (valor, confianca, evidencias, existente["id_padrao"]),
                )
                return existente["id_padrao"]
            cur.execute(
                """
                INSERT INTO padroes_comportamentais
                    (id_usuario, tipo_padrao, valor, fonte, confianca, evidencias)
                VALUES (%s, %s, %s, 'observado', %s, %s)
                RETURNING id_padrao
                """,
                (id_usuario, tipo_padrao, valor, confianca, evidencias),
            )
            return cur.fetchone()["id_padrao"]


# ============================================================
# 7. COMPROMISSOS
# ============================================================

def listar_compromissos(id_usuario):
    """Lista os compromissos do usuário em ordem cronológica."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM compromissos
                WHERE id_usuario = %s
                ORDER BY data_inicio
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def listar_compromissos_janela(id_usuario, inicio, fim):
    """Compromissos que sobrepõem a janela [inicio, fim)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM compromissos
                WHERE id_usuario = %s
                  AND data_inicio < %s
                  AND data_fim > %s
                ORDER BY data_inicio
                """,
                (id_usuario, fim, inicio),
            )
            linhas = cur.fetchall()
    return [dict(linha) for linha in linhas]


def buscar_compromisso(id_compromisso, id_usuario):
    """Busca um compromisso garantindo que pertença ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM compromissos
                WHERE id_compromisso = %s
                  AND id_usuario = %s
                """,
                (id_compromisso, id_usuario),
            )
            linha = cur.fetchone()

    return dict(linha) if linha else None


def criar_compromisso(id_usuario, titulo, data_inicio, data_fim, tipo="outro", local=None):
    """Cria um compromisso pertencente ao usuário e retorna o id criado."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO compromissos
                    (id_usuario, titulo, tipo, data_inicio, data_fim, local)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id_compromisso
                """,
                (id_usuario, titulo, tipo, data_inicio, data_fim, local),
            )
            return cur.fetchone()["id_compromisso"]


# ============================================================
# 8. OBJETIVOS
# ============================================================

def listar_objetivos(id_usuario):
    """Lista os objetivos do usuário, dos mais recentes aos mais antigos."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM objetivos
                WHERE id_usuario = %s
                ORDER BY criado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def buscar_objetivo(id_objetivo, id_usuario):
    """Busca um objetivo garantindo que pertença ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM objetivos
                WHERE id_objetivo = %s
                  AND id_usuario = %s
                """,
                (id_objetivo, id_usuario),
            )
            linha = cur.fetchone()

    return dict(linha) if linha else None


def criar_objetivo(id_usuario, titulo, descricao=None, prazo=None):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO objetivos (id_usuario, titulo, descricao, prazo)
                VALUES (%s, %s, %s, %s)
                RETURNING id_objetivo
                """,
                (id_usuario, titulo, descricao, prazo),
            )
            return cur.fetchone()["id_objetivo"]


def atualizar_objetivo(id_objetivo, id_usuario, **campos):
    colunas_permitidas = {"titulo", "descricao", "prazo", "status"}
    campos = {k: v for k, v in campos.items() if k in colunas_permitidas}
    if not campos:
        return 0
    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_objetivo, id_usuario]
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE objetivos SET {colunas} WHERE id_objetivo = %s AND id_usuario = %s",
                valores,
            )
            return cur.rowcount


def excluir_objetivo(id_objetivo, id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM objetivos WHERE id_objetivo = %s AND id_usuario = %s",
                (id_objetivo, id_usuario),
            )
            return cur.rowcount

def criar_fragmento_objetivo(id_usuario, id_objetivo, titulo, data_inicio, data_fim):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM objetivos WHERE id_objetivo = %s AND id_usuario = %s",
                (id_objetivo, id_usuario),
            )
            if cur.fetchone() is None:
                return None
            cur.execute(
                """
                INSERT INTO tarefas (id_usuario, titulo, data_inicio, data_fim, origem)
                VALUES (%s, %s, %s, %s, 'manual')
                RETURNING id_tarefa
                """,
                (id_usuario, titulo, data_inicio, data_fim),
            )
            id_tarefa = cur.fetchone()["id_tarefa"]
            cur.execute(
                "INSERT INTO tarefa_objetivos (id_tarefa, id_objetivo) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (id_tarefa, id_objetivo),
            )
            return id_tarefa


def listar_fragmentos_objetivo(id_objetivo, id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.*
                FROM tarefas t
                JOIN tarefa_objetivos tobj ON tobj.id_tarefa = t.id_tarefa
                JOIN objetivos o ON o.id_objetivo = tobj.id_objetivo
                WHERE tobj.id_objetivo = %s AND o.id_usuario = %s AND t.id_usuario = %s
                ORDER BY t.data_inicio
                """,
                (id_objetivo, id_usuario, id_usuario),
            )
            return [dict(l) for l in cur.fetchall()]

# ============================================================
# 9. HÁBITOS
# ============================================================

def listar_habitos(id_usuario):
    """Lista os hábitos do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM habitos
                WHERE id_usuario = %s
                ORDER BY criado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def buscar_habito(id_habito, id_usuario):
    """Busca um hábito garantindo que pertença ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM habitos
                WHERE id_habito = %s
                  AND id_usuario = %s
                """,
                (id_habito, id_usuario),
            )
            linha = cur.fetchone()

    return dict(linha) if linha else None


# ============================================================
# 10. PREFERÊNCIAS
# ============================================================

def listar_preferencias(id_usuario):
    """Lista as preferências registradas para o usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM preferencias
                WHERE id_usuario = %s
                ORDER BY chave
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]

def salvar_preferencia(id_usuario, chave, valor):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO preferencias (id_usuario, chave, valor)
                VALUES (%s, %s, %s)
                ON CONFLICT (id_usuario, chave) DO UPDATE SET valor = EXCLUDED.valor
                """,
                (id_usuario, chave, valor),
            )


def buscar_preferencia(id_usuario, chave):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT valor FROM preferencias WHERE id_usuario = %s AND chave = %s",
                (id_usuario, chave),
            )
            linha = cur.fetchone()
    return linha["valor"] if linha else None


# ============================================================
# 11. DISPONIBILIDADES
# ============================================================

def listar_disponibilidades(id_usuario):
    """Lista os períodos de disponibilidade do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM disponibilidades
                WHERE id_usuario = %s
                ORDER BY dia_semana, hora_inicio
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 12. EVENTOS DE EXECUÇÃO
# ============================================================

def registrar_evento_execucao(id_tarefa, id_usuario, tipo_evento):
    """
    Registra um evento somente se a tarefa pertencer ao usuário.
    O id_usuario é usado para preservar o isolamento dos dados.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eventos_execucao (id_tarefa, tipo_evento)
                SELECT id_tarefa, %s
                FROM tarefas
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                RETURNING id_evento
                """,
                (tipo_evento, id_tarefa, id_usuario),
            )
            linha = cur.fetchone()

    if linha is None:
        return None

    return linha["id_evento"]


def listar_eventos_execucao(id_tarefa, id_usuario):
    """Lista eventos de uma tarefa pertencente ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.*
                FROM eventos_execucao e
                JOIN tarefas t
                  ON t.id_tarefa = e.id_tarefa
                WHERE e.id_tarefa = %s
                  AND t.id_usuario = %s
                ORDER BY e.data_hora DESC
                """,
                (id_tarefa, id_usuario),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def listar_eventos_usuario(id_usuario, desde=None):
    """Todos os eventos de execução das tarefas do usuário (insumo do aprendizado)."""
    query = """
        SELECT e.*, t.categoria
        FROM eventos_execucao e
        JOIN tarefas t ON t.id_tarefa = e.id_tarefa
        WHERE t.id_usuario = %s
    """
    parametros = [id_usuario]
    if desde:
        query += " AND e.data_hora >= %s"
        parametros.append(desde)
    query += " ORDER BY e.data_hora"
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()
    return [dict(linha) for linha in linhas]


# ============================================================
# 13. MÉTRICAS
# ============================================================

def salvar_metrica(id_usuario, nome_metrica, valor, periodo=None):
    """Salva uma nova medição e retorna o id da métrica."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metricas
                    (id_usuario, nome_metrica, valor, periodo_referencia)
                VALUES (%s, %s, %s, %s)
                RETURNING id_metrica
                """,
                (id_usuario, nome_metrica, valor, periodo),
            )
            return cur.fetchone()["id_metrica"]


def salvar_metrica_unica(id_usuario, nome_metrica, valor, periodo):
    """
    Grava/atualiza a métrica de (usuário, nome, período). Recalcular não
    cria uma linha nova a cada conclusão de tarefa (ver índice único em
    neocortex_aprendizado_migracao.sql).
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metricas (id_usuario, nome_metrica, valor, periodo_referencia)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id_usuario, nome_metrica, periodo_referencia)
                DO UPDATE SET valor = EXCLUDED.valor, calculado_em = CURRENT_TIMESTAMP
                RETURNING id_metrica
                """,
                (id_usuario, nome_metrica, valor, periodo),
            )
            return cur.fetchone()["id_metrica"]


def listar_metricas(id_usuario):
    """Lista as métricas do usuário das mais recentes às mais antigas."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM metricas
                WHERE id_usuario = %s
                ORDER BY calculado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def atualizar_metrica(id_metrica, id_usuario, valor):
    """Atualiza uma métrica somente se ela pertencer ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE metricas
                SET valor = %s,
                    calculado_em = CURRENT_TIMESTAMP
                WHERE id_metrica = %s
                  AND id_usuario = %s
                """,
                (valor, id_metrica, id_usuario),
            )
            return cur.rowcount


# ============================================================
# 14. MEMÓRIAS
# ============================================================

def salvar_memoria(id_usuario, conteudo, confianca="media"):
    """Cria uma memória e retorna o id criado."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memorias
                    (id_usuario, conteudo, confianca)
                VALUES (%s, %s, %s)
                RETURNING id_memoria
                """,
                (id_usuario, conteudo, confianca),
            )
            return cur.fetchone()["id_memoria"]


def listar_memorias(id_usuario):
    """Lista memórias do usuário das mais recentes às mais antigas."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM memorias
                WHERE id_usuario = %s
                ORDER BY criado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def listar_memorias_ativas(id_usuario, limite=20):
    """Só as memórias vigentes (as superadas ficam guardadas, mas inativas)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM memorias
                WHERE id_usuario = %s AND ativa
                ORDER BY atualizado_em DESC
                LIMIT %s
                """,
                (id_usuario, limite),
            )
            linhas = cur.fetchall()
    return [dict(linha) for linha in linhas]


def substituir_memoria(id_usuario, chave, conteudo, confianca, evidencias, origem="observado"):
    """
    Mantém UMA memória ativa por (usuário, chave).

      - não existia           -> cria                      (retorna 'criada')
      - mesmo conteúdo        -> só atualiza confiança/evidências ('reforcada')
      - conteúdo diferente    -> a antiga fica inativa (histórico preservado)
                                 e a nova entra ativa      ('substituida')
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_memoria, conteudo FROM memorias
                WHERE id_usuario = %s AND chave = %s AND ativa
                FOR UPDATE
                """,
                (id_usuario, chave),
            )
            atual = cur.fetchone()

            if atual and atual["conteudo"] == conteudo:
                cur.execute(
                    """
                    UPDATE memorias
                    SET confianca = %s, evidencias = %s, atualizado_em = CURRENT_TIMESTAMP
                    WHERE id_memoria = %s
                    """,
                    (confianca, evidencias, atual["id_memoria"]),
                )
                return "reforcada"

            if atual:
                cur.execute(
                    "UPDATE memorias SET ativa = FALSE, atualizado_em = CURRENT_TIMESTAMP WHERE id_memoria = %s",
                    (atual["id_memoria"],),
                )
            cur.execute(
                """
                INSERT INTO memorias (id_usuario, conteudo, confianca, chave, origem, evidencias)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (id_usuario, conteudo, confianca, chave, origem, evidencias),
            )
            return "substituida" if atual else "criada"


def atualizar_memoria(id_memoria, id_usuario, conteudo, confianca):
    """Atualiza uma memória somente se ela pertencer ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE memorias
                SET conteudo = %s,
                    confianca = %s
                WHERE id_memoria = %s
                  AND id_usuario = %s
                """,
                (conteudo, confianca, id_memoria, id_usuario),
            )
            return cur.rowcount


# ============================================================
# 15. RESTRIÇÕES
# ============================================================

def listar_restricoes(id_usuario):
    """Lista as restrições registradas para o usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM restricoes
                WHERE id_usuario = %s
                ORDER BY dia_semana, hora_inicio
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 16. DECISÕES
# ============================================================

def salvar_decisao(id_usuario, contexto, criterios, decisao):
    """Registra uma decisão tomada pelo Motor de Decisão."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO decisoes
                    (id_usuario, contexto, criterios_usados, decisao_tomada)
                VALUES (%s, %s, %s, %s)
                RETURNING id_decisao
                """,
                (id_usuario, contexto, criterios, decisao),
            )
            return cur.fetchone()["id_decisao"]


def listar_decisoes(id_usuario, limite=None):
    """Lista as decisões do usuário das mais recentes às mais antigas (limite opcional)."""
    query = """
        SELECT *
        FROM decisoes
        WHERE id_usuario = %s
        ORDER BY criado_em DESC
    """
    parametros = [id_usuario]
    if limite:
        query += " LIMIT %s"
        parametros.append(int(limite))
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 17. RECOMENDAÇÕES
# ============================================================

def salvar_recomendacao(id_usuario, texto, id_decisao=None, id_tarefa=None, tipo="geral"):
    """
    Salva uma recomendação. Decisão e tarefa informadas precisam pertencer
    ao mesmo usuário; caso contrário nada é gravado (retorna None).
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            return _inserir_recomendacao(cur, id_usuario, texto, id_decisao, id_tarefa, tipo)


def _inserir_recomendacao(cur, id_usuario, texto, id_decisao, id_tarefa, tipo):
    if id_decisao is not None:
        cur.execute(
            "SELECT 1 FROM decisoes WHERE id_decisao = %s AND id_usuario = %s",
            (id_decisao, id_usuario),
        )
        if cur.fetchone() is None:
            return None
    if id_tarefa is not None:
        cur.execute(
            "SELECT 1 FROM tarefas WHERE id_tarefa = %s AND id_usuario = %s",
            (id_tarefa, id_usuario),
        )
        if cur.fetchone() is None:
            return None

    cur.execute(
        """
        INSERT INTO recomendacoes (id_decisao, id_usuario, conteudo, id_tarefa, tipo)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id_recomendacao
        """,
        (id_decisao, id_usuario, texto, id_tarefa, tipo),
    )
    return cur.fetchone()["id_recomendacao"]


def registrar_decisao_com_recomendacao(id_usuario, contexto, criterios, decisao, texto, id_tarefa=None, tipo="geral"):
    """Grava decisão + recomendação juntas (uma transação). Retorna (id_decisao, id_recomendacao)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO decisoes (id_usuario, contexto, criterios_usados, decisao_tomada)
                VALUES (%s, %s, %s, %s)
                RETURNING id_decisao
                """,
                (id_usuario, contexto, criterios, decisao),
            )
            id_decisao = cur.fetchone()["id_decisao"]
            id_recomendacao = _inserir_recomendacao(cur, id_usuario, texto, id_decisao, id_tarefa, tipo)
            return id_decisao, id_recomendacao


def buscar_recomendacao_aberta_recente(id_usuario, id_tarefa, tipo, horas=2):
    """Recomendação do mesmo tipo para a mesma tarefa, sem resultado, criada há pouco."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.*
                FROM recomendacoes r
                WHERE r.id_usuario = %s AND r.id_tarefa = %s AND r.tipo = %s
                  AND LOCALTIMESTAMP - r.criado_em <= %s * INTERVAL '1 hour'
                  AND NOT EXISTS (
                      SELECT 1 FROM resultados_recomendacoes x
                      WHERE x.id_recomendacao = r.id_recomendacao
                  )
                ORDER BY r.criado_em DESC
                LIMIT 1
                """,
                (id_usuario, id_tarefa, tipo, horas),
            )
            linha = cur.fetchone()
    return dict(linha) if linha else None


def listar_recomendacoes_sem_resultado(id_usuario):
    """
    Recomendações ligadas a uma tarefa e ainda sem reação registrada, com o
    estado atual da tarefa. É o que o aprendizado varre para fechar
    recomendações vencidas como 'ignorou'.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.*, t.status AS tarefa_status, t.data_fim AS tarefa_data_fim,
                       t.concluido_em AS tarefa_concluido_em
                FROM recomendacoes r
                JOIN tarefas t ON t.id_tarefa = r.id_tarefa
                WHERE r.id_usuario = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM resultados_recomendacoes x
                      WHERE x.id_recomendacao = r.id_recomendacao
                  )
                ORDER BY r.criado_em
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()
    return [dict(linha) for linha in linhas]


def contar_resultados_recomendacoes(id_usuario):
    """{'aceitou': n, 'recusou': n, 'adiou': n, 'ignorou': n} das recomendações do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rr.acao_usuario, COUNT(*) AS n
                FROM resultados_recomendacoes rr
                JOIN recomendacoes r ON r.id_recomendacao = rr.id_recomendacao
                WHERE r.id_usuario = %s
                GROUP BY rr.acao_usuario
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()
    return {linha["acao_usuario"]: linha["n"] for linha in linhas}


def listar_recomendacoes(id_usuario):
    """Lista recomendações do usuário das mais recentes às mais antigas."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM recomendacoes
                WHERE id_usuario = %s
                ORDER BY criado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 18. RESULTADOS DAS RECOMENDAÇÕES
# ============================================================

def salvar_resultado_recomendacao(
    id_recomendacao,
    id_usuario,
    acao_usuario,
    resultado=None,
):
    """
    Registra o resultado somente se a recomendação pertencer ao usuário.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO resultados_recomendacoes
                    (id_recomendacao, acao_usuario, resultado)
                SELECT id_recomendacao, %s, %s
                FROM recomendacoes
                WHERE id_recomendacao = %s
                  AND id_usuario = %s
                RETURNING id_resultado
                """,
                (
                    acao_usuario,
                    resultado,
                    id_recomendacao,
                    id_usuario,
                ),
            )
            linha = cur.fetchone()

    if linha is None:
        return None

    return linha["id_resultado"]


def listar_resultados_recomendacoes(id_recomendacao, id_usuario):
    """Lista resultados de uma recomendação do usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rr.*
                FROM resultados_recomendacoes rr
                JOIN recomendacoes r
                  ON r.id_recomendacao = rr.id_recomendacao
                WHERE rr.id_recomendacao = %s
                  AND r.id_usuario = %s
                ORDER BY rr.registrado_em DESC
                """,
                (id_recomendacao, id_usuario),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 19. PLANEJAMENTO DE TAREFAS
# ============================================================

def buscar_planejamento_tarefa(id_tarefa, id_usuario):
    """Busca o planejamento de uma tarefa pertencente ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tp.*
                FROM tarefa_planejamento tp
                JOIN tarefas t
                  ON t.id_tarefa = tp.id_tarefa
                WHERE tp.id_tarefa = %s
                  AND t.id_usuario = %s
                """,
                (id_tarefa, id_usuario),
            )
            linha = cur.fetchone()

    return dict(linha) if linha else None


# ============================================================
# AÇÃO PENDENTE DE CONFIRMAÇÃO (conflito de agenda)
# Quando a IA pergunta "confirma mesmo assim?", a ação fica guardada aqui. O "sim"
# seguinte executa exatamente ela, sem depender do modelo reescrever o comando.
# Uma linha por usuário; vale por poucos minutos.
# ============================================================
def salvar_acoes_pendentes(id_usuario, acoes):
    """Substitui as ações pendentes do usuário (lista de dicts JSON-serializáveis)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO acoes_pendentes (id_usuario, acoes, criado_em)
                VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (id_usuario)
                DO UPDATE SET acoes = EXCLUDED.acoes, criado_em = CURRENT_TIMESTAMP
                """,
                (id_usuario, json.dumps(acoes, ensure_ascii=False)),
            )


def buscar_acoes_pendentes(id_usuario, max_idade_min=15):
    """Ações pendentes ainda válidas (lista) ou None."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT acoes
                FROM acoes_pendentes
                WHERE id_usuario = %s
                  AND criado_em >= CURRENT_TIMESTAMP - make_interval(mins => %s)
                """,
                (id_usuario, int(max_idade_min)),
            )
            linha = cur.fetchone()
    return linha["acoes"] if linha else None


def apagar_acoes_pendentes(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM acoes_pendentes WHERE id_usuario = %s", (id_usuario,))


def enriquecer_tarefas(id_usuario, tarefas):
    """
    Acrescenta a cada tarefa (dict) os campos que o motor de decisão usa e
    que não existem na tabela 'tarefas', em UMA consulta para a lista toda:

      prioridade           'baixa' | 'media' | 'alta' (tarefa_planejamento) ou None
      objetivo_prazo       menor prazo entre os objetivos em andamento ligados à tarefa
      dependencia_pendente True se algum pré-requisito ainda está aberto

    (tarefa_dependencias.id_tarefa depende de id_tarefa_dependente.)
    Devolve a mesma lista; sem dados nessas tabelas, os campos ficam None/False.
    """
    ids = [t["id_tarefa"] for t in tarefas]
    if not ids:
        return tarefas
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id_tarefa,
                       (SELECT tp.prioridade
                          FROM tarefa_planejamento tp
                         WHERE tp.id_tarefa = t.id_tarefa
                         ORDER BY tp.id_planejamento DESC LIMIT 1) AS prioridade,
                       (SELECT MIN(o.prazo)
                          FROM tarefa_objetivos tob
                          JOIN objetivos o ON o.id_objetivo = tob.id_objetivo
                         WHERE tob.id_tarefa = t.id_tarefa
                           AND o.id_usuario = t.id_usuario
                           AND o.status = 'em_andamento') AS objetivo_prazo,
                       EXISTS (SELECT 1
                                 FROM tarefa_dependencias d
                                 JOIN tarefas pre ON pre.id_tarefa = d.id_tarefa_dependente
                                WHERE d.id_tarefa = t.id_tarefa
                                  AND pre.status IN ('pendente', 'em_andamento')) AS dependencia_pendente
                  FROM tarefas t
                 WHERE t.id_usuario = %s
                   AND t.id_tarefa = ANY(%s)
                """,
                (id_usuario, ids),
            )
            extras = {linha["id_tarefa"]: linha for linha in cur.fetchall()}
    for t in tarefas:
        e = extras.get(t["id_tarefa"]) or {}
        t["prioridade"] = e.get("prioridade")
        t["objetivo_prazo"] = e.get("objetivo_prazo")
        t["dependencia_pendente"] = bool(e.get("dependencia_pendente"))
    return tarefas


# ============================================================
# 20. RELAÇÃO TAREFA ↔ OBJETIVOS
# ============================================================

def listar_objetivos_da_tarefa(id_tarefa, id_usuario):
    """Lista objetivos associados a uma tarefa pertencente ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.*
                FROM objetivos o
                JOIN tarefa_objetivos tobj
                  ON tobj.id_objetivo = o.id_objetivo
                JOIN tarefas t
                  ON t.id_tarefa = tobj.id_tarefa
                WHERE tobj.id_tarefa = %s
                  AND t.id_usuario = %s
                  AND o.id_usuario = %s
                ORDER BY o.criado_em DESC
                """,
                (id_tarefa, id_usuario, id_usuario),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 21. DEPENDÊNCIAS ENTRE TAREFAS
# ============================================================

def listar_dependencias_da_tarefa(id_tarefa, id_usuario):
    """
    Lista as tarefas das quais a tarefa informada depende.
    A relação é definida por:
    tarefa_dependencias.id_tarefa -> tarefa_dependente;
    tarefa_dependencias.id_tarefa_dependente -> pré-requisito.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.*
                FROM tarefas t
                JOIN tarefa_dependencias d
                  ON d.id_tarefa_dependente = t.id_tarefa
                JOIN tarefas tarefa_alvo
                  ON tarefa_alvo.id_tarefa = d.id_tarefa
                WHERE d.id_tarefa = %s
                  AND tarefa_alvo.id_usuario = %s
                  AND t.id_usuario = %s
                ORDER BY t.data_inicio
                """,
                (id_tarefa, id_usuario, id_usuario),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


def calcular_pontos_mascote(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM tarefas WHERE id_usuario = %s AND status = 'concluida'",
                (id_usuario,),
            )
            tarefas = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM objetivos WHERE id_usuario = %s AND status = 'concluido'",
                (id_usuario,),
            )
            objetivos = cur.fetchone()["n"]
    return tarefas * 10 + objetivos * 50