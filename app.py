"""
NEOCORTEX — app.py (Flask)
O "zelador da casa": decide qual página HTML mostrar, busca os dados
no db.py quando precisa, e entrega a página pronta pro navegador.
"""

import os
import pandas as pd
import plotly.express as px
from flask import Flask, render_template, request, redirect, url_for, session

import db

app = Flask(__name__)

# Chave usada pelo Flask pra "assinar" o cookie de sessão (quem está
# logado). Em produção, isso também deveria vir do .env — por ora,
# um valor fixo simples já resolve pro MVP.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "troque-essa-chave-em-producao")


def usuario_logado():
    """Devolve o id do usuário logado, ou None se ninguém estiver logado."""
    return session.get("id_usuario")


# ============================================================
# ROTA INICIAL — manda pra tarefas se já estiver logado,
# ou pra tela de login se não estiver
# ============================================================
@app.route("/")
def inicio():
    if usuario_logado():
        return redirect(url_for("tarefas"))
    return redirect(url_for("tela_login"))


# ============================================================
# LOGIN / CADASTRO
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def tela_login():
    if request.method == "GET":
        return render_template("auth.html", aba="login", erro=None)

    email = request.form["email"]
    senha = request.form["senha"]
    usuario = db.verificar_login(email, senha)

    if usuario:
        session["id_usuario"] = usuario["id_usuario"]
        session["nome"] = usuario["nome"]
        return redirect(url_for("tarefas"))

    return render_template("auth.html", aba="login", erro="E-mail ou senha errados.")


@app.route("/cadastro", methods=["POST"])
def cadastro():
    nome = request.form["nome"]
    email = request.form["email"]
    senha = request.form["senha"]
    faixa_etaria = request.form["faixa_etaria"]
    ocupacao = request.form["ocupacao"]
    turno = request.form.get("turno")
    hobbies_texto = request.form.get("hobbies", "")

    try:
        id_usuario = db.cadastrar_usuario(nome, email, senha, faixa_etaria, ocupacao, turno)
        for hobby in hobbies_texto.split(","):
            if hobby.strip():
                db.associar_hobby(id_usuario, hobby)

        session["id_usuario"] = id_usuario
        session["nome"] = nome
        return redirect(url_for("tarefas"))

    except ValueError as erro:
        return render_template("auth.html", aba="cadastro", erro=str(erro))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("tela_login"))


# ============================================================
# TAREFAS
# ============================================================
@app.route("/tarefas")
def tarefas():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    lista_tarefas = db.listar_tarefas(usuario_logado())
    return render_template(
        "tarefas.html",
        tarefas=lista_tarefas,
        pagina="tarefas",
        titulo_pagina="Tarefas",
        inicial_usuario=session.get("nome", "?")[0].upper(),
    )


@app.route("/tarefas/nova", methods=["POST"])
def criar_tarefa():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    db.criar_tarefa(
        usuario_logado(),
        titulo=request.form["titulo"],
        data_inicio=request.form["data_inicio"],
        data_fim=request.form["data_fim"],
        categoria=request.form.get("categoria"),
    )
    return redirect(url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/concluir", methods=["POST"])
def concluir_tarefa(id_tarefa):
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    db.marcar_tarefa_concluida(id_tarefa)
    return redirect(url_for("tarefas"))


# ============================================================
# DASHBOARD
# ============================================================
@app.route("/dashboard")
def dashboard():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    lista_tarefas = db.listar_tarefas(usuario_logado())
    df = pd.DataFrame(lista_tarefas)

    grafico_html = None
    if not df.empty:
        contagem = df["status"].value_counts().reset_index()
        contagem.columns = ["status", "quantidade"]
        fig = px.bar(contagem, x="status", y="quantidade", title="Tarefas por status")
        grafico_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    return render_template(
        "dashboard.html",
        grafico_html=grafico_html,
        pagina="dashboard",
        titulo_pagina="Dashboard",
        inicial_usuario=session.get("nome", "?")[0].upper(),
    )


if __name__ == "__main__":
    app.run(debug=True)
