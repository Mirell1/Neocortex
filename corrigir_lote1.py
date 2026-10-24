"""
NEOCORTEX - corrigir_lote1.py          (correções do relatório de avaliação de 18/10, lote 1)

Itens do relatório: 32, 35, 36, 37, 48, 49, 50, 51, 52, 53 e 72.

  app.py                         32  cadastro confere horários e listas ANTES de criar a conta (sem conta pela metade)
                                 72  prazo inválido de objetivo vira erro 400, não erro 500
                                 53  confirmar passos: confere a lista INTEIRA antes de gravar e confere o dono do objetivo
                                 48, 49, 50  planejamento dos passos: respeita o prazo, o ritmo muda o espaçamento e nunca inventa horário
                                 36  filtro de categoria da lista de tarefas funciona
                                 37  "Hoje" inclui tarefas que começaram antes e atravessam a meia-noite (como a Agenda)
  templates/objetivos.html       51  botão de fragmentar funciona com apóstrofo e aspas no título
                                 NOVO (achado ao aplicar): as opções de foco e ritmo da fragmentação não marcavam nada ao clicar, então a
                                 escolha NUNCA chegava ao servidor (valia sempre geral/moderado). Agora marcam, com o padrão já marcado
                                 52  a prévia não insere HTML vindo da IA; mostra aviso e erro de confirmação
  static/semana_tematica.js      35  "livre" passa a dizer "sem tarefas" (o dia pode estar cheio de rotina)

Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python corrigir_lote1.py            # só mostra
    python corrigir_lote1.py --aplicar  # grava (cópias .bak; confere a sintaxe antes)

Rodar de novo é seguro. Funciona com o app.py antes ou depois do atualizar_objetivo_onboarding.py. Se não reconhecer um trecho,
NÃO mexe naquele arquivo e explica como fazer à mão.
"""
import argparse
import difflib
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(".").resolve()
MARCA = "# [LOTE1]"

