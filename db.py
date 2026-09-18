"""
NEOCORTEX — Backend completo (PostgreSQL)

Mesma estrutura e funções da versão SQLite, adaptadas pra PostgreSQL.
Principais diferenças de código em relação à versão SQLite:

  1. Placeholder de parâmetro: SQLite usa "?", psycopg2 usa "%s".
  2. sqlite3 tem cursor.lastrowid pra pegar o id gerado; psycopg2 não
     tem — por isso todo INSERT termina com "RETURNING id_da_coluna"
     e a gente lê esse valor do próprio SELECT do INSERT.
  3. sqlite3.Row deixa acessar coluna por nome direto; aqui usamos
     RealDictCursor, que já devolve cada linha como um dicionário.
  4. No SQLite era preciso ligar manualmente o PRAGMA foreign_keys;
     no Postgres as foreign keys já são sempre aplicadas.

Requisitos:
    pip install psycopg2-binary bcrypt
"""

import os
import psycopg2
import psycopg2.extras
import bcrypt
from contextlib import contextmanager
from dotenv import load_dotenv

# Lê o arquivo .env (que fica na mesma pasta) e carrega as variáveis
# de ambiente automaticamente, sem precisar fazer nada manual.
load_dotenv()

# Dados de conexão. Em produção, prefira variáveis de ambiente
# (nunca deixe usuário/senha reais fixos no código).
CONFIG_BANCO = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "neocortex"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


# ============================================================
# CONEXÃO
# ============================================================

@contextmanager
def conectar():
    """
    Abre uma conexão com o Postgres e devolve um cursor que já
    retorna cada linha como dicionário (RealDictCursor), equivalente
    ao sqlite3.Row da versão SQLite.

    Mesma lógica de antes: commit automático se der tudo certo,
    rollback se der erro, e fecha a conexão sempre no final.
    """
    conn = psycopg2.connect(**CONFIG_BANCO, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def criar_tabelas():
    """Executa o neocortex_schema_postgres.sql pra criar as tabelas."""
    with open("neocortex_schema_postgres.sql", "r", encoding="utf-8") as f:
        schema = f.read()
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)


# ============================================================
# 1. USUÁRIOS / LOGIN
# ============================================================

def cadastrar_usuario(nome, email, senha, faixa_etaria, ocupacao, turno=None):
    """
    Cadastra um usuário. bcrypt gera um hash com salt embutido — mesma
    senha em usuários diferentes resulta em hashes diferentes.
    Guardamos o hash como texto (.decode) porque a coluna é TEXT.
    """
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    with conectar() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO usuarios (nome, email, senha_hash, faixa_etaria, ocupacao, turno)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id_usuario
                    """,
                    (nome, email, senha_hash, faixa_etaria, ocupacao, turno),
                )
                return cur.fetchone()["id_usuario"]
            except psycopg2.errors.UniqueViolation:
                # dispara quando o email já existe (UNIQUE) — precisa
                # dar rollback aqui porque o Postgres trava a transação
                # inteira depois de um erro, até o rollback acontecer
                conn.rollback()
                raise ValueError("Já existe um usuário cadastrado com esse e-mail.")


def verificar_login(email, senha):
    """Confere a senha digitada contra o hash salvo. Retorna None se não bater."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
            linha = cur.fetchone()

    if linha is None:
        return None

    senha_correta = bcrypt.checkpw(senha.encode("utf-8"), linha["senha_hash"].encode("utf-8"))
    return dict(linha) if senha_correta else None


def buscar_usuario(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE id_usuario = %s", (id_usuario,))
            linha = cur.fetchone()
    return dict(linha) if linha else None


def atualizar_usuario(id_usuario, **campos):
    campos.pop("senha", None)
    if not campos:
        return
    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_usuario]
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE usuarios SET {colunas} WHERE id_usuario = %s", valores)


def trocar_senha(id_usuario, nova_senha):
    novo_hash = bcrypt.hashpw(nova_senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET senha_hash = %s WHERE id_usuario = %s",
                (novo_hash, id_usuario),
            )


# ============================================================
# 2. HOBBIES (catálogo) + USUARIO_HOBBIES (relação N:N)
# ============================================================

def obter_ou_criar_hobby(nome):
    nome = nome.strip().lower()
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_hobby FROM hobbies WHERE nome = %s", (nome,))
            linha = cur.fetchone()
            if linha:
                return linha["id_hobby"]
            cur.execute(
                "INSERT INTO hobbies (nome) VALUES (%s) RETURNING id_hobby", (nome,)
            )
            return cur.fetchone()["id_hobby"]


def listar_hobbies_catalogo():
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM hobbies ORDER BY nome")
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


def associar_hobby(id_usuario, nome_hobby):
    id_hobby = obter_ou_criar_hobby(nome_hobby)
    with conectar() as conn:
        with conn.cursor() as cur:
            # ON CONFLICT DO NOTHING = equivalente Postgres do "tenta
            # inserir, mas se a chave primária composta já existir, ignora"
            cur.execute(
                """
                INSERT INTO usuario_hobbies (id_usuario, id_hobby)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (id_usuario, id_hobby),
            )


def remover_hobby(id_usuario, nome_hobby):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM usuario_hobbies
                WHERE id_usuario = %s
                  AND id_hobby = (SELECT id_hobby FROM hobbies WHERE nome = %s)
                """,
                (id_usuario, nome_hobby.strip().lower()),
            )


