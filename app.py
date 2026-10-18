"""
NEOCORTEX — app.py (Flask)

Decide qual página mostrar e entrega a página pronta. NÃO contém regra de
negócio: criar/editar/concluir tarefas e rotina passam por servicos.py (as
mesmas funções que a IA usa) e o calendário vem de agenda.py (a mesma agenda que
a IA consulta).
"""

import json
import math
import os
import time
import calendar as calendario_lib
from functools import wraps
from datetime import date, datetime, timedelta


import bcrypt
from flask import Flask, Response, abort, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

import agenda
import ai
import db
import servicos
import decisao
import seguranca

import markdown as markdown_lib
import bleach

app = Flask(__name__)

# Chave que assina o cookie de sessão. Vem do .env (gere com: python -c "import secrets; print(secrets.token_hex(32))").
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",   # use 1 em produção (HTTPS)
)

csrf = CSRFProtect(app)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024    # [SEGURANÇA] nenhuma tela envia arquivo: recusa corpos grandes (erro 413)

# [SEGURANÇA] Atrás de um proxy (ex.: Render) o IP real vem em X-Forwarded-For. Só confiamos nesse cabeçalho com NEOCORTEX_PROXY=1:
# sem o proxy, qualquer pessoa poderia forjá-lo e escapar do limite de tentativas de login.
if os.getenv("NEOCORTEX_PROXY", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# [SEGURANÇA] Limite de tentativas de login (janela de 15 minutos): por conta+IP e, mais folgado, por IP (quem testa várias contas).
LOGIN_MAX_TENTATIVAS = int(os.getenv("LOGIN_MAX_TENTATIVAS", "5"))
LOGIN_ATRASO_MINIMO = float(os.getenv("LOGIN_ATRASO_MINIMO", "0.4"))   # toda falha demora pelo menos isso (esconde se o e-mail existe)
LIMITE_LOGIN = seguranca.LimiteTentativas(maximo=LOGIN_MAX_TENTATIVAS, janela=900)
LIMITE_LOGIN_IP = seguranca.LimiteTentativas(maximo=4 * LOGIN_MAX_TENTATIVAS, janela=900)

# Conflito de agenda na tela:
#   confirmar (padrão) = mostra o conflito e só salva se o usuário confirmar (igual à IA)
#   avisar             = salva mesmo assim
CONFLITO_UI_MODO = os.getenv("NEOCORTEX_CONFLITO_UI", "confirmar").strip().lower()

GAMIFICACAO_ATIVA = os.getenv("NEOCORTEX_GAMIFICACAO", "1") == "1"
INTENSIDADES_MASCOTE = {"completa", "reduzida", "desligada"}

FAIXAS_ETARIAS_VALIDAS = {"18-24", "25-34", "35-44", "45+"}   # igual ao CHECK do banco
OCUPACOES_VALIDAS = {"trabalha", "estuda", "ambos", "nenhum"}
TURNOS_VALIDOS = {"manha", "tarde", "noite", "intermediario", "personalizado"}
ENERGIAS_VALIDAS = {"manha", "tarde", "noite", "nao_sei"}
_VERDADEIRO = {"1", "true", "on", "sim", "yes"}

MAX_CARACTERES_MENSAGEM = 1000

DIAS_SEMANA_VALIDOS = set(agenda.DIAS_SEMANA)
DIAS_SEMANA_ORDEM = list(agenda.DIAS_SEMANA)
DIAS_SEMANA_LABEL = {"segunda": "Segunda", "terca": "Terça", "quarta": "Quarta",
                     "quinta": "Quinta", "sexta": "Sexta", "sabado": "Sábado", "domingo": "Domingo"}
DIAS_SEMANA_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                  "sexta-feira", "sábado", "domingo"]
MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
            "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

COR_POR_STATUS = {
    "pendente": "#2563EB",
    "em_andamento": "#F59E0B",
    "concluida": "#22C55E",
    "cancelada": "#9CA3AF",
}
COR_COMPROMISSO = "#8B5CF6"
COR_ROTINA = "#94A3B8"

COR_ATRASADA = "#C98A82"  # terracota suave — mesmo princípio de "sem alarme" de antes


# [TEMA] catálogo de temas. O padrão é sempre liberado; os outros são recompensa.
TEMAS = {
    "padrao": {"nome": "Padrão", "mascote": "robo", "mascote_nome": "Robô",
               "descricao": "O visual original do NEOCORTEX.", "como_liberar": ""},
    # [TEMA] cada tema tem 2 versões: 1 = simples (cores e tipografia), 2 = completa (mascote,
    # semana temática, vocabulário e falas). Cada área do sistema libera o seu tema.
    "cafeteria": {"nome": "Cafeteria", "mascote": "grao", "mascote_nome": "Grão", "area": "Objetivos",
                  "descricao": "Tons de café e o Grão como mascote.",
                  "como_liberar": "Crie seu primeiro objetivo para liberar.",
                  "como_completar": "Divida um objetivo em fragmentos para liberar a versão completa, com o Grão."},
    "campeonato": {"nome": "Campeonato", "mascote": "boltz", "mascote_nome": "Boltz", "area": "Tarefas",
                   "descricao": "Futebol: verde e dourado, com o Boltz como mascote.",
                   "como_liberar": "Conclua todas as tarefas de um dia para liberar.",
                   "como_completar": "Remarque uma tarefa atrasada em vez de deixá-la pra trás para liberar a versão completa, com o Boltz."},
    "papelaria": {"nome": "Papelaria", "mascote": "rabisco", "mascote_nome": "Rabisco", "area": "Rotina Fixa",
                  "descricao": "Papel, canetas e marca-texto, com o Rabisco como mascote.",
                  "como_liberar": "Monte uma rotina fixa com blocos em pelo menos 3 dias da semana para liberar.",
                  "como_completar": "Mantenha sua rotina montada por 7 dias para liberar a versão completa, com o Rabisco."},
}

# [PERSONALIZAR] paleta de cores do mascote. "padrao" não muda nada: cada mascote mantém a cor dele.
# A cor pinta os detalhes que brilham (luzes do robô, faixa do Grão, costuras e chuteiras do Boltz).
CORES_MASCOTE = [
    {"id": "padrao",  "nome": "Original", "cor": "",        "brilho": ""},
    {"id": "azul",    "nome": "Azul",     "cor": "#3B82F6", "brilho": "#DBEAFE"},
    {"id": "verde",   "nome": "Verde",    "cor": "#18A575", "brilho": "#D8EFE5"},
    {"id": "rosa",    "nome": "Rosa",     "cor": "#E0629A", "brilho": "#FBD5E5"},
    {"id": "laranja", "nome": "Laranja",  "cor": "#E8892B", "brilho": "#FDE6CC"},
    {"id": "roxo",    "nome": "Roxo",     "cor": "#8C7BFF", "brilho": "#D3CCFF"},
]

# [TEMA] só para gravar a apresentação: libera todos os temas e acessórios. Nunca em produção.
MODO_DEMO = os.getenv("NEOCORTEX_DEMO", "0") == "1"
if MODO_DEMO and app.config["SESSION_COOKIE_SECURE"]:
    raise RuntimeError("NEOCORTEX_DEMO=1 não pode ser usado com SESSION_COOKIE_SECURE=1 (produção).")


def status_visual(tarefa):
    agora = datetime.now()

    if tarefa["status"] in ("concluida", "cancelada", "em_andamento"):
        label = {"concluida": "concluída", "em_andamento": "em andamento", "cancelada": "cancelada"}[tarefa["status"]]
        return label, COR_POR_STATUS[tarefa["status"]]

    if tarefa["data_fim"] < agora:
        return "atrasada", COR_ATRASADA

    return "pendente", COR_POR_STATUS["pendente"]


app.jinja_env.globals["status_visual"] = status_visual


# ============================================================
# AUXILIARES
# ============================================================
def usuario_logado():
    """Devolve o id do usuário logado, ou None se ninguém estiver logado."""
    return session.get("id_usuario")


@app.route("/favicon.ico")
def favicon():
    """Ícone da aba. Rota PÚBLICA: o navegador pede /favicon.ico sozinho, inclusive nas telas de login e cadastro."""
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon", max_age=86400)


# status como o usuário lê: "em_andamento" -> "em andamento". Uso nos templates: {{ objetivo.status|status_legivel }}
STATUS_LEGIVEL = {
    "em_andamento": "em andamento", "concluido": "concluído", "concluida": "concluída", "pausado": "pausado", "pausada": "pausada",
    "cancelado": "cancelado", "cancelada": "cancelada", "pendente": "pendente",
}