# ------------------------------------------------------------------ blocos novos (app.py)
AJUDANTES = '''# [LOTE1] validações e planejamento de passos (itens 32, 48, 49, 50, 53 e 72 do relatório)
def _horario_valido(valor):
    """{'start': 'HH:MM', 'end': 'HH:MM'} com horas e minutos reais."""
    if not isinstance(valor, dict):
        return False
    for chave in ("start", "end"):
        texto = valor.get(chave)
        if not isinstance(texto, str):
            return False
        partes = texto.split(":")
        if len(partes) != 2 or not all(p.isdigit() and len(p) <= 2 for p in partes):
            return False
        if not (0 <= int(partes[0]) <= 23 and 0 <= int(partes[1]) <= 59):
            return False
    return True


def _lista_de_textos(valor):
    return valor is None or (isinstance(valor, list) and all(isinstance(x, str) for x in valor))


def _prazo_date(texto):
    """vazio -> None; 'AAAA-MM-DD' real (de 2000 até hoje + 10 anos) -> date; qualquer outra coisa -> ValueError."""
    if not texto:
        return None
    if not isinstance(texto, str):
        raise ValueError("prazo")
    dia = datetime.strptime(texto.strip(), "%Y-%m-%d").date()
    if dia < date(2000, 1, 1) or dia > date.today() + timedelta(days=3653):
        raise ValueError("prazo fora do intervalo")
    return dia


def _prazo_iso(texto):
    dia = _prazo_date(texto)
    return dia.isoformat() if dia else None


def _validar_propostas(lista):
    """Confere TODA a lista de passos antes de gravar qualquer um. Devolve (passos, None) ou ([], mensagem)."""
    if not isinstance(lista, list) or not lista:
        return [], "Não há passos para salvar."
    if len(lista) > 12:
        return [], "Passos demais de uma vez (no máximo 12)."
    agora = datetime.now()
    passos = []
    for p in lista:
        if not isinstance(p, dict):
            return [], "Um dos passos veio num formato inválido."
        titulo = p.get("titulo")
        titulo = " ".join(titulo.split())[:200] if isinstance(titulo, str) else ""
        if not titulo:
            return [], "Um dos passos está sem título."
        try:
            inicio = datetime.fromisoformat(p["inicio"])
        except (KeyError, TypeError, ValueError):
            return [], "Um dos passos está com data ou hora inválida."
        if not (agora - timedelta(days=1) <= inicio.replace(tzinfo=None) <= agora + timedelta(days=3653)):
            return [], "Um dos passos está com data fora do intervalo permitido."
        duracao = p.get("duracao_min", 30)
        if isinstance(duracao, bool) or not isinstance(duracao, int) or not 5 <= duracao <= 480:
            return [], "Um dos passos está com duração inválida (de 5 a 480 minutos)."
        passos.append({"titulo": titulo, "inicio": inicio, "fim": inicio + timedelta(minutes=duracao)})
    return passos, None


def _planejar_fragmentos(id_usuario, titulos, prazo, duracao_min, ritmo, hoje=None):
    """Distribui os passos entre amanhã e o prazo (sem prazo: uma semana entre eles). O ritmo define o espaçamento mínimo.
    Só propõe horários que a agenda confirma como livres: sem horário livre não há proposta. Devolve (propostas, aviso)."""
    hoje = hoje or date.today()
    titulos = list(titulos)[:12]
    total = len(titulos)
    if prazo:
        inicio_janela = hoje if prazo <= hoje else hoje + timedelta(days=1)
        dias = [inicio_janela + timedelta(days=i) for i in range((prazo - inicio_janela).days + 1)]   # o prazo já foi validado (até 10 anos)
        intervalo = {"curto_frequente": 1, "moderado": 2, "longo_espacado": 3}.get(ritmo, 2)
        quantos = min(total, (len(dias) - 1) // intervalo + 1)
        alvos = [0] if quantos == 1 else [round(k * (len(dias) - 1) / (quantos - 1)) for k in range(quantos)]
    else:
        dias = [hoje + timedelta(days=i) for i in range(1, 7 * total + 8)]
        quantos = total
        alvos = [7 * (k + 1) - 1 for k in range(quantos)]
    usados, slots = set(), []
    for alvo in alvos:
        ordem = [alvo]
        for passo in range(1, len(dias)):
            ordem += [alvo + passo, alvo - passo]
        for idx in ordem:
            if not prazo and abs(idx - alvo) > 6:
                break                      # sem prazo, não se afasta mais de uma semana do dia-alvo
            if idx in usados or not 0 <= idx < len(dias):
                continue
            achou = decisao.sugerir_horarios(id_usuario, dias[idx], duracao_min, max_sugestoes=1)
            if achou.get("sugestoes"):
                usados.add(idx)
                slots.append(achou["sugestoes"][0]["inicio"])
                break
    slots.sort()
    propostas = [{"titulo": titulos[i], "inicio": inicio, "duracao_min": duracao_min} for i, inicio in enumerate(slots)]
    if not propostas:
        return [], ("Não encontrei horário livre até o prazo. Tente um prazo maior ou libere espaço na agenda." if prazo
                    else "Não encontrei horário livre nos próximos dias. Libere espaço na agenda e tente de novo.")
    aviso = None
    passos = lambda n: f"{n} passo" + ("" if n == 1 else "s")
    if quantos < total:
        aviso = f"Até o prazo cabem só {passos(quantos)} nesse ritmo (a IA sugeriu {total})."
        if len(propostas) < quantos:
            aviso = f"Só encontrei horário livre para {len(propostas)} de {total} passos até o prazo."
    elif len(propostas) < total:
        aviso = f"Só encontrei horário livre para {len(propostas)} de {total} passos {'até o prazo' if prazo else 'nos próximos dias'}."
    return propostas, aviso


'''

VALIDACAO_CADASTRO = '''    # [LOTE1] confere a forma dos dados ANTES de criar a conta: um horário incompleto não pode deixar conta pela metade
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos. Atualize a página e tente de novo."}), 400
    for chave in ("horario_trabalho_personalizado", "horario_trabalho_estimado", "horario_estudo"):
        if dados.get(chave) and not _horario_valido(dados[chave]):
            return jsonify({"erro": "Horário inválido. Volte e confira o início e o fim."}), 400
    for chave in ("dias_trabalho", "dias_estudo", "hobbies", "areas_melhoria"):
        if not _lista_de_textos(dados.get(chave)):
            return jsonify({"erro": "Alguma resposta veio num formato inválido. Atualize a página e tente de novo."}), 400

'''

