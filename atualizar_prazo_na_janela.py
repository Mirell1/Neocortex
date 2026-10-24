"""
NEOCORTEX - atualizar_prazo_na_janela.py

O prazo do objetivo sai do onboarding (para aliviá-lo) e passa a ser perguntado na janela "Duas perguntas rápidas" (a que abre
para dividir o objetivo em passos), SÓ quando o objetivo ainda não tem prazo.

  app.py                    a prévia usa o prazo escolhido na janela; o prazo só é GRAVADO no objetivo ao confirmar os passos
                            (quem cancelar não fica com um prazo que não escolheu). Objetivo que já tem prazo não é alterado.
  templates/objetivos.html  campo "Até quando?" na janela, mostrado só quando o objetivo não tem prazo

Pré-requisito: o lote 1 (corrigir_lote1.py) já aplicado. O módulo static/onboarding_objetivo.js novo (sem o campo de prazo) vem no
mesmo pacote: basta extraí-lo por cima do antigo.

Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_prazo_na_janela.py            # só mostra
    python atualizar_prazo_na_janela.py --aplicar  # grava (cópias .bak; confere a sintaxe antes)

Rodar de novo é seguro. Se não reconhecer um trecho, NÃO mexe naquele arquivo e explica.
"""
import argparse
import difflib
import py_compile
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(".").resolve()
MARCA = "# [PRAZO-JANELA]"

PREVIA_NOVA = '''# [PRAZO-JANELA] objetivo sem prazo: a janela "Duas perguntas rápidas" pergunta o prazo; a prévia usa o que foi escolhido
@app.route("/objetivos/<int:id_objetivo>/fragmentar/previa", methods=["POST"])
@login_obrigatorio
def fragmentar_objetivo_previa(id_objetivo):
    objetivo = db.buscar_objetivo(id_objetivo, usuario_logado())
    if not objetivo:
        return jsonify(erro="objetivo não encontrado"), 404
    prazo = objetivo["prazo"]
    prazo_date = prazo.date() if hasattr(prazo, "date") else prazo
    if prazo_date:
        return _previa_fragmentos(objetivo["titulo"], prazo_date, existente=True)
    try:
        prazo_date = _prazo_date(request.form.get("prazo"))      # vazio -> None (sem prazo: 4 passos, uma semana entre eles)
    except ValueError:
        return jsonify(erro="Prazo inválido. Escolha uma data de hoje em diante."), 400
    return _previa_fragmentos(objetivo["titulo"], prazo_date)
'''

CONFIRMAR_NOVO = '''@app.route("/objetivos/<int:id_objetivo>/fragmentar/confirmar", methods=["POST"])
@login_obrigatorio
def fragmentar_objetivo_confirmar(id_objetivo):
    objetivo = db.buscar_objetivo(id_objetivo, usuario_logado())
    if not objetivo:
        return jsonify(erro="objetivo não encontrado"), 404
    passos, erro = _validar_propostas(request.get_json(silent=True))
    if erro:
        return jsonify(erro=erro), 400      # nada foi criado: a lista inteira é conferida antes de gravar
    try:
        prazo_escolhido = _prazo_iso(request.args.get("prazo"))
    except ValueError:
        return jsonify(erro="Prazo inválido."), 400
    if prazo_escolhido and prazo_escolhido < date.today().isoformat():
        return jsonify(erro="O prazo já passou. Escolha uma data de hoje em diante."), 400
    if prazo_escolhido and not objetivo["prazo"]:
        db.atualizar_objetivo(id_objetivo, usuario_logado(), prazo=prazo_escolhido)   # o prazo escolhido na janela passa a ser o do objetivo
    for p in passos:
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, p["titulo"], p["inicio"], p["fim"])

    _mascote_evento("tarefa_criada")   # [MASCOTE] [TEMA]
    _verificar_desbloqueio_cafeteria(usuario_logado())
    return jsonify(ok=True, redirect=url_for("objetivos"))
'''