@app.template_filter("status_legivel")
def status_legivel(valor):
    texto = "" if valor is None else str(valor)
    return STATUS_LEGIVEL.get(texto, texto.replace("_", " "))


@app.after_request
def _cabecalhos_de_seguranca(resposta):
    return seguranca.aplicar_cabecalhos(resposta, https=app.config["SESSION_COOKIE_SECURE"], endpoint=request.endpoint)


def _quer_json():
    return request.path.startswith("/api/") or request.is_json or request.accept_mimetypes.best == "application/json"


def _pagina_de_erro(codigo, titulo, mensagem):
    """Erro amigável, sem detalhe técnico. Renderiza sem os context processors: eles consultam o banco e o erro pode ser o próprio banco."""
    if _quer_json():
        return jsonify({"erro": mensagem}), codigo
    destino = url_for("dashboard") if usuario_logado() else url_for("tela_login")
    html = app.jinja_env.get_template("erro.html").render(codigo=codigo, titulo=titulo, mensagem=mensagem, destino=destino)
    return make_response(html, codigo)


@app.errorhandler(404)
def _erro_404(_e):
    return _pagina_de_erro(404, "Página não encontrada", "O endereço que você abriu não existe ou foi movido.")


@app.errorhandler(405)
def _erro_405(_e):
    return _pagina_de_erro(405, "Ação não permitida", "Esse endereço não aceita esse tipo de acesso.")


@app.errorhandler(413)
def _erro_413(_e):
    return _pagina_de_erro(413, "Envio grande demais", "O que você enviou passou do tamanho permitido.")


@app.errorhandler(429)
def _erro_429(_e):
    return _pagina_de_erro(429, "Muitas tentativas", "Aguarde um pouco e tente de novo.")


@app.errorhandler(CSRFError)
def _erro_csrf(_e):
    return _pagina_de_erro(400, "Sua sessão de segurança expirou", "Volte, recarregue a página e tente de novo.")


@app.errorhandler(500)
def _erro_500(_e):
    return _pagina_de_erro(500, "Algo deu errado do nosso lado", "O problema foi registrado. Tente de novo em instantes.")


def login_obrigatorio(rota):
    @wraps(rota)
    def protegida(*args, **kwargs):
        if not usuario_logado():
            return redirect(url_for("tela_login"))
        return rota(*args, **kwargs)
    return protegida


def _inicial():
    return (session.get("nome") or "?")[0].upper()


def _pagina(pagina, titulo, **extra):
    """Variáveis que todo template de página logada recebe."""
    return {"pagina": pagina, "titulo_pagina": titulo, "inicial_usuario": _inicial(), **extra}


def _confirmou_conflito():
    return CONFLITO_UI_MODO == "avisar" or request.form.get("confirmar_conflito") in _VERDADEIRO


def _mascote_evento(tipo, **dados):
    """[MASCOTE] Guarda uma reação pra próxima página mostrar (as rotas terminam em redirect)."""
    if not GAMIFICACAO_ATIVA:
        return
    fila = session.get("mascote_eventos", [])
    fila.append({"tipo": tipo, "dados": dados})
    session["mascote_eventos"] = fila[-3:]   # nunca acumula mais que 3


NIVEL_SIMPLES, NIVEL_COMPLETO = 1, 2

# [INTERFACE] A interface CLÁSSICA (a original do NEOCORTEX) é a base de todo mundo. A IMERSIVA (semana desenhada,
# mascote no cartão de boas-vindas, vocabulário do tema) é um prêmio adicional: libera com 100 pontos
# (nível "Pegando o ritmo"), nunca volta a bloquear, liga sozinha e a pessoa pode voltar à clássica em Configurações.
PONTOS_INTERFACE_IMERSIVA = 100


def _nivel_tema(id_usuario, tid):
    """[TEMA] 0 = bloqueado, 1 = versão simples, 2 = versão completa.
    O padrão é sempre completo. Compatibilidade: quem já tinha o tema liberado pelas regras
    antigas (que hoje são as da versão completa) fica com o nível 2."""
    if tid == "padrao" or MODO_DEMO:
        return NIVEL_COMPLETO
    nivel = db.buscar_preferencia(id_usuario, f"tema_{tid}_nivel")
    if nivel in ("1", "2"):
        return int(nivel)
    if db.buscar_preferencia(id_usuario, f"tema_{tid}_liberado") == "true":
        return NIVEL_COMPLETO
    return 0


def _temas_liberados(id_usuario):
    """[TEMA] {tema: nível} só com os temas que a pessoa já pode usar."""
    niveis = {tid: _nivel_tema(id_usuario, tid) for tid in TEMAS}
    return {tid: n for tid, n in niveis.items() if n >= NIVEL_SIMPLES}


def _liberar_tema(id_usuario, tid, nivel=NIVEL_COMPLETO):
    """[TEMA] Sobe o tema para o nível pedido (nunca desce) e avisa pelo mascote.
    Liberar a versão completa já inclui a simples."""
    if not GAMIFICACAO_ATIVA or _nivel_tema(id_usuario, tid) >= nivel:
        return
    db.salvar_preferencia(id_usuario, f"tema_{tid}_nivel", str(nivel))
    if nivel >= NIVEL_COMPLETO:   # a marca antiga "_liberado" sempre significou a versão completa: não grava na simples
        db.salvar_preferencia(id_usuario, f"tema_{tid}_liberado", "true")
    nome = TEMAS[tid]["nome"]
    item = f"Tema {nome}" if nivel == NIVEL_SIMPLES else f"Tema {nome} completo, com o {TEMAS[tid]['mascote_nome']}"
    _mascote_evento("conquista", item=item)


def _tema_imersivo(id_usuario, tema):
    """[TEMA] O tema ativo está na versão completa? (o padrão sempre está)"""
    return _nivel_tema(id_usuario, tema) >= NIVEL_COMPLETO


def _skin_atual(id_usuario):
    """[TEMA] Mascote em uso: o do tema só na versão completa; na simples, continua o robô."""
    tema = _tema_atual(id_usuario)
    return TEMAS[tema]["mascote"] if _tema_imersivo(id_usuario, tema) else "robo"


def _tema_atual(id_usuario):
    """[TEMA] Tema escolhido, já validado: tema bloqueado ou inválido volta ao padrão."""
    tema = db.buscar_preferencia(id_usuario, "tema_visual") or "padrao"
    return tema if tema in _temas_liberados(id_usuario) else "padrao"


def _chave_mascote(base, skin):
    """[PERSONALIZAR] Cada mascote guarda a sua personalização. O robô mantém a chave antiga
    (quem já tinha acessório equipado não perde nada); os outros ganham um sufixo."""
    return base if skin == "robo" else f"{base}_{skin}"


def _cor_do_mascote(id_usuario, skin):
    cor_id = db.buscar_preferencia(id_usuario, _chave_mascote("mascote_cor", skin)) or "padrao"
    return next((c for c in CORES_MASCOTE if c["id"] == cor_id), CORES_MASCOTE[0])


def _interface_imersiva_liberada(id_usuario, pontos):
    """[INTERFACE] A interface imersiva já foi liberada? Libera uma vez (100 pontos) e nunca volta a bloquear,
    mesmo que os pontos caiam depois (por exemplo, ao desfazer uma tarefa)."""
    if not GAMIFICACAO_ATIVA:
        return False
    if MODO_DEMO or db.buscar_preferencia(id_usuario, "interface_imersiva_liberada") == "true":
        return True
    if pontos >= PONTOS_INTERFACE_IMERSIVA:
        db.salvar_preferencia(id_usuario, "interface_imersiva_liberada", "true")
        _mascote_evento("conquista", item="Interface imersiva, com a rede da semana")
        return True
    return False


def _interface_imersiva_disponivel(id_usuario, pontos=None):
    """[INTERFACE] Disponível com 100 pontos OU porque o tema ativo é um tema de RECOMPENSA na versão completa
    (a tela temática daquele tema faz parte da recompensa dele). O padrão nasce completo para todos,
    então ele NÃO conta aqui: para o padrão, a imersiva só vem pelos pontos."""
    pontos = db.calcular_pontos_mascote(id_usuario) if pontos is None else pontos
    tema = _tema_atual(id_usuario)
    return _interface_imersiva_liberada(id_usuario, pontos) or (tema != "padrao" and _tema_imersivo(id_usuario, tema))