PREVIA_NOVO = '''@app.route("/objetivos/novo/fragmentar/previa", methods=["POST"])
@login_obrigatorio
def novo_objetivo_fragmentar_previa():
    titulo_objetivo = request.form.get("titulo", "").strip()
    if not titulo_objetivo:
        return jsonify(erro="Digite um título antes de fragmentar."), 400
    try:
        prazo_date = _prazo_date(request.form.get("prazo"))
    except ValueError:
        return jsonify(erro="Prazo inválido. Escolha uma data de hoje em diante."), 400
    return _previa_fragmentos(titulo_objetivo, prazo_date)


def _previa_fragmentos(titulo_objetivo, prazo_date, existente=False):
    """Prévia dos passos (compartilhada pelo objetivo novo e pelo existente). Nada é gravado aqui."""
    if prazo_date and prazo_date < date.today():
        return jsonify(erro=("O prazo deste objetivo já passou. Edite o objetivo e escolha uma nova data para dividir em passos." if existente
                             else "O prazo já passou. Escolha uma data de hoje em diante.")), 400
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

    propostas, aviso = _planejar_fragmentos(usuario_logado(), titulos, prazo_date, duracao_min, ritmo)
    if not propostas:
        return jsonify(erro=aviso), 409
    return jsonify(propostas=propostas, aviso=aviso)
'''

CONFIRMAR_NOVO = '''@app.route("/objetivos/novo/fragmentar/confirmar", methods=["POST"])
@login_obrigatorio
def novo_objetivo_fragmentar_confirmar():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify(erro="formato inválido"), 400
    titulo_objetivo = dados.get("titulo_objetivo")
    titulo_objetivo = " ".join(titulo_objetivo.split())[:200] if isinstance(titulo_objetivo, str) else ""
    if not titulo_objetivo:
        return jsonify(erro="título ausente"), 400
    try:
        prazo_str = _prazo_iso(dados.get("prazo"))
    except ValueError:
        return jsonify(erro="Prazo inválido."), 400
    passos, erro = _validar_propostas(dados.get("propostas"))
    if erro:
        return jsonify(erro=erro), 400      # nada foi criado: a lista inteira é conferida antes de gravar

    id_objetivo = db.criar_objetivo(usuario_logado(), titulo_objetivo, prazo=prazo_str)
    for p in passos:
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, p["titulo"], p["inicio"], p["fim"])

    _mascote_evento("tarefa_criada")   # [MASCOTE] [TEMA]
    _verificar_desbloqueio_cafeteria(usuario_logado())
    return jsonify(ok=True, redirect=url_for("objetivos"))
'''

PREVIA_EXISTENTE = '''@app.route("/objetivos/<int:id_objetivo>/fragmentar/previa", methods=["POST"])
@login_obrigatorio
def fragmentar_objetivo_previa(id_objetivo):
    objetivo = db.buscar_objetivo(id_objetivo, usuario_logado())
    if not objetivo:
        return jsonify(erro="objetivo não encontrado"), 404
    prazo = objetivo["prazo"]
    prazo_date = prazo.date() if hasattr(prazo, "date") else prazo
    return _previa_fragmentos(objetivo["titulo"], prazo_date, existente=True)
'''

CONFIRMAR_EXISTENTE = '''@app.route("/objetivos/<int:id_objetivo>/fragmentar/confirmar", methods=["POST"])
@login_obrigatorio
def fragmentar_objetivo_confirmar(id_objetivo):
    if not db.buscar_objetivo(id_objetivo, usuario_logado()):
        return jsonify(erro="objetivo não encontrado"), 404
    passos, erro = _validar_propostas(request.get_json(silent=True))
    if erro:
        return jsonify(erro=erro), 400      # nada foi criado: a lista inteira é conferida antes de gravar
    for p in passos:
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, p["titulo"], p["inicio"], p["fim"])

    _mascote_evento("tarefa_criada")   # [MASCOTE] [TEMA]
    _verificar_desbloqueio_cafeteria(usuario_logado())
    return jsonify(ok=True, redirect=url_for("objetivos"))
'''

