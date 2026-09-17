"""
NEOCORTEX — app.py
Interface Streamlit que liga tudo: cadastro, login, tarefas e dashboard.
"""

import streamlit as st
import db
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="NEOCORTEX", layout="wide")

# ------------------------------------------------------------
# "Mochila" que guarda quem está logado entre um clique e outro
# ------------------------------------------------------------
if "id_usuario" not in st.session_state:
    st.session_state.id_usuario = None


# ============================================================
# TELA DE LOGIN / CADASTRO (só aparece se ninguém estiver logado)
# ============================================================
def tela_login_cadastro():
    st.title("NEOCORTEX")
    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar conta"])

    with aba_login:
        with st.form("form_login"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                usuario = db.verificar_login(email, senha)
                if usuario:
                    st.session_state.id_usuario = usuario["id_usuario"]
                    st.rerun()
                else:
                    st.error("E-mail ou senha errados.")

    with aba_cadastro:
        with st.form("form_cadastro"):
            nome = st.text_input("Nome")
            email = st.text_input("E-mail", key="cad_email")
            senha = st.text_input("Senha", type="password", key="cad_senha")
            faixa_etaria = st.selectbox("Faixa etária", ["14-18", "18-30", "30-50+"])
            ocupacao = st.selectbox("Você trabalha, estuda ou nenhum?", ["trabalha", "estuda", "nenhum"])
            turno = st.selectbox("Turno", ["manha", "tarde", "noite", "personalizado"])
            hobbies_texto = st.text_input("Hobbies (separados por vírgula)")

            if st.form_submit_button("Cadastrar"):
                try:
                    id_usuario = db.cadastrar_usuario(nome, email, senha, faixa_etaria, ocupacao, turno)
                    for hobby in hobbies_texto.split(","):
                        if hobby.strip():
                            db.associar_hobby(id_usuario, hobby)
                    st.session_state.id_usuario = id_usuario
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))


# ============================================================
# TELA DE TAREFAS
# ============================================================
def tela_tarefas():
    st.header("Minhas tarefas")

    with st.form("form_tarefa"):
        titulo = st.text_input("Título da tarefa")
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.text_input("Início (ex: 2026-09-17T19:00)")
        with col2:
            data_fim = st.text_input("Fim (ex: 2026-09-17T21:00)")
        categoria = st.selectbox("Categoria", ["trabalho", "estudo", "hobby", "pessoal", "saude", "outro"])
        if st.form_submit_button("Salvar tarefa"):
            db.criar_tarefa(st.session_state.id_usuario, titulo, data_inicio, data_fim, categoria=categoria)
            st.rerun()

    tarefas = db.listar_tarefas(st.session_state.id_usuario)
    for t in tarefas:
        col1, col2, col3 = st.columns([4, 2, 1])
        col1.write(f"**{t['titulo']}** — {t['categoria']}")
        col2.write(t["status"])
        if t["status"] != "concluida":
            if col3.button("Concluir", key=f"concluir_{t['id_tarefa']}"):
                db.marcar_tarefa_concluida(t["id_tarefa"])
                st.rerun()


# ============================================================
# TELA DE DASHBOARD
# ============================================================
def tela_dashboard():
    st.header("Dashboard de produtividade")

    tarefas = db.listar_tarefas(st.session_state.id_usuario)
    df = pd.DataFrame(tarefas)

    if df.empty:
        st.info("Cadastre tarefas pra ver o dashboard.")
        return

    contagem_status = df["status"].value_counts().reset_index()
    contagem_status.columns = ["status", "quantidade"]
    st.plotly_chart(px.bar(contagem_status, x="status", y="quantidade", title="Tarefas por status"))


# ============================================================
# ROTEAMENTO PRINCIPAL
# ============================================================
if st.session_state.id_usuario is None:
    tela_login_cadastro()
else:
    st.sidebar.write(f"Usuário logado: id {st.session_state.id_usuario}")
    if st.sidebar.button("Sair"):
        st.session_state.id_usuario = None
        st.rerun()

    aba = st.sidebar.radio("Ir para:", ["Tarefas", "Dashboard"])
    if aba == "Tarefas":
        tela_tarefas()
    else:
        tela_dashboard()