def listar_hobbies_usuario(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT h.id_hobby, h.nome
                FROM hobbies h
                JOIN usuario_hobbies uh ON uh.id_hobby = h.id_hobby
                WHERE uh.id_usuario = %s
                ORDER BY h.nome
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


# ============================================================
# 3. TAREFAS (CRUD)
# ============================================================

def criar_tarefa(id_usuario, titulo, data_inicio, data_fim,
                  descricao=None, categoria=None, cor=None, origem="manual"):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tarefas
                    (id_usuario, titulo, descricao, categoria, data_inicio, data_fim, cor, origem)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id_tarefa
                """,
                (id_usuario, titulo, descricao, categoria, data_inicio, data_fim, cor, origem),
            )
            return cur.fetchone()["id_tarefa"]


def listar_tarefas(id_usuario, data_inicio=None, data_fim=None, status=None):
    query = "SELECT * FROM tarefas WHERE id_usuario = %s"
    parametros = [id_usuario]

    if data_inicio and data_fim:
        query += " AND data_inicio >= %s AND data_fim <= %s"
        parametros += [data_inicio, data_fim]

    if status:
        query += " AND status = %s"
        parametros.append(status)

    query += " ORDER BY data_inicio"

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


def buscar_tarefa(id_tarefa):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tarefas WHERE id_tarefa = %s", (id_tarefa,))
            linha = cur.fetchone()
    return dict(linha) if linha else None


def atualizar_tarefa(id_tarefa, **campos):
    if not campos:
        return
    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_tarefa]
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE tarefas SET {colunas} WHERE id_tarefa = %s", valores)


def deletar_tarefa(id_tarefa):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tarefas WHERE id_tarefa = %s", (id_tarefa,))


def marcar_tarefa_concluida(id_tarefa):
    """
    Marca a tarefa como concluída E registra o momento exato em que
    isso aconteceu (CURRENT_TIMESTAMP), tudo numa única chamada —
    em vez de depender que quem usa a função lembre de mandar a
    data manualmente toda vez. É esse campo (concluido_em) que
    alimenta os gráficos de produtividade.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tarefas
                SET status = 'concluida', concluido_em = CURRENT_TIMESTAMP
                WHERE id_tarefa = %s
                """,
                (id_tarefa,),
            )


def desfazer_conclusao_tarefa(id_tarefa):
    """Volta a tarefa pro status pendente e limpa a data de conclusão (caso o usuário desmarque por engano)."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tarefas
                SET status = 'pendente', concluido_em = NULL
                WHERE id_tarefa = %s
                """,
                (id_tarefa,),
            )


# ============================================================
# 4. ROTINA FIXA (CRUD)
# ============================================================

def adicionar_rotina(id_usuario, dia_semana, descricao, hora_inicio, hora_fim):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rotina_fixa (id_usuario, dia_semana, descricao, hora_inicio, hora_fim)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id_rotina
                """,
                (id_usuario, dia_semana, descricao, hora_inicio, hora_fim),
            )
            return cur.fetchone()["id_rotina"]


def listar_rotina(id_usuario, dia_semana=None):
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
    return [dict(l) for l in linhas]


def atualizar_rotina(id_rotina, **campos):
    if not campos:
        return
    colunas = ", ".join(f"{chave} = %s" for chave in campos)
    valores = list(campos.values()) + [id_rotina]
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE rotina_fixa SET {colunas} WHERE id_rotina = %s", valores)


def deletar_rotina(id_rotina):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rotina_fixa WHERE id_rotina = %s", (id_rotina,))


# ============================================================
# 5. INTERAÇÕES COM O CHAT
# ============================================================

def registrar_interacao(id_usuario, conteudo, tipo="texto", contexto="interacao_geral"):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO interacoes_chat (id_usuario, tipo, conteudo, contexto)
                VALUES (%s, %s, %s, %s)
                RETURNING id_interacao
                """,
                (id_usuario, tipo, conteudo, contexto),
            )
            return cur.fetchone()["id_interacao"]


def listar_interacoes(id_usuario, contexto=None, limite=100):
    query = "SELECT * FROM interacoes_chat WHERE id_usuario = %s"
    parametros = [id_usuario]
    if contexto:
        query += " AND contexto = %s"
        parametros.append(contexto)
    query += " ORDER BY data_hora DESC LIMIT %s"
    parametros.append(limite)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(query, parametros)
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


# ============================================================
# 6. PADRÕES COMPORTAMENTAIS
# ============================================================

def salvar_padrao(id_usuario, tipo_padrao, valor):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id_padrao FROM padroes_comportamentais WHERE id_usuario = %s AND tipo_padrao = %s",
                (id_usuario, tipo_padrao),
            )
            existente = cur.fetchone()

            if existente:
                cur.execute(
                    """
                    UPDATE padroes_comportamentais
                    SET valor = %s, calculado_em = CURRENT_TIMESTAMP
                    WHERE id_padrao = %s
                    """,
                    (valor, existente["id_padrao"]),
                )
                return existente["id_padrao"]
            else:
                cur.execute(
                    """
                    INSERT INTO padroes_comportamentais (id_usuario, tipo_padrao, valor)
                    VALUES (%s, %s, %s)
                    RETURNING id_padrao
                    """,
                    (id_usuario, tipo_padrao, valor),
                )
                return cur.fetchone()["id_padrao"]


def listar_padroes(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM padroes_comportamentais WHERE id_usuario = %s", (id_usuario,)
            )
            linhas = cur.fetchall()
    return [dict(l) for l in linhas]


def obter_padrao(id_usuario, tipo_padrao):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM padroes_comportamentais WHERE id_usuario = %s AND tipo_padrao = %s",
                (id_usuario, tipo_padrao),
            )
            linha = cur.fetchone()
    return dict(linha) if linha else None