TAREFAS_NOVO = '''def tarefas_filtradas(id_usuario, filtro, categoria=None):
    """'hoje' | 'proximas' | qualquer outro valor = todas. 'hoje' inclui as tarefas que começaram antes e ainda estão ativas
    (atravessam a meia-noite), como na Agenda. categoria: uma das categorias da tela, ou None/'todas'."""
    hoje = datetime.combine(datetime.now().date(), datetime.min.time())
    if filtro == "hoje":
        do_dia = db.listar_tarefas(id_usuario, data_inicio=hoje, inicio_antes=hoje + timedelta(days=1))
        anteriores = [t for t in db.listar_tarefas(id_usuario, data_inicio=hoje - timedelta(days=7), inicio_antes=hoje)
                      if t.get("data_fim") and t["data_fim"] > hoje]
        lista = sorted(list(anteriores) + list(do_dia), key=lambda t: t["data_inicio"])
    elif filtro == "proximas":
        lista = db.listar_tarefas(id_usuario, data_inicio=hoje + timedelta(days=1))
    else:
        lista = db.listar_tarefas(id_usuario)
    if categoria and categoria != "todas":
        lista = [t for t in lista if t.get("categoria") == categoria]
    return lista


def _render_tarefas(filtro="hoje", categoria_filtro="todas", **extra):
    return render_template(
        "tarefas.html",
        tarefas=tarefas_filtradas(usuario_logado(), filtro, categoria_filtro),
        filtro=filtro,
        categoria_filtro=categoria_filtro,
        **_pagina("tarefas", "Tarefas", **extra),
    )
'''

ROTA_TAREFAS_ANTIGA = '''def tarefas():
    return _render_tarefas(request.args.get("filtro", "hoje"))
'''
ROTA_TAREFAS_NOVA = '''def tarefas():
    categoria = request.args.get("categoria", "todas")
    if categoria not in ("todas", "trabalho", "estudo", "hobby", "pessoal", "saude", "outro"):
        categoria = "todas"
    return _render_tarefas(request.args.get("filtro", "hoje"), categoria_filtro=categoria)
'''

# ------------------------------------------------------------------ padrões do app.py
RE_PREVIA_NOVO = re.compile(r'@app\.route\("/objetivos/novo/fragmentar/previa", methods=\["POST"\]\)\n.*?    return jsonify\(propostas=propostas\)\n', re.S)
RE_CONFIRMAR_NOVO = re.compile(r'@app\.route\("/objetivos/novo/fragmentar/confirmar", methods=\["POST"\]\)\n.*?    return jsonify\(ok=True, redirect=url_for\("objetivos"\)\)\n', re.S)
RE_PREVIA_EXISTENTE = re.compile(r'@app\.route\("/objetivos/<int:id_objetivo>/fragmentar/previa", methods=\["POST"\]\)\n.*?    return jsonify\(propostas=propostas\)\n', re.S)
RE_CONFIRMAR_EXISTENTE = re.compile(r'@app\.route\("/objetivos/<int:id_objetivo>/fragmentar/confirmar", methods=\["POST"\]\)\n.*?    return jsonify\(ok=True, redirect=url_for\("objetivos"\)\)\n', re.S)
RE_TAREFAS_FILTRADAS = re.compile(r'def tarefas_filtradas\(id_usuario, filtro\):\n.*?        \*\*_pagina\("tarefas", "Tarefas", \*\*extra\),\n    \)\n', re.S)

