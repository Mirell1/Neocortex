"""
NEOCORTEX — app.py (Flask)
O "zelador da casa": decide qual página HTML mostrar, busca os dados
no db.py quando precisa, e entrega a página pronta pro navegador.
"""

import os
import pandas as pd
import plotly.express as px
from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify
from flask_wtf import CSRFProtect
from datetime import datetime
import bcrypt
from flask import Response
import json
import calendar as calendario_lib

import db

app = Flask(__name__)

# Chave usada pelo Flask pra "assinar" o cookie de sessão (quem está
# logado). Em produção, isso também deveria vir do .env — por ora,
# um valor fixo simples já resolve pro MVP.
app.secret_key = os.environ["FLASK_SECRET_KEY"]

csrf = CSRFProtect(app)

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
        return render_template("login.html", erro=None)

    email = request.form.get("email", "").strip()
    senha = request.form.get("senha", "")

    if not email or not senha:
        return render_template("login.html", erro="Preencha e-mail e senha.")

    usuario = db.verificar_login(email, senha)

    if usuario:
        session["id_usuario"] = usuario["id_usuario"]
        session["nome"] = usuario["nome"]
        return redirect(url_for("tarefas"))

    return render_template("login.html", erro="E-mail ou senha errados.")

@app.route("/cadastro/termos")
def cadastro_termos():
    return render_template("cadastro_termos.html")

@app.route("/cadastro/conta", methods=["GET", "POST"])
def cadastro_conta():
    if request.method == "GET":
        return render_template("cadastro_conta.html", erro=None)

    email = request.form.get("email", "").strip()
    senha = request.form.get("senha", "")
    confirmar = request.form.get("confirmar", "")

    erro = None
    if not email or not senha:
        erro = "Preencha e-mail e senha."
    elif senha != confirmar:
        erro = "As senhas não coincidem."
    elif len(senha) < 6:
        erro = "A senha precisa ter pelo menos 6 caracteres."

    if erro:
        return render_template("cadastro_conta.html", erro=erro)

    session["cadastro"] = {"email": email, "senha": senha}
    return redirect(url_for("cadastro_nome"))

@app.route("/cadastro/nome", methods=["GET", "POST"])
def cadastro_nome():
    if "cadastro" not in session:
        return redirect(url_for("cadastro_conta"))

    if request.method == "GET":
        return render_template("cadastro_nome.html", erro=None)

    nome = request.form.get("nome", "").strip()
    if len(nome) < 2:
        return render_template("cadastro_nome.html", erro="Digite um nome válido.")

    session["cadastro"]["nome"] = nome
    session.modified = True
    return redirect(url_for("cadastro_perfil"))


DIAS_ONBOARDING_PARA_DB = {
    "seg": "segunda", "ter": "terca", "qua": "quarta", "qui": "quinta",
    "sex": "sexta", "sab": "sabado", "dom": "domingo",
}

FAIXA_ETARIA_ONBOARDING_PARA_DB = {
    "18_24": "18-24", "25_34": "25-34", "35_44": "35-44", "45_plus": "45+",
}


