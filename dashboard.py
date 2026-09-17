"""
NEOCORTEX — Exemplo de dashboard de produtividade
Combina pandas (agrupar/calcular) + Plotly Express (desenhar).

Ideia geral: pandas nunca fala com o banco diretamente aqui — ele
recebe os dados já prontos (uma lista de dicionários) vindos do
db.listar_tarefas(), e só organiza/calcula em cima disso.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
import db


def montar_dataframe_tarefas(id_usuario):
    """
    Busca as tarefas do usuário no banco e transforma numa tabela
    pandas (DataFrame) — é o pandas.DataFrame que faz a ponte entre
    "lista de dicionários vinda do banco" e "tabela que dá pra
    agrupar, filtrar e agregar com facilidade".
    """
    tarefas = db.listar_tarefas(id_usuario)
    df = pd.DataFrame(tarefas)

    if df.empty:
        return df

    # Converte as colunas de texto/timestamp em datas de verdade,
    # senão o pandas trata tudo como texto e não dá pra comparar/agrupar por dia
    df["data_inicio"] = pd.to_datetime(df["data_inicio"])
    df["concluido_em"] = pd.to_datetime(df["concluido_em"])
    return df


def grafico_tarefas_por_status(df):
    """Quantas tarefas em cada status (pendente/em_andamento/concluida/cancelada)."""
    contagem = df["status"].value_counts().reset_index()
    contagem.columns = ["status", "quantidade"]

    fig = px.bar(contagem, x="status", y="quantidade", title="Tarefas por status")
    return fig


def grafico_conclusoes_por_dia(df):
    """
    Quantas tarefas foram concluídas em cada dia — só é possível
    graças à coluna concluido_em. Ignora tarefas que ainda não
    foram concluídas (concluido_em nulo).
    """
    concluidas = df.dropna(subset=["concluido_em"]).copy()
    if concluidas.empty:
        return None

    concluidas["dia"] = concluidas["concluido_em"].dt.date
    contagem = concluidas.groupby("dia").size().reset_index(name="quantidade")

    fig = px.line(contagem, x="dia", y="quantidade", markers=True,
                   title="Tarefas concluídas por dia")
    return fig


def grafico_tarefas_por_categoria(df):
    """Distribuição de tarefas por categoria (trabalho/estudo/hobby/...)."""
    contagem = df["categoria"].value_counts().reset_index()
    contagem.columns = ["categoria", "quantidade"]

    fig = px.pie(contagem, names="categoria", values="quantidade",
                 title="Tarefas por categoria")
    return fig


def pontualidade_media(df):
    """
    Calcula, em média, se o usuário costuma concluir tarefas antes
    ou depois do prazo (data_fim). Resultado negativo = concluiu
    antes do prazo, em média; positivo = depois.
    """
    concluidas = df.dropna(subset=["concluido_em"]).copy()
    if concluidas.empty:
        return None

    concluidas["data_fim"] = pd.to_datetime(concluidas["data_fim"])
    concluidas["atraso_horas"] = (
        concluidas["concluido_em"] - concluidas["data_fim"]
    ).dt.total_seconds() / 3600

    return concluidas["atraso_horas"].mean()


# ------------------------------------------------------------
# Exemplo de uso dentro de uma tela Streamlit
# ------------------------------------------------------------
def pagina_dashboard():
    st.title("Dashboard de produtividade")

    id_usuario = st.session_state.id_usuario
    df = montar_dataframe_tarefas(id_usuario)

    if df.empty:
        st.info("Você ainda não tem tarefas cadastradas.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(grafico_tarefas_por_status(df), use_container_width=True)
    with col2:
        st.plotly_chart(grafico_tarefas_por_categoria(df), use_container_width=True)

    fig_conclusoes = grafico_conclusoes_por_dia(df)
    if fig_conclusoes:
        st.plotly_chart(fig_conclusoes, use_container_width=True)

    media = pontualidade_media(df)
    if media is not None:
        if media <= 0:
            st.success(f"Em média, você conclui tarefas {abs(media):.1f}h antes do prazo.")
        else:
            st.warning(f"Em média, você conclui tarefas {media:.1f}h depois do prazo.")