def _verificar_desbloqueio_cafeteria(id_usuario):
    """[TEMA] Cafeteria (área Objetivos): versão simples com o primeiro objetivo;
    versão completa quando algum objetivo tem pelo menos um fragmento."""
    if not GAMIFICACAO_ATIVA or _nivel_tema(id_usuario, "cafeteria") >= NIVEL_COMPLETO:
        return
    objetivos = db.listar_objetivos(id_usuario)
    if any(db.listar_fragmentos_objetivo(o["id_objetivo"], id_usuario) for o in objetivos):
        _liberar_tema(id_usuario, "cafeteria", NIVEL_COMPLETO)
    elif objetivos:
        _liberar_tema(id_usuario, "cafeteria", NIVEL_SIMPLES)


DIAS_ROTINA_PARA_PAPELARIA = 3      # versão simples: rotina cobrindo 3 dias da semana
DIAS_ROTINA_MONTADA_COMPLETA = 7    # versão completa: rotina montada há 7 dias (o tempo faz o trabalho)


def _verificar_desbloqueio_papelaria(id_usuario):
    """[TEMA] Papelaria (área Rotina Fixa). A rotina não tem "concluir", ela se consolida com o tempo:
    - simples: rotina com blocos em pelo menos 3 dias diferentes (marco de planejamento);
    - completa: essa rotina montada há 7 dias. Não exige entrar no app todo dia e nunca zera."""
    if not GAMIFICACAO_ATIVA or _nivel_tema(id_usuario, "papelaria") >= NIVEL_COMPLETO:
        return
    montada_em = db.buscar_preferencia(id_usuario, "rotina_montada_em")
    if not montada_em:
        dias = {r["dia_semana"] for r in db.listar_rotina(id_usuario)}
        if len(dias) < DIAS_ROTINA_PARA_PAPELARIA:
            return
        montada_em = datetime.now().date().isoformat()
        db.salvar_preferencia(id_usuario, "rotina_montada_em", montada_em)
        _liberar_tema(id_usuario, "papelaria", NIVEL_SIMPLES)
    try:
        dias_montada = (datetime.now().date() - date.fromisoformat(montada_em)).days
    except ValueError:
        return
    if dias_montada >= DIAS_ROTINA_MONTADA_COMPLETA:
        _liberar_tema(id_usuario, "papelaria", NIVEL_COMPLETO)


# ============================================================
# ROTA INICIAL
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

    inicio = time.perf_counter()
    email = request.form.get("email", "").strip()[:254]
    senha = request.form.get("senha", "")

    if not email or not senha:
        return render_template("login.html", erro="Preencha e-mail e senha.")

    ip = request.remote_addr or "desconhecido"
    chave_da_conta, chave_do_ip = seguranca.chave_conta(ip, email), f"ip:{ip}"
    espera = max(LIMITE_LOGIN.espera(chave_da_conta), LIMITE_LOGIN_IP.espera(chave_do_ip))
    if espera:   # bloqueado: nem consulta o banco nem confere a senha (vale mesmo que ela esteja certa)
        minutos = max(1, math.ceil(espera / 60))
        resposta = make_response(render_template("login.html", erro=f"Muitas tentativas seguidas. Aguarde {minutos} minuto(s) e tente de novo."), 429)
        resposta.headers["Retry-After"] = str(espera)
        return resposta

    # o bcrypt só aceita até 72 bytes: acima disso não pode ser a senha de ninguém (e não deve virar erro 500)
    usuario = db.verificar_login(email, senha) if len(senha.encode("utf-8")) <= seguranca.SENHA_MAX_BYTES else None
    if usuario:
        LIMITE_LOGIN.limpar(chave_da_conta)   # acertou: zera os erros dessa conta (o contador do IP continua)
        session.clear()   # não reaproveita sessão anterior
        session["id_usuario"] = usuario["id_usuario"]
        session["nome"] = usuario["nome"]
        try:
            db.apagar_eventos_antigos()
        except Exception:
            app.logger.exception("Falha na limpeza de retenção (não bloqueia o login)")
        return redirect(url_for("tarefas"))

    LIMITE_LOGIN.registrar_falha(chave_da_conta)
    LIMITE_LOGIN_IP.registrar_falha(chave_do_ip)
    sobra = LOGIN_ATRASO_MINIMO - (time.perf_counter() - inicio)
    if sobra > 0:
        time.sleep(sobra)   # e-mail inexistente (sem bcrypt) e senha errada (com bcrypt) passam a demorar parecido
    return render_template("login.html", erro="E-mail ou senha errados.")


def _ler_perfil(form):
    """
    Lê faixa etária, ocupação e turno do formulário. Retorna
    (faixa_etaria, trabalha, estuda, turno, erro).

    Ocupação aceita os dois jeitos: o campo 'ocupacao' (trabalha | estuda | ambos |
    nenhum) ou as caixas independentes 'trabalha' e 'estuda' (dá para ser os dois).
    """
    faixa_etaria = form.get("faixa_etaria", "").strip()
    turno = (form.get("turno") or "").strip() or None
    ocupacao = form.get("ocupacao", "").strip()

    trabalha = form.get("trabalha") in _VERDADEIRO
    estuda = form.get("estuda") in _VERDADEIRO
    if ocupacao in OCUPACOES_VALIDAS:
        trabalha = trabalha or ocupacao in ("trabalha", "ambos")
        estuda = estuda or ocupacao in ("estuda", "ambos")
        informou_ocupacao = True
    else:
        informou_ocupacao = trabalha or estuda or form.get("nenhuma_ocupacao") in _VERDADEIRO

    erro = None
    if faixa_etaria not in FAIXAS_ETARIAS_VALIDAS:
        erro = "Selecione sua faixa etária."
    elif not informou_ocupacao:
        erro = "Selecione sua ocupação."
    elif turno is not None and turno not in TURNOS_VALIDOS:
        erro = "Selecione um turno válido."
    return faixa_etaria, trabalha, estuda, turno, erro


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
    elif (problema_senha := seguranca.senha_valida(senha)):
        erro = problema_senha
    elif db.email_existe(email):
        erro = "Já existe um usuário cadastrado com esse e-mail."

    if erro:
        return render_template("cadastro_conta.html", erro=erro)

    # O cookie de sessão é só ASSINADO, não criptografado: quem o abre lê o conteúdo.
    # Por isso guardamos o hash bcrypt, nunca a senha.
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    session["cadastro"] = {"email": email, "senha_hash": senha_hash}
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
    dados_sessao = session.get("cadastro") or {}
    if not all(chave in dados_sessao for chave in ("email", "senha_hash", "nome")):
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

    try:
        id_usuario = db.cadastrar_usuario(
            dados_sessao["nome"], dados_sessao["email"], None,
            faixa_etaria, trabalha, estuda, turno,
            senha_hash=dados_sessao["senha_hash"],
        )
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    dias_trabalho = dados.get("dias_trabalho") or []
    horario_trabalho = dados.get("horario_trabalho_personalizado") or dados.get("horario_trabalho_estimado")
    if trabalha and dias_trabalho and horario_trabalho:
        for dia in dias_trabalho:
            dia_db = DIAS_ONBOARDING_PARA_DB.get(dia)
            if dia_db:
                db.adicionar_rotina(id_usuario, dia_db, "Trabalho", horario_trabalho["start"], horario_trabalho["end"])

    dias_estudo = dados.get("dias_estudo") or []
    horario_estudo = dados.get("horario_estudo")
    if estuda and dias_estudo and horario_estudo:
        for dia in dias_estudo:
            dia_db = DIAS_ONBOARDING_PARA_DB.get(dia)
            if dia_db:
                db.adicionar_rotina(id_usuario, dia_db, "Estudo", horario_estudo["start"], horario_estudo["end"])

    for obj in (dados.get("objetivos") or []):
        titulo = (obj.get("titulo") or "").strip()
        if titulo:
            db.criar_objetivo(id_usuario, titulo, prazo=obj.get("prazo") or None)

    for hobby in (dados.get("hobbies") or []):
        if hobby != "personalizado":
            db.associar_hobby(id_usuario, hobby)
    hobby_personalizado = dados.get("hobby_personalizado")
    if hobby_personalizado:
        db.associar_hobby(id_usuario, hobby_personalizado)

    if dados.get("pico_energia") in {"manha", "tarde", "noite", "nao_sei"}:
        db.salvar_padrao(id_usuario, "energia", dados["pico_energia"])
    if dados.get("areas_melhoria"):
        db.salvar_padrao(id_usuario, "areas_melhoria", ", ".join(dados["areas_melhoria"]))
    if dados.get("tipo_estudo"):
        db.salvar_preferencia(id_usuario, "tipo_estudo", dados["tipo_estudo"])
    if dados.get("frequencia_hobbies"):
        db.salvar_preferencia(id_usuario, "frequencia_hobbies", dados["frequencia_hobbies"])
    if dados.get("sugestoes_hobbies"):
        db.salvar_preferencia(id_usuario, "quer_sugestoes_hobbies", dados["sugestoes_hobbies"])

    escolha_acess = dados.get("acessibilidade")
    if escolha_acess == "fonte_grande":
        db.salvar_preferencia(id_usuario, "acess_fonte", "grande")
    elif escolha_acess == "alto_contraste":
        db.salvar_preferencia(id_usuario, "acess_contraste", "alto")
    elif escolha_acess == "dislexia":
        db.salvar_preferencia(id_usuario, "acess_tipografia", "dislexia")

    if dados.get("tempo_organizacao"):
        db.salvar_padrao(id_usuario, "tempo_organizacao", dados["tempo_organizacao"])
    if dados.get("tempo_neocortex"):
        db.salvar_padrao(id_usuario, "tempo_neocortex", dados["tempo_neocortex"])
    if dados.get("personalizacao"):
        db.registrar_interacao(id_usuario, dados["personalizacao"], tipo="texto", contexto="cadastro_inicial")

    session.pop("cadastro", None)
    session["id_usuario"] = id_usuario
    session["nome"] = dados_sessao["nome"]

    return jsonify({"redirect": url_for("cadastro_sucesso")})