RE_PREVIA = re.compile(r'@app\.route\("/objetivos/<int:id_objetivo>/fragmentar/previa", methods=\["POST"\]\)\n@login_obrigatorio\ndef fragmentar_objetivo_previa\(id_objetivo\):\n'
                       r'.*?    return _previa_fragmentos\(objetivo\["titulo"\], prazo_date, existente=True\)\n', re.S)
RE_CONFIRMAR = re.compile(r'@app\.route\("/objetivos/<int:id_objetivo>/fragmentar/confirmar", methods=\["POST"\]\)\n@login_obrigatorio\ndef fragmentar_objetivo_confirmar\(id_objetivo\):\n'
                          r'.*?    return jsonify\(ok=True, redirect=url_for\("objetivos"\)\)\n', re.S)

BLOCO_HTML = '''      <div id="fragAutoPrazoBloco" class="hidden" style="margin-bottom:20px;">
        <label class="nc-label" for="fragAutoPrazo">Até quando? <span style="font-weight:500;color:var(--nc-text2);">(opcional)</span></label>
        <input id="fragAutoPrazo" type="date" class="nc-input" style="max-width:220px;" aria-describedby="fragAutoPrazoDica">
        <p id="fragAutoPrazoDica" style="margin:8px 0 0;font-size:13px;line-height:1.45;color:var(--nc-text2);">Sem prazo, eu sugiro 4 passos. Com um prazo, eles se distribuem até a data.</p>
      </div>
'''
BOTAO_GERAR = '      <button type="button" id="btnGerarFragmentos" class="btn-primary" style="width:100%;height:48px;margin-bottom:10px;">Gerar sugestão</button>\n'

JS_CAMPO = '''  // [PRAZO-JANELA] o prazo é perguntado aqui (e não no onboarding) quando o objetivo ainda não tem um
  function mostrarCampoPrazo(mostrar) {
    const bloco = document.getElementById('fragAutoPrazoBloco'), campo = document.getElementById('fragAutoPrazo');
    bloco.classList.toggle('hidden', !mostrar);
    campo.value = '';
    if (mostrar) {
      const pad = (n) => String(n).padStart(2, '0'), fmt = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());   // data local, não UTC
      const d = new Date();
      campo.min = fmt(d);
      d.setFullYear(d.getFullYear() + 10);
      campo.max = fmt(d);
    }
  }

'''
SCRIPT_ABRIR_ANTIGO = '''    var id = {{ abrir_fragmentacao.id_objetivo|tojson }}, titulo = {{ abrir_fragmentacao.titulo|tojson }};
    abrirFragmentacaoAutomatica(id, titulo);
'''
SCRIPT_ABRIR_NOVO = '''    var id = {{ abrir_fragmentacao.id_objetivo|tojson }}, titulo = {{ abrir_fragmentacao.titulo|tojson }}, tem = {{ (abrir_fragmentacao.prazo is not none)|tojson }};
    abrirFragmentacaoAutomatica(id, titulo, tem);
'''


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


def preparar_app(texto):
    if MARCA in texto:
        return None, "app.py: já está atualizado (nada a fazer)."
    if "# [LOTE1]" not in texto:
        return None, "app.py: o lote 1 ainda NÃO está aplicado (rode primeiro:  python corrigir_lote1.py --aplicar). O app.py ficou como estava."
    if len(RE_PREVIA.findall(texto)) != 1 or len(RE_CONFIRMAR.findall(texto)) != 1:
        return None, ("app.py: NÃO reconheci a prévia ou a confirmação dos passos de um objetivo existente (a versão do lote 1 que eu conheço).\n"
                      "  O app.py ficou como estava. Me mande o arquivo e eu ajusto.")
    texto = RE_PREVIA.sub(lambda m: PREVIA_NOVA, texto, count=1)
    texto = RE_CONFIRMAR.sub(lambda m: CONFIRMAR_NOVO, texto, count=1)
    return texto, "app.py: a prévia usa o prazo escolhido na janela e a confirmação o grava no objetivo (só se ele ainda não tinha)."


