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

import os
from pathlib import Path
from contextlib import contextmanager

import bcrypt
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from psycopg2 import pool


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

CONFIG_BANCO = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "neocortex"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

POOL_CONEXOES = pool.SimpleConnectionPool(
    1,
    10,
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
        POOL_CONEXOES.putconn(conn)


def criar_tabelas():
    """Executa os schemas PostgreSQL na ordem correta."""
    arquivos_schema = (
        BASE_DIR / "neocortex_schema_postgres.sql",
        BASE_DIR / "neocortex_novas_tabelas.sql",
    )

    with conectar() as conn:
        with conn.cursor() as cur:
            for caminho_schema in arquivos_schema:
                with caminho_schema.open("r", encoding="utf-8") as arquivo:
                    cur.execute(arquivo.read())


# ============================================================
# 1. USUÁRIOS / LOGIN
# ============================================================

def cadastrar_usuario(nome, email, senha, faixa_etaria, trabalha, estuda, turno=None):
    """
    Cadastra um usuário e retorna o id criado.
    """
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

def criar_tarefa(id_usuario, titulo, data_inicio, data_fim, categoria=None, descricao=None, origem="manual"):
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
            return cur.fetchone()["id_tarefa"]


def listar_tarefas(id_usuario, status=None, data_inicio=None, data_fim=None):
    query = "SELECT * FROM tarefas WHERE id_usuario = %s"
    parametros = [id_usuario]
    if status:
        query += " AND status = %s"
        parametros.append(status)
    if data_inicio:
        query += " AND data_inicio >= %s"
        parametros.append(data_inicio)
    if data_fim:
        query += " AND data_fim <= %s"
        parametros.append(data_fim)
    query += " ORDER BY data_inicio"

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
    """Atualiza somente campos permitidos de uma tarefa do usuário."""
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
                f"""
                UPDATE tarefas
                SET {colunas}
                WHERE id_tarefa = %s
                  AND id_usuario = %s
                """,
                valores,
            )
            return cur.rowcount


def deletar_tarefa(id_tarefa, id_usuario):
    """Exclui somente uma tarefa pertencente ao usuário."""
    with conectar() as conn:
        with conn.cursor() as cur:
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
    Marca a tarefa como concluída e registra o evento de execução na mesma
    transação. Isso mantém estado atual e histórico sincronizados.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
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

            if cur.rowcount == 0:
                return 0

            cur.execute(
                """
                INSERT INTO eventos_execucao
                    (id_tarefa, tipo_evento)
                VALUES (%s, 'concluiu')
                """,
                (id_tarefa,),
            )

            return 1


def desfazer_conclusao_tarefa(id_tarefa, id_usuario):
    """Volta a tarefa para pendente e remove a data de conclusão."""
    with conectar() as conn:
        with conn.cursor() as cur:
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
            return cur.rowcount


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

    query += " ORDER BY data_hora DESC LIMIT %s"
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


def listar_decisoes(id_usuario):
    """Lista as decisões do usuário das mais recentes às mais antigas."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM decisoes
                WHERE id_usuario = %s
                ORDER BY criado_em DESC
                """,
                (id_usuario,),
            )
            linhas = cur.fetchall()

    return [dict(linha) for linha in linhas]


# ============================================================
# 17. RECOMENDAÇÕES
# ============================================================

def salvar_recomendacao(id_usuario, texto, id_decisao=None):
    """
    Salva uma recomendação. Quando houver decisão relacionada, garante que
    essa decisão pertença ao mesmo usuário.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            if id_decisao is not None:
                cur.execute(
                    """
                    SELECT 1
                    FROM decisoes
                    WHERE id_decisao = %s
                      AND id_usuario = %s
                    """,
                    (id_decisao, id_usuario),
                )
                if cur.fetchone() is None:
                    return None

            cur.execute(
                """
                INSERT INTO recomendacoes
                    (id_decisao, id_usuario, conteudo)
                VALUES (%s, %s, %s)
                RETURNING id_recomendacao
                """,
                (id_decisao, id_usuario, texto),
            )
            return cur.fetchone()["id_recomendacao"]


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