@app.route("/cadastro/sucesso")
@login_obrigatorio
def cadastro_sucesso():
    return render_template("cadastro_sucesso.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("tela_login"))


# ============================================================
# TAREFAS
# ============================================================
def tarefas_filtradas(id_usuario, filtro):
    """'hoje' | 'proximas' | qualquer outro valor = todas. Filtra no banco, não em Python."""
    hoje = datetime.combine(datetime.now().date(), datetime.min.time())
    if filtro == "hoje":
        return db.listar_tarefas(id_usuario, data_inicio=hoje, inicio_antes=hoje + timedelta(days=1))
    if filtro == "proximas":
        return db.listar_tarefas(id_usuario, data_inicio=hoje + timedelta(days=1))
    return db.listar_tarefas(id_usuario)


def _render_tarefas(filtro="hoje", **extra):
    return render_template(
        "tarefas.html",
        tarefas=tarefas_filtradas(usuario_logado(), filtro),
        filtro=filtro,
        **_pagina("tarefas", "Tarefas", **extra),
    )


def _montar_datetime(data, hora, minuto):
    """'2026-10-08', '9', '5' -> '2026-10-08T09:05'. None se algo faltar ou for inválido."""
    try:
        return f"{data}T{int(hora):02d}:{int(minuto):02d}" if data else None
    except (TypeError, ValueError):
        return None


def _ler_formulario_tarefa():
    """Campos comuns de criar/editar tarefa. Retorna um dict com 'erro' preenchido se algo estiver errado."""
    f = request.form
    dados = {
        "titulo": f.get("titulo", "").strip(),
        "categoria": f.get("categoria") or None,
        "inicio": _montar_datetime(f.get("data_inicio_data", ""), f.get("data_inicio_h", ""), f.get("data_inicio_m", "")),
        "fim": _montar_datetime(f.get("data_fim_data", ""), f.get("data_fim_h", ""), f.get("data_fim_m", "")),
        "erro": None,
    }
    if not dados["titulo"] or not f.get("data_inicio_data") or not f.get("data_fim_data"):
        dados["erro"] = "Preencha título, início e fim da tarefa."
    elif not dados["inicio"] or not dados["fim"]:
        dados["erro"] = "Data ou horário inválido."
    return dados


def _resposta_de_tarefa(resultado, formulario):
    """
    Traduz o retorno de um serviço de tarefa: None se deu certo; senão, a tela de
    tarefas de novo com o motivo. Em conflito, devolve também os dados digitados e
    'exige_confirmacao', para o template oferecer "salvar mesmo assim"
    (reenviar o formulário com confirmar_conflito=1).
    """
    if resultado.get("nao_encontrada"):
        abort(404)
    if resultado.get("sucesso") or resultado.get("sem_mudanca"):
        return None
    if resultado.get("conflitos"):
        return _render_tarefas(
            erro="Há conflito com: " + servicos.descrever_conflitos(resultado["conflitos"]) + ".",
            conflitos=resultado["conflitos"], formulario=formulario, exige_confirmacao=True,
        )
    return _render_tarefas(erro=resultado.get("erro") or "Não foi possível salvar a tarefa.", formulario=formulario)


@app.route("/tarefas")
@login_obrigatorio
def tarefas():
    return _render_tarefas(request.args.get("filtro", "hoje"))


@app.route("/tarefas/nova", methods=["POST"])
@login_obrigatorio
def criar_tarefa():
    dados = _ler_formulario_tarefa()
    if dados["erro"]:
        return _render_tarefas(erro=dados["erro"], formulario=dados)
    try:
        resultado = servicos.criar_tarefa(
            usuario_logado(), dados["titulo"], dados["inicio"], dados["fim"],
            categoria=dados["categoria"], origem="manual", confirmar_conflito=_confirmou_conflito(),
        )
    except ValueError as erro:
        return _render_tarefas(erro=str(erro), formulario=dados)
    resposta = _resposta_de_tarefa(resultado, dados)
    if resposta:
        return resposta
    _mascote_evento("tarefa_criada")   # [MASCOTE]
    return redirect(url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/editar", methods=["POST"])
@login_obrigatorio
def editar_tarefa(id_tarefa):
    dados = _ler_formulario_tarefa()
    if dados["erro"]:
        return _render_tarefas(erro=dados["erro"], formulario=dados)

    # [MASCOTE] guarda o estado antes, pra reconhecer quando uma tarefa atrasada foi remarcada
    agora = datetime.now()
    antes = next((t for t in db.listar_tarefas(usuario_logado()) if t["id_tarefa"] == id_tarefa), None)
    estava_atrasada = bool(antes and antes["status"] in ("pendente", "em_andamento") and antes["data_fim"] < agora)

    try:
        resultado = servicos.atualizar_tarefa(
            usuario_logado(), id_tarefa, titulo=dados["titulo"], categoria=dados["categoria"],
            data_inicio=dados["inicio"], data_fim=dados["fim"], confirmar_conflito=_confirmou_conflito(),
        )
    except ValueError as erro:
        return _render_tarefas(erro=str(erro), formulario=dados)
    resposta = _resposta_de_tarefa(resultado, dados)
    if resposta:
        return resposta

    # [MASCOTE] remarcar uma atrasada pra frente conta como replanejar (não é culpa, é ajuste)
    if estava_atrasada and datetime.fromisoformat(dados["fim"]) > agora:
        _mascote_evento("tarefa_replanejada")
        _liberar_tema(usuario_logado(), "campeonato")   # [TEMA]
    return redirect(url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/concluir", methods=["POST"])
@login_obrigatorio
def concluir_tarefa(id_tarefa):
    resultado = servicos.concluir_tarefa(usuario_logado(), id_tarefa)
    if resultado.get("nao_encontrada"):
        abort(404)

    # [MASCOTE] se era a última de hoje, a comemoração é de "dia concluído"
    if not resultado.get("erro"):
        hoje = [t for t in tarefas_filtradas(usuario_logado(), "hoje") if t["status"] != "cancelada"]
        era_de_hoje = any(t["id_tarefa"] == id_tarefa for t in hoje)
        if era_de_hoje and all(t["status"] == "concluida" for t in hoje):
            _mascote_evento("dia_concluido")
            _liberar_tema(usuario_logado(), "campeonato", NIVEL_SIMPLES)   # [TEMA] versão simples
        else:
            _mascote_evento("tarefa_concluida")
    return redirect(request.referrer or url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/desfazer", methods=["POST"])
@login_obrigatorio
def desfazer_tarefa(id_tarefa):
    resultado = servicos.desfazer_conclusao(usuario_logado(), id_tarefa)
    if resultado.get("nao_encontrada"):
        abort(404)
    return redirect(request.referrer or url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/cancelar", methods=["POST"])
@login_obrigatorio
def cancelar_tarefa_rota(id_tarefa):
    resultado = servicos.cancelar_tarefa(usuario_logado(), id_tarefa)
    if resultado.get("nao_encontrada"):
        abort(404)
    return redirect(request.referrer or url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_tarefa(id_tarefa):
    resultado = servicos.excluir_tarefa(usuario_logado(), id_tarefa)
    if resultado.get("nao_encontrada"):
        abort(404)
    return redirect(url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/reativar", methods=["POST"])
@login_obrigatorio
def reativar_tarefa_rota(id_tarefa):
    resultado = servicos.reativar_tarefa(usuario_logado(), id_tarefa)
    if resultado.get("nao_encontrada"):
        abort(404)
    return redirect(request.referrer or url_for("tarefas"))


# ============================================================
# ROTINA FIXA
# ============================================================
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


def _render_rotina(**extra):
    return render_template(
        "rotina.html",
        rotina=agrupar_rotina(db.listar_rotina(usuario_logado())),
        **_pagina("rotina", "Rotina Fixa", **extra),
    )


@app.route("/rotina")
@login_obrigatorio
def rotina():
    return _render_rotina()


@app.route("/rotina/nova", methods=["POST"])
@login_obrigatorio
def adicionar_rotina_rota():
    dias_semana = request.form.getlist("dia_semana")
    descricao = request.form.get("descricao", "").strip()
    hora_inicio = f"{request.form.get('hora_inicio_h', '')}:{request.form.get('hora_inicio_m', '')}"
    hora_fim = f"{request.form.get('hora_fim_h', '')}:{request.form.get('hora_fim_m', '')}"

    dias_invalidos = [d for d in dias_semana if d not in DIAS_SEMANA_VALIDOS]
    if not dias_semana or dias_invalidos:
        return _render_rotina(erro="Selecione ao menos um dia da semana válido.")
    if not descricao:
        return _render_rotina(erro="Preencha a descrição.")

    try:
        servicos.configurar_rotina(usuario_logado(), descricao, hora_inicio, hora_fim, dias_semana)
    except ValueError as erro:
        return _render_rotina(erro=str(erro))
    _verificar_desbloqueio_papelaria(usuario_logado())   # [TEMA]
    return redirect(url_for("rotina"))


@app.route("/rotina/grupo/excluir", methods=["POST"])
@login_obrigatorio
def excluir_grupo_rotina():
    for id_str in request.form.getlist("id_rotina"):
        try:
            db.deletar_rotina(int(id_str), usuario_logado())
        except ValueError:
            continue
    return redirect(url_for("rotina"))


# ============================================================
# DASHBOARD
# ============================================================
@app.route("/dashboard")
@login_obrigatorio
def dashboard():
    hoje = datetime.now().date()
    hoje_formatado = f"{DIAS_SEMANA_PT[hoje.weekday()]}, {hoje.day} de {MESES_PT[hoje.month - 1].lower()}"

    # canceladas não contam: a tarefa deixou de existir para o usuário
    tarefas_hoje = [t for t in tarefas_filtradas(usuario_logado(), "hoje") if t["status"] != "cancelada"]
    total = len(tarefas_hoje)
    concluidas = len([t for t in tarefas_hoje if t["status"] == "concluida"])
    pct = round((concluidas / total) * 100) if total else 0

    # [TEMA] resumo dos 7 dias (segunda a domingo) para a prateleira / escalação da tela inicial.
    # Só conta concluídas de planejadas: o visual nunca desenha tarefa por tarefa.
    segunda = datetime.combine(hoje - timedelta(days=hoje.weekday()), datetime.min.time())
    semana_dias = [{"data": (segunda + timedelta(days=i)).date().isoformat(), "total": 0, "concluidas": 0} for i in range(7)]
    por_data = {d["data"]: d for d in semana_dias}
    for t in db.listar_tarefas(usuario_logado(), data_inicio=segunda, inicio_antes=segunda + timedelta(days=7)):
        dia = por_data.get(t["data_inicio"].date().isoformat())
        if dia and t["status"] != "cancelada":
            dia["total"] += 1
            dia["concluidas"] += t["status"] == "concluida"

    hora = datetime.now().hour
    saudacao = "Bom dia" if 5 <= hora < 12 else ("Boa tarde" if hora < 18 else "Boa noite")

    return render_template(
        "dashboard.html",
        tarefas=tarefas_hoje,
        total=total, concluidas=concluidas, pct=pct,
        hoje_formatado=hoje_formatado,
        semana_dias=semana_dias,                      # [TEMA]
        saudacao=saudacao,                            # [TEMA]
        primeiro_nome=(session.get("nome") or "").split(" ")[0],
        **_pagina("dashboard", f"Olá, {session.get('nome', '?')} 👋"),
    )


# =============================================================
# OBJETIVOS
# =============================================================

@app.route("/objetivos")
def objetivos():
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    lista = db.listar_objetivos(usuario_logado())
    fragmentos = {o["id_objetivo"]: db.listar_fragmentos_objetivo(o["id_objetivo"], usuario_logado()) for o in lista}
    return render_template(
        "objetivos.html",
        objetivos=lista,
        db_fragmentos=fragmentos,
        **_pagina("objetivos", "Objetivos"),
    )


@app.route("/objetivos/novo", methods=["POST"])
def criar_objetivo_rota():
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    titulo = request.form.get("titulo", "").strip()
    prazo = request.form.get("prazo") or None
    if titulo:
        db.criar_objetivo(usuario_logado(), titulo, prazo=prazo)
        _mascote_evento("objetivo_criado", objetivo=titulo)   # [MASCOTE]
        _verificar_desbloqueio_cafeteria(usuario_logado())    # [TEMA] versão simples
    return redirect(url_for("objetivos"))


@app.route("/objetivos/<int:id_objetivo>/concluir", methods=["POST"])
def concluir_objetivo_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    objetivo = db.buscar_objetivo(id_objetivo, usuario_logado())   # [MASCOTE] pra citar o título
    db.atualizar_objetivo(id_objetivo, usuario_logado(), status="concluido")
    if objetivo:
        _mascote_evento("objetivo_concluido", objetivo=objetivo["titulo"])   # [MASCOTE]
    return redirect(url_for("objetivos"))


@app.route("/objetivos/<int:id_objetivo>/excluir", methods=["POST"])
def excluir_objetivo_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    db.excluir_objetivo(id_objetivo, usuario_logado())
    return redirect(url_for("objetivos"))


@app.route("/objetivos/<int:id_objetivo>/desfazer", methods=["POST"])
def desfazer_objetivo_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    db.atualizar_objetivo(id_objetivo, usuario_logado(), status="em_andamento")
    return redirect(url_for("objetivos"))


@app.route("/objetivos/<int:id_objetivo>/editar", methods=["POST"])
def editar_objetivo_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    titulo = request.form.get("titulo", "").strip()
    prazo = request.form.get("prazo") or None
    if titulo:
        db.atualizar_objetivo(id_objetivo, usuario_logado(), titulo=titulo, prazo=prazo)
    return redirect(url_for("objetivos"))


@app.route("/objetivos/<int:id_objetivo>/fragmentos", methods=["POST"])
def criar_fragmento_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    titulo = request.form.get("titulo", "").strip()
    data = request.form.get("data")
    hora = request.form.get("hora") or "09:00"
    if titulo and data:
        inicio = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
        fim = inicio + timedelta(minutes=30)
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, titulo, inicio, fim)
        _mascote_evento("tarefa_criada")   # [MASCOTE]
        _verificar_desbloqueio_cafeteria(usuario_logado())   # [TEMA]
    return redirect(url_for("objetivos"))


def calcular_quantidade_fragmentos(prazo, hoje=None):
    hoje = hoje or date.today()
    if not prazo or prazo <= hoje:
        return 4
    semanas = max(1, (prazo - hoje).days // 7)
    return min(semanas, 12)


@app.route("/objetivos/novo/fragmentar/previa", methods=["POST"])
@login_obrigatorio
def novo_objetivo_fragmentar_previa():
    titulo_objetivo = request.form.get("titulo", "").strip()
    prazo_str = request.form.get("prazo") or None
    if not titulo_objetivo:
        return jsonify(erro="Digite um título antes de fragmentar."), 400

    prazo_date = datetime.strptime(prazo_str, "%Y-%m-%d").date() if prazo_str else None
    foco = request.form.get("foco", "geral")
    ritmo = request.form.get("ritmo", "moderado")
    duracao_min = 60 if ritmo == "longo_espacado" else 30
    quantidade = calcular_quantidade_fragmentos(prazo_date)

    try:
        titulos = ai.gerar_titulos_fragmentos(titulo_objetivo, prazo_date, foco, ritmo, quantidade)
    except Exception:
        return jsonify(erro="Não consegui falar com a IA agora. Tenta de novo em instantes."), 503
    if not titulos:
        return jsonify(erro="A IA não conseguiu gerar os fragmentos. Tenta de novo."), 502

    hoje = datetime.now()
    propostas = []
    for i, titulo in enumerate(titulos):
        dia_alvo = (hoje + timedelta(weeks=i + 1)).date()
        sugestoes = decisao.sugerir_horarios(usuario_logado(), dia_alvo, duracao_min, max_sugestoes=1)
        if sugestoes.get("sugestoes"):
            inicio = sugestoes["sugestoes"][0]["inicio"]
        else:
            inicio = datetime.combine(dia_alvo, datetime.min.time().replace(hour=9)).isoformat(timespec="minutes")
        propostas.append({"titulo": titulo, "inicio": inicio, "duracao_min": duracao_min})

    return jsonify(propostas=propostas)


@app.route("/objetivos/novo/fragmentar/confirmar", methods=["POST"])
@login_obrigatorio
def novo_objetivo_fragmentar_confirmar():
    dados = request.get_json(silent=True) or {}
    titulo_objetivo = (dados.get("titulo_objetivo") or "").strip()
    prazo_str = dados.get("prazo") or None
    propostas = dados.get("propostas") or []
    if not titulo_objetivo:
        return jsonify(erro="título ausente"), 400

    id_objetivo = db.criar_objetivo(usuario_logado(), titulo_objetivo, prazo=prazo_str)

    for p in propostas:
        try:
            inicio = datetime.fromisoformat(p["inicio"])
        except (KeyError, ValueError):
            continue
        fim = inicio + timedelta(minutes=p.get("duracao_min", 30))
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, p["titulo"], inicio, fim)

    if propostas:   # [MASCOTE] [TEMA]
        _mascote_evento("tarefa_criada")
        _verificar_desbloqueio_cafeteria(usuario_logado())

    return jsonify(ok=True, redirect=url_for("objetivos"))


@app.route("/objetivos/<int:id_objetivo>/fragmentar/previa", methods=["POST"])
@login_obrigatorio
def fragmentar_objetivo_previa(id_objetivo):
    objetivo = db.buscar_objetivo(id_objetivo, usuario_logado())
    if not objetivo:
        return jsonify(erro="objetivo não encontrado"), 404

    foco = request.form.get("foco", "geral")
    ritmo = request.form.get("ritmo", "moderado")
    duracao_min = 60 if ritmo == "longo_espacado" else 30

    quantidade = calcular_quantidade_fragmentos(objetivo["prazo"].date() if objetivo["prazo"] else None)

    try:
        titulos = ai.gerar_titulos_fragmentos(objetivo["titulo"], objetivo["prazo"], foco, ritmo, quantidade)
    except Exception:
        return jsonify(erro="Não consegui falar com a IA agora. Tenta de novo em instantes."), 503

    if not titulos:
        return jsonify(erro="A IA não conseguiu gerar os fragmentos. Tenta de novo."), 502

    hoje = datetime.now()
    propostas = []
    for i, titulo in enumerate(titulos):
        dia_alvo = (hoje + timedelta(weeks=i + 1)).date()
        sugestoes = decisao.sugerir_horarios(usuario_logado(), dia_alvo, duracao_min, max_sugestoes=1)
        if sugestoes.get("sugestoes"):
            inicio = sugestoes["sugestoes"][0]["inicio"]
        else:
            inicio = datetime.combine(dia_alvo, datetime.min.time().replace(hour=9)).isoformat(timespec="minutes")
        propostas.append({"titulo": titulo, "inicio": inicio, "duracao_min": duracao_min})

    return jsonify(propostas=propostas)


@app.route("/objetivos/<int:id_objetivo>/fragmentar/confirmar", methods=["POST"])
@login_obrigatorio
def fragmentar_objetivo_confirmar(id_objetivo):
    propostas = request.get_json(silent=True) or []
    for p in propostas:
        try:
            inicio = datetime.fromisoformat(p["inicio"])
        except (KeyError, ValueError):
            continue
        fim = inicio + timedelta(minutes=p.get("duracao_min", 30))
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, p["titulo"], inicio, fim)

    if propostas:   # [MASCOTE] [TEMA]
        _mascote_evento("tarefa_criada")
        _verificar_desbloqueio_cafeteria(usuario_logado())

    return jsonify(ok=True, redirect=url_for("objetivos"))


# ============================================================
# CALENDÁRIO (lê a mesma agenda que a IA consulta)
# ============================================================
def _cor_do_evento(evento):
    if evento["tipo"] == "tarefa":
        return evento.get("cor") or COR_POR_STATUS.get(evento["status"], "#2563EB")
    return COR_COMPROMISSO if evento["tipo"] == "compromisso" else COR_ROTINA


@app.route("/calendario")
@login_obrigatorio
def calendario():
    hoje = datetime.now()
    ano = request.args.get("ano", type=int) or hoje.year
    mes = request.args.get("mes", type=int) or hoje.month
    if not (1 <= mes <= 12 and 1900 <= ano <= 2100):
        ano, mes = hoje.year, hoje.month

    semanas = calendario_lib.Calendar(firstweekday=6).monthdayscalendar(ano, mes)   # semana começa no domingo

    primeiro = datetime(ano, mes, 1)
    proximo_mes = datetime(ano + 1, 1, 1) if mes == 12 else datetime(ano, mes + 1, 1)
    carregada = agenda.carregar_agenda(usuario_logado(), primeiro, proximo_mes)   # 3 consultas para o mês todo
    por_dia = agenda.eventos_por_dia(carregada, primeiro.date(), proximo_mes.date())

    eventos_por_dia = {
        dia.day: [{"label": e["titulo"], "cor": _cor_do_evento(e), "tipo": e["tipo"]} for e in eventos]
        for dia, eventos in por_dia.items()
    }

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
        **_pagina("calendario", "Agenda"),
    )


@app.route("/api/eventos")
@login_obrigatorio
def api_eventos():
    """
    Eventos do usuário entre duas datas (AAAA-MM-DD, 'fim' inclusivo; máximo 62 dias).
    Mesma fonte do calendário e da IA: agenda.py.
    """
    try:
        inicio = datetime.strptime(request.args.get("inicio", ""), "%Y-%m-%d")
        fim = datetime.strptime(request.args.get("fim", request.args.get("inicio", "")), "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return jsonify(erro="Informe inicio e fim no formato AAAA-MM-DD."), 400
    if fim <= inicio or (fim - inicio).days > 62:
        return jsonify(erro="Intervalo inválido (máximo 62 dias)."), 400

    carregada = agenda.carregar_agenda(usuario_logado(), inicio, fim)
    por_dia = agenda.eventos_por_dia(carregada, inicio.date(), fim.date())
    vistos, eventos = set(), []
    for lista in por_dia.values():
        for e in lista:
            if (e["tipo"], e["id"], e["inicio"]) in vistos:
                continue
            vistos.add((e["tipo"], e["id"], e["inicio"]))
            eventos.append({
                "tipo": e["tipo"], "id": e["id"], "titulo": e["titulo"],
                "inicio": e["inicio"].isoformat(timespec="minutes"),
                "fim": e["fim"].isoformat(timespec="minutes"),
                "status": e["status"], "categoria": e["categoria"], "cor": _cor_do_evento(e),
            })
    eventos.sort(key=lambda e: e["inicio"])
    return jsonify(eventos)


# ============================================================
# ASSISTENTE
# ============================================================
@app.route("/assistente")
@login_obrigatorio
def assistente():
    mensagens = list(reversed(
        db.listar_interacoes(usuario_logado(), contexto="interacao_geral", limite=50)
    ))
    return render_template("assistente.html", mensagens=mensagens, **_pagina("assistente", "Assistente"))


@app.route("/assistente/enviar", methods=["POST"])
@login_obrigatorio
def enviar_mensagem():
    texto = request.form.get("mensagem", "").strip()[:MAX_CARACTERES_MENSAGEM]
    if not texto:
        return redirect(url_for("assistente"))

    id_usuario = usuario_logado()

    # O histórico é lido antes de gravar a mensagem atual para não duplicá-la no contexto da IA.
    historico = list(reversed(
        db.listar_interacoes(id_usuario, contexto="interacao_geral", limite=10)
    ))

    db.registrar_interacao(id_usuario, texto, autor="usuario")

    try:
        resposta = ai.responder(id_usuario, texto, historico)
        _mascote_evento("ia_respondeu")   # [MASCOTE] boca mexendo ao chegar a resposta
    except Exception:
        app.logger.exception("Falha ao gerar a resposta da IA (usuário %s)", id_usuario)
        resposta = "Deu um problema pra falar com a IA agora. Tenta de novo em um instante."
        _mascote_evento("ia_erro")        # [MASCOTE] expressão de confusão

    # A resposta é salva no histórico para manter continuidade entre as mensagens.
    db.registrar_interacao(id_usuario, resposta, autor="assistente")
    return redirect(url_for("assistente"))


# ==============================================================
# MASCOTE, LOJA, JORNADA E TEMAS
# ==============================================================
# [ACESSÓRIOS] Cada mascote tem os seus. Um item de cada vez. Tudo libera até 600 pontos ("Dupla afiada").
# Para cada "id" precisa existir o desenho (grupo .nc-acessorio-<id> no SVG do mascote, em mascote_robo.js)
# e a regra de CSS que o mostra (mascote_robo.css). O verificar_pacote.py confere isso.
ACESSORIOS_POR_MASCOTE = {
    "robo": [
        {"id": "oculos", "nome": "Óculos", "pontos_min": 100},
        {"id": "gorro", "nome": "Gorro", "pontos_min": 200},
        {"id": "oculos3d", "nome": "Óculos 3D de cinema", "pontos_min": 300},
        {"id": "protetor", "nome": "Protetor de orelha térmico", "pontos_min": 450},   # com gorro em outra cor
        {"id": "cachecol", "nome": "Cachecol", "pontos_min": 600},
    ],
    "grao": [
        {"id": "gorro", "nome": "Gorro", "pontos_min": 100},
        {"id": "anjo", "nome": "Asas e auréola", "pontos_min": 250},
        {"id": "jaqueta", "nome": "Jaqueta com capuz felpudo", "pontos_min": 400},
        {"id": "cachecol", "nome": "Cachecol", "pontos_min": 600},
    ],
    "boltz": [
        {"id": "gorro", "nome": "Gorro", "pontos_min": 100},
        {"id": "chuteira", "nome": "Chuteira de ouro", "pontos_min": 250},
        {"id": "uniforme", "nome": "Uniforme do time NEOCORTEX", "pontos_min": 400},
        {"id": "cachecol", "nome": "Cachecol", "pontos_min": 600},
    ],
    "rabisco": [
        {"id": "gorro", "nome": "Gorro", "pontos_min": 100},
        {"id": "capacete", "nome": "Capacete de pedreiro", "pontos_min": 200},
        {"id": "prancheta", "nome": "Prancheta", "pontos_min": 300},
        {"id": "caminha", "nome": "Caminha de gato", "pontos_min": 450},   # em dia livre, o gato dorme nela
        {"id": "cachecol", "nome": "Cachecol", "pontos_min": 600},
    ],
}
ACESSORIOS_MASCOTE = ACESSORIOS_POR_MASCOTE["robo"]   # nome antigo: o catálogo do robô


def acessorios_do_mascote(skin):
    return ACESSORIOS_POR_MASCOTE.get(skin, ACESSORIOS_POR_MASCOTE["robo"])


def acessorios_desbloqueados(pontos, skin="robo"):
    catalogo = acessorios_do_mascote(skin)
    if MODO_DEMO:   # [TEMA] gravação da apresentação: todos liberados
        return {a["id"] for a in catalogo}
    return {a["id"] for a in catalogo if pontos >= a["pontos_min"]}


NIVEIS_MASCOTE = [
    {"nivel": 1, "pontos_min": 0,   "nome": "Começando junto",     "frases_extra": False, "acessorio": None,       "animado": False},
    {"nivel": 2, "pontos_min": 100, "nome": "Pegando o ritmo",     "frases_extra": True,  "acessorio": "novos acessórios", "animado": False},
    {"nivel": 3, "pontos_min": 300, "nome": "Parceria de verdade", "frases_extra": True,  "acessorio": "novos acessórios", "animado": True},
    {"nivel": 4, "pontos_min": 600, "nome": "Dupla afiada",        "frases_extra": True,  "acessorio": "novos acessórios", "animado": True},
]


def nivel_mascote(pontos):
    atual = NIVEIS_MASCOTE[0]
    for n in NIVEIS_MASCOTE:
        if pontos >= n["pontos_min"]:
            atual = n
        else:
            break
    return atual


@app.context_processor
def injetar_mascote():
    """[MASCOTE] [TEMA] [PERSONALIZAR] Pontos, tema, e a personalização do mascote ATUAL,
    num lugar só (um único pop dos eventos)."""
    if not GAMIFICACAO_ATIVA or not usuario_logado():
        return {"mascote_ativo": False, "tema_ativo": "padrao", "mascote_skin": "robo"}

    id_usuario = usuario_logado()
    pontos = db.calcular_pontos_mascote(id_usuario)
    atual = nivel_mascote(pontos)
    proximo = next((n for n in NIVEIS_MASCOTE if n["pontos_min"] > pontos), None)
    if proximo:
        faixa = proximo["pontos_min"] - atual["pontos_min"]
        progresso_pct = int(((pontos - atual["pontos_min"]) / faixa) * 100) if faixa else 100
    else:
        progresso_pct = 100

    _verificar_desbloqueio_papelaria(id_usuario)   # [TEMA] a versão completa chega com o tempo, sem ação
    intensidade = db.buscar_preferencia(id_usuario, "mascote_intensidade") or ""
    liberados = _temas_liberados(id_usuario)       # {tema: nível}
    tema = db.buscar_preferencia(id_usuario, "tema_visual") or "padrao"
    if tema not in liberados:
        tema = "padrao"
    imersivo = liberados[tema] >= NIVEL_COMPLETO
    skin = TEMAS[tema]["mascote"] if imersivo else "robo"

    # [INTERFACE] clássica por padrão; imersiva liberada por pontos ou pelo tema completo. Liga sozinha e só volta
    # à clássica se a pessoa escolher (preferência "interface_modo"). A liberação roda antes de consumir os eventos.
    liberada = _interface_imersiva_liberada(id_usuario, pontos)
    disponivel = liberada or (imersivo and tema != "padrao")   # o padrão nasce completo: só os pontos o liberam
    modo = (db.buscar_preferencia(id_usuario, "interface_modo") or "") if disponivel else ""
    usa_imersiva = disponivel and modo != "classica"

    equipado = db.buscar_preferencia(id_usuario, _chave_mascote("mascote_acessorio_equipado", skin)) or "nenhum"
    if equipado not in acessorios_desbloqueados(pontos, skin):
        equipado = "nenhum"
    cor = _cor_do_mascote(id_usuario, skin)

    return {
        "mascote_ativo": True,
        "mascote_eventos": session.pop("mascote_eventos", []),
        "mascote_intensidade": intensidade if intensidade in INTENSIDADES_MASCOTE else "",
        "mascote_nivel": atual,
        "mascote_pontos": pontos,
        "mascote_proximo_nivel": proximo,
        "mascote_progresso_pct": progresso_pct,
        "mascote_acessorio": equipado,
        "tema_ativo": tema,
        "mascote_skin": skin,
        "mascote_nome": TEMAS[tema]["mascote_nome"] if imersivo else TEMAS["padrao"]["mascote_nome"],
        "tema_imersivo": imersivo,
        # o que a tela inicial e a agenda desenham: na versão simples, a rede do padrão nas cores do tema
        # vazio = interface clássica (tela original); com valor = o que a tela inicial e a agenda desenham
        "tema_semana": (tema if imersivo else "padrao") if usa_imersiva else "",
        "interface_imersiva": usa_imersiva,
        "interface_imersiva_disponivel": disponivel,
        "pontos_interface": PONTOS_INTERFACE_IMERSIVA,
        "mascote_cor": cor["cor"],
        "mascote_brilho": cor["brilho"],
        "mascote_cor_id": cor["id"],
        "cores_mascote": CORES_MASCOTE,
        "temas": {tid: {**info, "liberado": tid in liberados, "nivel": liberados.get(tid, 0)}
                  for tid, info in TEMAS.items()},
    }


@app.route("/configuracoes/mascote", methods=["POST"])
@login_obrigatorio
def salvar_mascote():
    intensidade = request.form.get("mascote_animacao")
    if intensidade in INTENSIDADES_MASCOTE:
        db.salvar_preferencia(usuario_logado(), "mascote_intensidade", intensidade)
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/tema", methods=["POST"])
@login_obrigatorio
def salvar_tema():
    """[TEMA] Troca o tema. Só aceita temas já liberados; nada nos dados muda."""
    escolha = request.form.get("tema", "")
    if escolha in TEMAS and escolha in _temas_liberados(usuario_logado()):
        db.salvar_preferencia(usuario_logado(), "tema_visual", escolha)
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/interface", methods=["POST"])
@login_obrigatorio
def salvar_interface():
    """[INTERFACE] Clássica ou imersiva. A clássica é sempre permitida; a imersiva só depois de liberada."""
    escolha = request.form.get("interface", "")
    if escolha == "classica" or (escolha == "imersiva" and _interface_imersiva_disponivel(usuario_logado())):
        db.salvar_preferencia(usuario_logado(), "interface_modo", escolha)
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/mascote-cor", methods=["POST"])
@login_obrigatorio
def salvar_cor_mascote():
    """[PERSONALIZAR] Cor do mascote ATUAL (cada mascote guarda a sua). Só aceita cores da paleta."""
    escolha = request.form.get("cor", "")
    if escolha in {c["id"] for c in CORES_MASCOTE}:
        skin = _skin_atual(usuario_logado())
        db.salvar_preferencia(usuario_logado(), _chave_mascote("mascote_cor", skin), escolha)
    return redirect(url_for("configuracoes"))


@app.route("/mascote/loja")
@login_obrigatorio
def mascote_loja():
    pontos = db.calcular_pontos_mascote(usuario_logado())
    skin = _skin_atual(usuario_logado())
    desbloqueados = acessorios_desbloqueados(pontos, skin)
    equipado = db.buscar_preferencia(usuario_logado(), _chave_mascote("mascote_acessorio_equipado", skin)) or "nenhum"
    if equipado not in desbloqueados:   # ex.: acessório que não existe mais no catálogo deste mascote
        equipado = "nenhum"
    return render_template(
        "mascote_loja.html",
        acessorios=acessorios_do_mascote(skin),
        desbloqueados=desbloqueados,
        equipado_atual=equipado,
        **_pagina("mascote_loja", "Loja"),
    )


@app.route("/mascote/loja/equipar", methods=["POST"])
@login_obrigatorio
def equipar_acessorio():
    escolha = request.form.get("acessorio", "nenhum")
    pontos = db.calcular_pontos_mascote(usuario_logado())
    skin = _skin_atual(usuario_logado())   # [PERSONALIZAR] equipa no mascote atual
    if escolha != "nenhum" and escolha not in acessorios_desbloqueados(pontos, skin):
        abort(403)  # tentou equipar algo que não desbloqueou (ou que é de outro mascote)
    db.salvar_preferencia(usuario_logado(), _chave_mascote("mascote_acessorio_equipado", skin), escolha)
    if escolha != "nenhum":   # [ACESSÓRIOS] o mascote comenta o item novo
        item = next(a["nome"] for a in acessorios_do_mascote(skin) if a["id"] == escolha)
        _mascote_evento("acessorio", id=escolha, item=item)
    return redirect(url_for("mascote_loja"))


@app.route("/jornada")
@login_obrigatorio
def jornada():
    pontos = db.calcular_pontos_mascote(usuario_logado())
    nivel_atual = nivel_mascote(pontos)
    nos = []
    for i, n in enumerate(NIVEIS_MASCOTE):
        if n["nivel"] == nivel_atual["nivel"]:
            status = "atual"
        elif pontos >= n["pontos_min"]:
            status = "concluido"
        else:
            status = "bloqueado"
        nos.append({
            **n,
            "x": 150 if i % 2 == 0 else 346,
            "y": 70 + i * 170,
            "status": status,
        })
    altura_svg = 70 + len(NIVEIS_MASCOTE) * 170
    return render_template("jornada.html", nos=nos, altura_svg=altura_svg, **_pagina("jornada", "Jornada"))


# ============================================================
# CONFIGURAÇÕES
# ============================================================

@app.route("/configuracoes")
@login_obrigatorio
def configuracoes():
    _verificar_desbloqueio_cafeteria(usuario_logado())   # [TEMA] cobre quem já tinha fragmentos
    _verificar_desbloqueio_papelaria(usuario_logado())   # [TEMA] cobre quem já tinha rotina montada
    notificacoes_ativas = db.buscar_preferencia(usuario_logado(), "notificacoes_ativas") == "true"
    return render_template(
        "configuracoes.html",
        notificacoes_ativas=notificacoes_ativas,
        **_pagina("configuracoes", "Configurações"),
    )


@app.route("/configuracoes/perfil", methods=["POST"])
@login_obrigatorio
def atualizar_perfil():
    nome = request.form.get("nome", "").strip()
    if len(nome) < 2:
        return redirect(url_for("configuracoes"))

    db.atualizar_usuario(usuario_logado(), nome=nome)
    session["nome"] = nome
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/senha", methods=["POST"])
@login_obrigatorio
def trocar_senha_rota():
    senha_atual = request.form.get("senha_atual", "")
    nova_senha = request.form.get("nova_senha", "")

    usuario = db.buscar_usuario(usuario_logado())
    if not usuario or not bcrypt.checkpw(senha_atual.encode("utf-8"), usuario["senha_hash"].encode("utf-8")):
        return redirect(url_for("configuracoes", erro="senha_atual"))

    if seguranca.senha_valida(nova_senha):
        return redirect(url_for("configuracoes", erro="senha_curta"))

    db.trocar_senha(usuario_logado(), nova_senha)
    return redirect(url_for("configuracoes", sucesso="senha"))


@app.route("/configuracoes/exportar")
@login_obrigatorio
def exportar_dados():
    id_usuario = usuario_logado()
    usuario = db.buscar_usuario(id_usuario) or {}

    payload = {
        "nome": usuario.get("nome") or session.get("nome"),
        "email": usuario.get("email"),
        "exportado_em": datetime.now().isoformat(),
        "tarefas": [
            {
                "titulo": t["titulo"], "categoria": t["categoria"], "status": t["status"],
                "data_inicio": t["data_inicio"].isoformat(), "data_fim": t["data_fim"].isoformat(),
            }
            for t in db.listar_tarefas(id_usuario)
        ],
        "compromissos": [
            {
                "titulo": c["titulo"], "tipo": c["tipo"], "local": c["local"],
                "data_inicio": c["data_inicio"].isoformat(), "data_fim": c["data_fim"].isoformat(),
            }
            for c in db.listar_compromissos(id_usuario)
        ],
        "rotina_fixa": [
            {"descricao": r["descricao"], "dia_semana": r["dia_semana"],
             "hora_inicio": r["hora_inicio"], "hora_fim": r["hora_fim"]}
            for r in db.listar_rotina(id_usuario)
        ],
    }

    return Response(
        json.dumps(payload, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=neocortex-dados.json"},
    )


@app.route("/configuracoes/notificacoes", methods=["POST"])
@login_obrigatorio
def salvar_notificacoes():
    ativado = request.form.get("notificacoes_ativas") == "on"
    db.salvar_preferencia(usuario_logado(), "notificacoes_ativas", "true" if ativado else "false")
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/excluir-conta", methods=["POST"])
@login_obrigatorio
def excluir_conta():
    senha_atual = request.form.get("senha_atual", "")
    usuario = db.buscar_usuario(usuario_logado())
    if not usuario or not bcrypt.checkpw(senha_atual.encode("utf-8"), usuario["senha_hash"].encode("utf-8")):
        return redirect(url_for("configuracoes", erro="senha_atual"))

    db.excluir_usuario(usuario_logado())
    session.clear()
    return redirect(url_for("tela_login"))


TAGS_MARKDOWN_PERMITIDAS = ["p", "br", "strong", "em", "b", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "code", "pre", "blockquote", "a"]
ATRIBUTOS_MARKDOWN_PERMITIDOS = {"a": ["href", "title"]}


def renderizar_markdown(texto):
    html = markdown_lib.markdown(texto, extensions=["nl2br"])
    return bleach.clean(html, tags=TAGS_MARKDOWN_PERMITIDAS, attributes=ATRIBUTOS_MARKDOWN_PERMITIDOS, strip=True)


app.jinja_env.filters["markdown"] = renderizar_markdown


@app.context_processor
def injetar_acessibilidade():
    if not usuario_logado():
        return {}
    return {
        chave: seguranca.acessibilidade_valida(chave, db.buscar_preferencia(usuario_logado(), chave))   # valor estranho vira o padrão
        for chave in ("acess_fonte", "acess_contraste", "acess_tipografia")
    }


@app.route("/configuracoes/acessibilidade", methods=["POST"])
@login_obrigatorio
def salvar_acessibilidade():
    for chave, campo in (
        ("acess_fonte", "acess_fonte"),
        ("acess_contraste", "acess_contraste_oculto"),
        ("acess_tipografia", "acess_tipografia_oculto"),
    ):
        valor = request.form.get(campo)
        if valor in seguranca.ACESSIBILIDADE[chave]:   # [SEGURANÇA] só grava o que as telas oferecem
            db.salvar_preferencia(usuario_logado(), chave, valor)
    return redirect(url_for("configuracoes"))


if __name__ == "__main__":
    # debug só quando pedido (FLASK_DEBUG=1); nunca ligado por padrão
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")