def preparar_objetivos_html(texto):
    if "fragAutoPrazoBloco" in texto:
        return None, "objetivos.html: já tem o campo de prazo na janela (nada a fazer)."
    trocas = [
        ("onclick='abrirFragmentacaoAutomatica({{ o.id_objetivo }}, {{ o.titulo|tojson }})'",
         "onclick='abrirFragmentacaoAutomatica({{ o.id_objetivo }}, {{ o.titulo|tojson }}, {{ (o.prazo is not none)|tojson }})'"),
        (BOTAO_GERAR, BLOCO_HTML + BOTAO_GERAR),
        ("  function abrirFragmentacaoAutomatica(idObjetivo, titulo) {\n    fragAutoContexto = { tipo: 'existente', idObjetivo };\n",
         JS_CAMPO + "  function abrirFragmentacaoAutomatica(idObjetivo, titulo, temPrazo) {\n    fragAutoContexto = { tipo: 'existente', idObjetivo };\n    mostrarCampoPrazo(temPrazo === false);   // só pergunta o prazo se o objetivo ainda não tem\n"),
        ("    fragAutoContexto = { tipo: 'novo', titulo, prazo };\n", "    fragAutoContexto = { tipo: 'novo', titulo, prazo };\n    mostrarCampoPrazo(false);   // o prazo já foi preenchido no formulário do objetivo novo\n"),
        ("      url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/previa`;\n    }\n",
         "      url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/previa`;\n      const prazoEscolhido = document.getElementById('fragAutoPrazo').value;\n      fragAutoContexto.prazoEscolhido = prazoEscolhido || null;\n      if (prazoEscolhido) form.set('prazo', prazoEscolhido);\n    }\n"),
        ("        url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/confirmar`;\n",
         "        url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/confirmar`\n          + (fragAutoContexto.prazoEscolhido ? '?prazo=' + encodeURIComponent(fragAutoContexto.prazoEscolhido) : '');\n"),
    ]
    faltam = [antigo[:70] for antigo, _ in trocas if texto.count(antigo) != 1]
    if faltam:
        return None, ("objetivos.html: NÃO reconheci estes trechos: " + "; ".join(faltam) + "\n  (precisa do lote 1 aplicado). O arquivo ficou como estava. Me mande o arquivo e eu ajusto.")
    for antigo, novo in trocas:
        texto = texto.replace(antigo, novo, 1)
    if SCRIPT_ABRIR_ANTIGO in texto:       # a abertura automática depois do cadastro (objetivo v2), se estiver aplicada
        texto = texto.replace(SCRIPT_ABRIR_ANTIGO, SCRIPT_ABRIR_NOVO, 1)
    return texto, "objetivos.html: a janela pergunta 'Até quando?' quando o objetivo ainda não tem prazo."


def mostrar_diff(nome, antes, depois):
    linhas = list(difflib.unified_diff(antes.splitlines(), depois.splitlines(), f"{nome} (atual)", f"{nome} (novo)", lineterm="", n=0))
    print("\n".join(linhas[:40]) + (f"\n   ... (diff cortado: {len(linhas)} linhas)" if len(linhas) > 40 else ""))


def main():
    ap = argparse.ArgumentParser(description="Leva a pergunta do prazo do onboarding para a janela dos passos.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    alvos = [(RAIZ / "app.py", preparar_app, python_confere), (RAIZ / "templates" / "objetivos.html", preparar_objetivos_html, jinja_confere)]
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
        print("Nada foi alterado. Para aplicar:  python atualizar_prazo_na_janela.py --aplicar")
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
    print("\nPronto. Reinicie o servidor.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