@app.route("/cadastro/perfil", methods=["GET", "POST"])
def cadastro_perfil():
    if "cadastro" not in session or "nome" not in session["cadastro"]:
        return redirect(url_for("cadastro_conta"))

    if request.method == "GET":
        return render_template("onboarding.html")

    dados = request.get_json(silent=True) or {}

    faixa_etaria = FAIXA_ETARIA_ONBOARDING_PARA_DB.get(dados.get("idade"))
    trabalha = dados.get("trabalha") == "sim"
    estuda = dados.get("estuda") == "sim"
    turno = dados.get("turno_trabalho") or None

    if not faixa_etaria:
        return jsonify({"erro": "Faixa etária inválida."}), 400

    cadastro = session["cadastro"]
    try:
        id_usuario = db.cadastrar_usuario(
            cadastro["nome"], cadastro["email"], cadastro["senha"],
            faixa_etaria, trabalha, estuda, turno,
        )
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    # Rotina de trabalho
    dias_trabalho = dados.get("dias_trabalho") or []
    horario_trabalho = dados.get("horario_trabalho_personalizado") or dados.get("horario_trabalho_estimado")
    if trabalha and dias_trabalho and horario_trabalho:
        for dia in dias_trabalho:
            dia_db = DIAS_ONBOARDING_PARA_DB.get(dia)
            if dia_db:
                db.adicionar_rotina(id_usuario, dia_db, "Trabalho", horario_trabalho["start"], horario_trabalho["end"])

    # Rotina de estudo
    dias_estudo = dados.get("dias_estudo") or []
    horario_estudo = dados.get("horario_estudo")
    if estuda and dias_estudo and horario_estudo:
        for dia in dias_estudo:
            dia_db = DIAS_ONBOARDING_PARA_DB.get(dia)
            if dia_db:
                db.adicionar_rotina(id_usuario, dia_db, "Estudo", horario_estudo["start"], horario_estudo["end"])

    # Hobbies
    for hobby in (dados.get("hobbies") or []):
        if hobby != "personalizado":
            db.associar_hobby(id_usuario, hobby)
    hobby_personalizado = dados.get("hobby_personalizado")
    if hobby_personalizado:
        db.associar_hobby(id_usuario, hobby_personalizado)

    # Preferências e padrões
    if dados.get("areas_melhoria"):
        db.salvar_padrao(id_usuario, "areas_melhoria", ", ".join(dados["areas_melhoria"]))
    if dados.get("tipo_estudo"):
        db.salvar_preferencia(id_usuario, "tipo_estudo", dados["tipo_estudo"])
    if dados.get("frequencia_hobbies"):
        db.salvar_preferencia(id_usuario, "frequencia_hobbies", dados["frequencia_hobbies"])
    if dados.get("sugestoes_hobbies"):
        db.salvar_preferencia(id_usuario, "quer_sugestoes_hobbies", dados["sugestoes_hobbies"])
    if dados.get("tempo_organizacao"):
        db.salvar_padrao(id_usuario, "tempo_organizacao", dados["tempo_organizacao"])
    if dados.get("tempo_neocortex"):
        db.salvar_padrao(id_usuario, "tempo_neocortex", dados["tempo_neocortex"])
    if dados.get("personalizacao"):
        db.registrar_interacao(id_usuario, dados["personalizacao"], tipo="texto", contexto="cadastro_inicial")
    # "personalizacao" (texto livre) é recebida mas propositalmente NÃO
    # é salva ainda — aguardando revisão do Matheus sobre esse campo.

    session.pop("cadastro", None)
    session["id_usuario"] = id_usuario
    session["nome"] = cadastro["nome"]

    return jsonify({"redirect": url_for("cadastro_sucesso")})