CRIAR_ANTIGO = '''    titulo = request.form.get("titulo", "").strip()
    prazo = request.form.get("prazo") or None
    if titulo:
        db.criar_objetivo(usuario_logado(), titulo, prazo=prazo)
'''
CRIAR_NOVO = '''    titulo = request.form.get("titulo", "").strip()[:200]
    try:
        prazo = _prazo_iso(request.form.get("prazo"))
    except ValueError:
        abort(400)   # data inválida: só chega assim por envio manual (o campo de data do navegador não deixa)
    if titulo:
        db.criar_objetivo(usuario_logado(), titulo, prazo=prazo)
'''
EDITAR_ANTIGO = '''    titulo = request.form.get("titulo", "").strip()
    prazo = request.form.get("prazo") or None
    if titulo:
        db.atualizar_objetivo(id_objetivo, usuario_logado(), titulo=titulo, prazo=prazo)
'''
EDITAR_NOVO = '''    titulo = request.form.get("titulo", "").strip()[:200]
    try:
        prazo = _prazo_iso(request.form.get("prazo"))
    except ValueError:
        abort(400)   # data inválida: só chega assim por envio manual (o campo de data do navegador não deixa)
    if titulo:
        db.atualizar_objetivo(id_objetivo, usuario_logado(), titulo=titulo, prazo=prazo)
'''
FAIXA_LINHA = '    faixa_etaria = FAIXA_ETARIA_ONBOARDING_PARA_DB.get(dados.get("idade"))\n'


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def python_confere(texto):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(texto)
    try:
        py_compile.compile(f.name, doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, str(e)[:300]
    finally:
        Path(f.name).unlink(missing_ok=True)


def jinja_confere(texto):
    try:
        import jinja2
        jinja2.Environment().parse(texto)
        return True, ""
    except ImportError:
        return True, ""
    except Exception as e:
        return False, str(e)[:300]


def js_confere(texto):
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(texto)
        r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        Path(f.name).unlink(missing_ok=True)
        return r.returncode == 0, r.stderr.strip()[:300]
    except OSError:
        return True, ""


# ------------------------------------------------------------------ app.py
def preparar_app(texto):
    if MARCA in texto:
        return None, "app.py: já está atualizado (nada a fazer)."
    ancoras = {
        "ajudantes (calcular_quantidade_fragmentos)": texto.count("def calcular_quantidade_fragmentos(prazo, hoje=None):\n") == 1,
        "criar objetivo": texto.count(CRIAR_ANTIGO) == 1, "editar objetivo": texto.count(EDITAR_ANTIGO) == 1,
        "cadastro (faixa etária)": texto.count(FAIXA_LINHA) == 1,
        "prévia (objetivo novo)": len(RE_PREVIA_NOVO.findall(texto)) == 1, "prévia (objetivo existente)": len(RE_PREVIA_EXISTENTE.findall(texto)) == 1,
        "confirmar (objetivo novo)": len(RE_CONFIRMAR_NOVO.findall(texto)) == 1, "confirmar (objetivo existente)": len(RE_CONFIRMAR_EXISTENTE.findall(texto)) == 1,
        "lista de tarefas": len(RE_TAREFAS_FILTRADAS.findall(texto)) == 1, "rota /tarefas": texto.count(ROTA_TAREFAS_ANTIGA) == 1,
    }
    faltam = [nome for nome, ok in ancoras.items() if not ok]
    if faltam:
        return None, ("app.py: NÃO reconheci estes trechos: " + ", ".join(faltam) + ".\n"
                      "  (esta versão do arquivo é diferente da que eu conheço). O app.py ficou como estava. Me mande o arquivo e eu ajusto.")
    texto = texto.replace("def calcular_quantidade_fragmentos(prazo, hoje=None):\n", AJUDANTES + "def calcular_quantidade_fragmentos(prazo, hoje=None):\n", 1)
    texto = texto.replace(CRIAR_ANTIGO, CRIAR_NOVO, 1).replace(EDITAR_ANTIGO, EDITAR_NOVO, 1)
    texto = texto.replace(FAIXA_LINHA, VALIDACAO_CADASTRO + FAIXA_LINHA, 1)
    for padrao, novo in ((RE_PREVIA_NOVO, PREVIA_NOVO), (RE_PREVIA_EXISTENTE, PREVIA_EXISTENTE), (RE_CONFIRMAR_NOVO, CONFIRMAR_NOVO),
                         (RE_CONFIRMAR_EXISTENTE, CONFIRMAR_EXISTENTE), (RE_TAREFAS_FILTRADAS, TAREFAS_NOVO)):
        texto = padrao.sub(lambda m, n=novo: n, texto, count=1)
    texto = texto.replace(ROTA_TAREFAS_ANTIGA, ROTA_TAREFAS_NOVA, 1)
    return texto, "app.py: cadastro e objetivos validados, passos planejados dentro do prazo, filtro de categoria e Hoje corrigidos."


# ------------------------------------------------------------------ objetivos.html
JS_ESC = "    const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;' }[c]));\n"


BLOCO_CHIPS = """
  // [CHIPS] foco e ritmo: uma opção marcada por grupo, com o padrão já marcado (Geral / Moderado).
  // Antes, nada marcava a opção ao clicar: a escolha nunca chegava ao servidor (valia sempre geral e moderado).
  const CHIPS_PADRAO = { foco: 'geral', ritmo: 'moderado' };
  function marcarChip(grupo, chip) {
    grupo.querySelectorAll('.chip').forEach(c => { const ativo = c === chip; c.classList.toggle('active', ativo); c.setAttribute('aria-pressed', ativo ? 'true' : 'false'); });
  }
  function resetarChips() {
    document.querySelectorAll('[data-chip-group]').forEach(grupo => marcarChip(grupo, grupo.querySelector('.chip[data-value="' + CHIPS_PADRAO[grupo.dataset.chipGroup] + '"]')));
  }
  document.querySelectorAll('[data-chip-group]').forEach(grupo => {
    grupo.setAttribute('role', 'group');
    grupo.addEventListener('click', e => { const chip = e.target.closest('.chip'); if (chip && grupo.contains(chip)) marcarChip(grupo, chip); });
  });
  resetarChips();
"""
ESTILO_CHIPS = """<style>
  /* [CHIPS] a opção marcada se destaca além da cor: borda mais grossa e um ✓ antes do texto */
  [data-chip-group] .chip.active { border-width: 2px; }
  [data-chip-group] .chip.active::before { content: "\\2713\\00a0"; }
  [data-chip-group] .chip:focus-visible { outline: 3px solid #2563EB; outline-offset: 2px; }
</style>
"""
LINHA_LIMPA_CHIPS = "    document.querySelectorAll('[data-chip-group] .chip').forEach(c => c.classList.remove('active'));\n"
ANCORA_CTX = "  let fragAutoContexto = null; // { tipo: 'existente', idObjetivo } | { tipo: 'novo', titulo, prazo }\n"
ANCORA_MODAL = '<div id="modalFragAuto" class="modal-overlay hidden">\n'


def preparar_objetivos_html(texto):
    ja_esc, ja_chips = "const esc = (s)" in texto, "function resetarChips()" in texto
    if ja_esc and ja_chips:
        return None, "objetivos.html: já está atualizado (nada a fazer)."
    trocas = []
    if not ja_esc:
        trocas += [
            ("""onclick="abrirFragmentacaoAutomatica({{ o.id_objetivo }}, '{{ o.titulo|e }}')\"""",
             """onclick='abrirFragmentacaoAutomatica({{ o.id_objetivo }}, {{ o.titulo|tojson }})'"""),
            ("mostrarPreviaFragmentos(dados.propostas);", "mostrarPreviaFragmentos(dados.propostas, dados.aviso);"),
            ("  function mostrarPreviaFragmentos(propostas) {\n", "  function mostrarPreviaFragmentos(propostas, aviso) {\n" + JS_ESC),
            ("${p.titulo}</span>", "${esc(p.titulo)}</span>"),
            ("""Proposta — ${propostas.length} fragmentos</h3>\n""", """Proposta — ${propostas.length} fragmentos</h3>
      ${aviso ? `<p role="status" style="margin:-6px 0 12px;font-size:13px;line-height:1.5;font-weight:600;color:#B45309;">${esc(aviso)}</p>` : ''}\n"""),
            ("""      const dados = await resp.json();
      if (dados.redirect) window.location.href = dados.redirect;""", """      const dados = await resp.json();
      if (!resp.ok) { alert(dados.erro || 'Não foi possível adicionar os passos.'); this.disabled = false; this.textContent = 'Adicionar à agenda'; return; }
      if (dados.redirect) window.location.href = dados.redirect;"""),
        ]
    if not ja_chips:
        trocas += [(ANCORA_CTX, ANCORA_CTX + BLOCO_CHIPS), (ANCORA_MODAL, ESTILO_CHIPS + ANCORA_MODAL)]
    faltam = [antigo[:60] for antigo, _ in trocas if texto.count(antigo) != 1]
    if not ja_chips and texto.count(LINHA_LIMPA_CHIPS) != 2:
        faltam.append("as duas linhas que limpam as opções (remove('active'))")
    if faltam:
        return None, ("objetivos.html: NÃO reconheci estes trechos: " + "; ".join(faltam) + "\n  O arquivo ficou como estava. Me mande o arquivo e eu ajusto.")
    for antigo, novo_ in trocas:
        texto = texto.replace(antigo, novo_, 1)
    if not ja_chips:
        texto = texto.replace(LINHA_LIMPA_CHIPS, "    resetarChips();\n")
    return texto, "objetivos.html: botão de fragmentar seguro, prévia sem HTML da IA, e as opções de foco e ritmo agora marcam e valem."


# ------------------------------------------------------------------ semana_tematica.js
def preparar_semana_js(texto):
    alvos = [("info.resumo = t ? plural(t, 'planejada', 'planejadas') : 'livre';", "info.resumo = t ? plural(t, 'planejada', 'planejadas') : 'sem tarefas';"),
             ("info.estado = 'livre'; info.resumo = 'livre'; info.nivel = 0;", "info.estado = 'livre'; info.resumo = 'sem tarefas'; info.nivel = 0;")]
    if "info.resumo = 'sem tarefas'" in texto and "livre: 'livre'" not in texto:
        return None, "semana_tematica.js: já está atualizado (nada a fazer)."
    for antigo, _ in alvos:
        if texto.count(antigo) != 1:
            return None, "semana_tematica.js: NÃO reconheci o trecho do resumo do dia ('livre'). O arquivo ficou como estava."
    novo = texto
    for antigo, trocado in alvos:
        novo = novo.replace(antigo, trocado, 1)
    novo = novo.replace("livre: 'livre'", "livre: 'sem tarefas'")
    return novo, "semana_tematica.js: o dia sem tarefas passa a dizer 'sem tarefas' (livre não é o mesmo que disponível)."


def mostrar_diff(nome, antes, depois):
    linhas = list(difflib.unified_diff(antes.splitlines(), depois.splitlines(), f"{nome} (atual)", f"{nome} (novo)", lineterm="", n=0))
    print("\n".join(linhas[:40]) + (f"\n   ... (diff cortado: {len(linhas)} linhas)" if len(linhas) > 40 else ""))


def main():
    ap = argparse.ArgumentParser(description="Lote 1 de correções do relatório de avaliação.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    alvos = [(RAIZ / "app.py", preparar_app, python_confere), (RAIZ / "templates" / "objetivos.html", preparar_objetivos_html, jinja_confere),
             (RAIZ / "static" / "semana_tematica.js", preparar_semana_js, js_confere)]
    plano, problemas = [], 0
    for arquivo, preparar, confere in alvos:
        if not arquivo.exists():
            print(f"   {arquivo.relative_to(RAIZ)}: não existe (pulei).")
            problemas += 1
            continue
        texto, crlf = ler(arquivo)
        novo, msg = preparar(texto)
        print(("-> " if novo is not None else "   ") + msg)
        if novo is None:
            problemas += 0 if "nada a fazer" in msg else 1
            continue
        ok, erro = confere(novo)
        if not ok:
            print(f"   ERRO: o arquivo novo não passou na conferência de sintaxe ({erro}). Nada foi gravado.")
            problemas += 1
            continue
        plano.append((arquivo, texto, novo, crlf))
    if not plano:
        print("\nNada para aplicar." + (" Veja as mensagens acima." if problemas else ""))
        return 1 if problemas else 0
    print()
    for arquivo, antes, depois, _ in plano:
        mostrar_diff(arquivo.name, antes, depois)
        print()
    if not args.aplicar:
        print("Nada foi alterado. Para aplicar:  python corrigir_lote1.py --aplicar")
        return 0
    for arquivo, _, depois, crlf in plano:
        copia = arquivo.with_name(arquivo.name + ".bak")
        n = 1
        while copia.exists():
            n += 1
            copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
        shutil.copy2(arquivo, copia)
        arquivo.write_bytes(gravar_texto(depois, crlf))
        print(f"gravado: {arquivo.relative_to(RAIZ)}  (cópia do original: {copia.name})")
    print("\nPronto. Reinicie o servidor e rode o verificar_pacote.py.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