@app.route("/cadastro/sucesso")
def cadastro_sucesso():
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    return render_template("cadastro_sucesso.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("tela_login"))


# ============================================================
# TAREFAS
# ============================================================
def tarefas_filtradas(id_usuario, filtro):
    hoje = datetime.now().date()
    todas = db.listar_tarefas(id_usuario)
    if filtro == "hoje":
        return [t for t in todas if t["data_inicio"].date() == hoje]
    if filtro == "proximas":
        return [t for t in todas if t["data_inicio"].date() > hoje]
    return todas


@app.route("/tarefas")
def tarefas():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    filtro = request.args.get("filtro", "hoje")
    categoria_filtro = request.args.get("categoria", "todas")

    lista_tarefas = tarefas_filtradas(usuario_logado(), filtro)
    if categoria_filtro != "todas":
        lista_tarefas = [t for t in lista_tarefas if t["categoria"] == categoria_filtro]

    return render_template(
        "tarefas.html",
        tarefas=lista_tarefas,
        filtro=filtro,
        categoria_filtro=categoria_filtro,
        pagina="tarefas",
        titulo_pagina="Tarefas",
        inicial_usuario=(session.get("nome") or "?")[0].upper(),
    )



@app.route("/tarefas/nova", methods=["POST"])
def criar_tarefa():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    titulo = request.form.get("titulo", "").strip()
    data_inicio_data = request.form.get("data_inicio_data", "")
    data_fim_data = request.form.get("data_fim_data", "")
    categoria = request.form.get("categoria")

    data_inicio = f"{data_inicio_data}T{request.form.get('data_inicio_h','')}:{request.form.get('data_inicio_m','')}"
    data_fim = f"{data_fim_data}T{request.form.get('data_fim_h','')}:{request.form.get('data_fim_m','')}"

    erro = None
    if not titulo or not data_inicio_data or not data_fim_data:
        erro = "Preencha título, início e fim da tarefa."
    else:
        try:
            inicio_dt = datetime.fromisoformat(data_inicio)
            fim_dt = datetime.fromisoformat(data_fim)
            if fim_dt <= inicio_dt:
                erro = "O horário de fim precisa ser depois do horário de início."
        except ValueError:
            erro = "Data ou horário inválido."

    if erro:
        lista_tarefas = tarefas_filtradas(usuario_logado(), "hoje")
        return render_template(
            "tarefas.html", tarefas=lista_tarefas, pagina="tarefas",
            titulo_pagina="Tarefas",
            inicial_usuario=(session.get("nome") or "?")[0].upper(),
            erro=erro,
        )

    db.criar_tarefa(usuario_logado(), titulo=titulo, data_inicio=data_inicio, data_fim=data_fim, categoria=categoria)
    return redirect(url_for("tarefas"))

@app.route("/tarefas/<int:id_tarefa>/concluir", methods=["POST"])
def concluir_tarefa(id_tarefa):
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    linhas_afetadas = db.marcar_tarefa_concluida(id_tarefa, usuario_logado())
    if linhas_afetadas == 0:
        abort(404)

    return redirect(request.referrer or url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/desfazer", methods=["POST"])
def desfazer_tarefa(id_tarefa):
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    linhas_afetadas = db.desfazer_conclusao_tarefa(id_tarefa, usuario_logado())
    if linhas_afetadas == 0:
        abort(404)

    return redirect(request.referrer or url_for("tarefas"))

DIAS_SEMANA_VALIDOS = {"segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"}

DIAS_SEMANA_ORDEM = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
DIAS_SEMANA_LABEL = {"segunda": "Segunda", "terca": "Terça", "quarta": "Quarta",
                      "quinta": "Quinta", "sexta": "Sexta", "sabado": "Sábado", "domingo": "Domingo"}


def agrupar_rotina(lista_rotina):
    grupos = {}
    for r in lista_rotina:
        chave = (r["descricao"], r["hora_inicio"], r["hora_fim"])
        grupos.setdefault(chave, {
            "descricao": r["descricao"], "hora_inicio": r["hora_inicio"],
            "hora_fim": r["hora_fim"], "dias": [], "ids": [],
        })
        grupos[chave]["dias"].append(r["dia_semana"])
        grupos[chave]["ids"].append(r["id_rotina"])

    resultado = []
    for g in grupos.values():
        dias_ordenados = sorted(g["dias"], key=lambda d: DIAS_SEMANA_ORDEM.index(d))
        g["dias_label"] = ", ".join(DIAS_SEMANA_LABEL[d] for d in dias_ordenados)
        resultado.append(g)
    return resultado

COR_POR_STATUS = {
    "pendente": "#255DC5",       # dourado suave — "está na sua lista", sem urgência
    "em_andamento": "#DCBD21",   # azul acinzentado — calmo, "em curso"
    "concluida": "#4CC76F",      # verde salva, suave — conquista sem euforia forçada
    "cancelada": "#A8B0BB",      # cinza neutro — sem julgamento
}
COR_ATRASADA = "#8D1EB9"         # terracota empoeirado — chama atenção sem alarmar

app.jinja_env.globals["COR_POR_STATUS"] = COR_POR_STATUS

def status_visual(tarefa):
    agora = datetime.now()

    if tarefa["status"] == "concluida":
        return "concluída", COR_POR_STATUS["concluida"]
    if tarefa["status"] == "cancelada":
        return "cancelada", COR_POR_STATUS["cancelada"]
    if tarefa["data_fim"] < agora:
        return "atrasada", COR_ATRASADA
    if tarefa["data_inicio"] <= agora <= tarefa["data_fim"]:
        return "em andamento", COR_POR_STATUS["em_andamento"]
    return "pendente", COR_POR_STATUS["pendente"]


app.jinja_env.globals["status_visual"] = status_visual


@app.route("/tarefas/<int:id_tarefa>/editar", methods=["POST"])
def editar_tarefa(id_tarefa):
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    titulo = request.form.get("titulo", "").strip()
    data_inicio_data = request.form.get("data_inicio_data", "")
    data_fim_data = request.form.get("data_fim_data", "")
    categoria = request.form.get("categoria")

    data_inicio = f"{data_inicio_data}T{request.form.get('data_inicio_h','')}:{request.form.get('data_inicio_m','')}"
    data_fim = f"{data_fim_data}T{request.form.get('data_fim_h','')}:{request.form.get('data_fim_m','')}"

    erro = None
    if not titulo or not data_inicio_data or not data_fim_data:
        erro = "Preencha título, início e fim da tarefa."
    else:
        try:
            inicio_dt = datetime.fromisoformat(data_inicio)
            fim_dt = datetime.fromisoformat(data_fim)
            if fim_dt <= inicio_dt:
                erro = "O horário de fim precisa ser depois do horário de início."
        except ValueError:
            erro = "Data ou horário inválido."

    if erro:
        lista_tarefas = tarefas_filtradas(usuario_logado(), "hoje")
        return render_template(
            "tarefas.html", tarefas=lista_tarefas, pagina="tarefas",
            titulo_pagina="Tarefas",
            inicial_usuario=(session.get("nome") or "?")[0].upper(),
            erro=erro,
        )

    linhas_afetadas = db.atualizar_tarefa(
        id_tarefa, usuario_logado(),
        titulo=titulo, data_inicio=data_inicio, data_fim=data_fim, categoria=categoria,
    )
    if linhas_afetadas == 0:
        abort(404)

    return redirect(url_for("tarefas"))

@app.route("/tarefas/<int:id_tarefa>/excluir", methods=["POST"])
def excluir_tarefa(id_tarefa):
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    linhas_afetadas = db.deletar_tarefa(id_tarefa, usuario_logado())
    if linhas_afetadas == 0:
        abort(404)

    return redirect(url_for("tarefas"))


# ============================================================
# ROTINA FIXA
# ============================================================
@app.route("/rotina")
def rotina():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    rotina_agrupada = agrupar_rotina(db.listar_rotina(usuario_logado()))
    return render_template(
        "rotina.html",
        rotina=rotina_agrupada,
        pagina="rotina",
        titulo_pagina="Rotina Fixa",
        inicial_usuario=(session.get("nome") or "?")[0].upper(),
    )


@app.route("/rotina/nova", methods=["POST"])
def adicionar_rotina_rota():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    dias_semana = request.form.getlist("dia_semana")
    descricao = request.form.get("descricao", "").strip()
    hora_inicio = f"{request.form.get('hora_inicio_h','')}:{request.form.get('hora_inicio_m','')}"
    hora_fim = f"{request.form.get('hora_fim_h','')}:{request.form.get('hora_fim_m','')}"

    erro = None
    dias_invalidos = [d for d in dias_semana if d not in DIAS_SEMANA_VALIDOS]
    if not dias_semana or dias_invalidos:
        erro = "Selecione ao menos um dia da semana válido."
    elif not descricao:
        erro = "Preencha a descrição."
    elif hora_fim <= hora_inicio:
        erro = "O horário de fim precisa ser depois do horário de início."

    if erro:
        lista_rotina = agrupar_rotina(db.listar_rotina(usuario_logado()))
        return render_template(
            "rotina.html", rotina=lista_rotina, pagina="rotina",
            titulo_pagina="Rotina Fixa",
            inicial_usuario=(session.get("nome") or "?")[0].upper(),
            erro=erro,
        )

    for dia in dias_semana:
        db.adicionar_rotina(usuario_logado(), dia, descricao, hora_inicio, hora_fim)

    return redirect(url_for("rotina"))

@app.route("/rotina/grupo/excluir", methods=["POST"])
def excluir_grupo_rotina():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    ids = request.form.getlist("id_rotina")
    for id_str in ids:
        db.deletar_rotina(int(id_str), usuario_logado())

    return redirect(url_for("rotina"))


# ============================================================
# DASHBOARD
# ============================================================


DIAS_SEMANA_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                   "sexta-feira", "sábado", "domingo"]

@app.route("/dashboard")
def dashboard():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    hoje = datetime.now().date()
    hoje_formatado = f"{DIAS_SEMANA_PT[hoje.weekday()]}, {hoje.day} de {MESES_PT[hoje.month - 1].lower()}"

    todas_tarefas = db.listar_tarefas(usuario_logado())
    tarefas_hoje = [t for t in todas_tarefas if t["data_inicio"].date() == hoje]

    total = len(tarefas_hoje)
    concluidas = len([t for t in tarefas_hoje if t["status"] == "concluida"])
    pct = round((concluidas / total) * 100) if total else 0

    return render_template(
        "dashboard.html",
        tarefas=tarefas_hoje,
        total=total, concluidas=concluidas, pct=pct,
        hoje_formatado=hoje_formatado,
        pagina="dashboard",
        titulo_pagina=f"Olá, {session.get('nome', '?')} 👋",
        inicial_usuario=(session.get("nome") or "?")[0].upper(),
    )


# ============================================================
# CALENDÁRIO
# ============================================================

MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
            "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

PYTHON_WEEKDAY_PARA_DIA_SEMANA = {
    0: "segunda", 1: "terca", 2: "quarta", 3: "quinta",
    4: "sexta", 5: "sabado", 6: "domingo",
}


@app.route("/calendario")
def calendario():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    hoje = datetime.now()
    ano = request.args.get("ano", type=int) or hoje.year
    mes = request.args.get("mes", type=int) or hoje.month

    cal = calendario_lib.Calendar(firstweekday=6)  # semana começa no domingo
    semanas = cal.monthdayscalendar(ano, mes)

    eventos_por_dia = {}

    for t in db.listar_tarefas(usuario_logado()):
        if t["data_inicio"].year == ano and t["data_inicio"].month == mes:
            dia = t["data_inicio"].day
            _,  cor_status = status_visual(t)
            eventos_por_dia.setdefault(dia, []).append({
                "label": t["titulo"],
                "cor": t["cor"] or cor_status,
        })

    for r in db.listar_rotina(usuario_logado()):
        for semana in semanas:
            for dia in semana:
                if dia == 0:
                    continue
                data_do_dia = datetime(ano, mes, dia)
                if PYTHON_WEEKDAY_PARA_DIA_SEMANA[data_do_dia.weekday()] == r["dia_semana"]:
                    eventos_por_dia.setdefault(dia, []).append({
                        "label": r["descricao"],
                        "cor": "#94A3B8",
                    })

    mes_anterior, ano_anterior = (12, ano - 1) if mes == 1 else (mes - 1, ano)
    mes_seguinte, ano_seguinte = (1, ano + 1) if mes == 12 else (mes + 1, ano)

    return render_template(
        "calendario.html",
        semanas=semanas,
        eventos_por_dia=eventos_por_dia,
        mes_nome=MESES_PT[mes - 1],
        mes=mes, ano=ano,
        hoje_dia=hoje.day, hoje_mes=hoje.month, hoje_ano=hoje.year,
        mes_anterior=mes_anterior, ano_anterior=ano_anterior,
        mes_seguinte=mes_seguinte, ano_seguinte=ano_seguinte,
        pagina="calendario",
        titulo_pagina="Agenda",
        inicial_usuario=(session.get("nome") or "?")[0].upper(),
    )

#================================================
#ASSISTENTE
#================================================

@app.route("/assistente")
def assistente():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    mensagens = list(reversed(
        db.listar_interacoes(usuario_logado(), contexto="interacao_geral", limite=50)
    ))
    return render_template(
        "assistente.html",
        mensagens=mensagens,
        pagina="assistente",
        titulo_pagina="Assistente",
        inicial_usuario=(session.get("nome") or "?")[0].upper(),
    )


@app.route("/assistente/enviar", methods=["POST"])
def enviar_mensagem():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    texto = request.form.get("mensagem", "").strip()
    if texto:
        db.registrar_interacao(usuario_logado(), texto)

    return redirect(url_for("assistente"))

#==================================================================
# CONFIGURAÇÕES
#==================================================================


@app.route("/configuracoes")
def configuracoes():
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    return render_template(
        "configuracoes.html",
        pagina="configuracoes",
        titulo_pagina="Configurações",
        inicial_usuario=(session.get("nome") or "?")[0].upper(),
    )


@app.route("/configuracoes/perfil", methods=["POST"])
def atualizar_perfil():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    nome = request.form.get("nome", "").strip()
    if len(nome) < 2:
        return redirect(url_for("configuracoes"))

    db.atualizar_usuario(usuario_logado(), nome=nome)
    session["nome"] = nome
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/senha", methods=["POST"])
def trocar_senha_rota():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    senha_atual = request.form.get("senha_atual", "")
    nova_senha = request.form.get("nova_senha", "")

    usuario = db.buscar_usuario(usuario_logado())
    if not usuario or not bcrypt.checkpw(senha_atual.encode("utf-8"), usuario["senha_hash"].encode("utf-8")):
        return redirect(url_for("configuracoes", erro="senha_atual"))

    if len(nova_senha) < 6:
        return redirect(url_for("configuracoes", erro="senha_curta"))

    db.trocar_senha(usuario_logado(), nova_senha)
    return redirect(url_for("configuracoes", sucesso="senha"))


@app.route("/configuracoes/exportar")
def exportar_dados():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    payload = {
        "nome": session.get("nome"),
        "email": session.get("email"),
        "exportado_em": datetime.now().isoformat(),
        "tarefas": [
            {
                "titulo": t["titulo"], "categoria": t["categoria"], "status": t["status"],
                "data_inicio": t["data_inicio"].isoformat(), "data_fim": t["data_fim"].isoformat(),
            }
            for t in db.listar_tarefas(usuario_logado())
        ],
        "rotina_fixa": [
            {"descricao": r["descricao"], "dia_semana": r["dia_semana"],
             "hora_inicio": r["hora_inicio"], "hora_fim": r["hora_fim"]}
            for r in db.listar_rotina(usuario_logado())
        ],
    }

    return Response(
        json.dumps(payload, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=neocortex-dados.json"},
    )


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


def excluir_usuario(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
            return cur.rowcount

        
@app.route("/configuracoes/notificacoes", methods=["POST"])
def salvar_notificacoes():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    ativado = request.form.get("notificacoes_ativas") == "on"
    db.salvar_preferencia(usuario_logado(), "notificacoes_ativas", "true" if ativado else "false")
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/excluir-conta", methods=["POST"])
def excluir_conta():
    if not usuario_logado():
        return redirect(url_for("tela_login"))

    senha_atual = request.form.get("senha_atual", "")
    usuario = db.buscar_usuario(usuario_logado())
    if not usuario or not bcrypt.checkpw(senha_atual.encode("utf-8"), usuario["senha_hash"].encode("utf-8")):
        return redirect(url_for("configuracoes", erro="senha_atual"))

    db.excluir_usuario(usuario_logado())
    session.clear()
    return redirect(url_for("tela_login"))

if __name__ == "__main__":

    app.run(debug=True)