"""
NEOCORTEX - atualizar_objetivo_onboarding.py

Liga o novo passo de objetivo do onboarding (static/onboarding_objetivo.js) ao resto do sistema:

  app.py                     o cadastro cria o objetivo com título, detalhes (descrição) e prazo; se a pessoa pediu ajuda para
                             dividir em passos, /objetivos abre a prévia dos passos uma vez, depois do cadastro
  templates/onboarding.html  carrega o módulo novo depois do onboarding.js
  templates/objetivos.html   mostra os detalhes no card do objetivo e abre a prévia dos passos quando for o caso
  templates/cadastro_sucesso.html   o botão da tela de sucesso leva para a prévia (quando ela foi pedida)

NÃO mexe no onboarding.js. Funciona com o app.py original ou com a versão da correção anterior (corrigir_objetivo_onboarding.py).

Por padrão só MOSTRA o que mudaria e não altera nada. Rode na pasta do projeto (a do app.py):

    python atualizar_objetivo_onboarding.py            # só mostra
    python atualizar_objetivo_onboarding.py --aplicar  # grava (cópias .bak; confere a sintaxe antes)

Rodar de novo é seguro. Se não reconhecer um trecho, NÃO mexe naquele arquivo e explica como fazer à mão.
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
MARCA = "# [OBJETIVO v2]"

AJUDANTES_PY = '''# [OBJETIVO v2] objetivos escritos no cadastro
def _objetivos_do_onboarding(dados):
    """Objetivos do cadastro: a pergunta "objetivo" ({titulo, detalhes, prazo, fragmentar} ou só texto) e/ou a lista "objetivos"
    (textos ou dicionários). Limpa os textos, confere o prazo (de hoje até 10 anos) e fica com no máximo 5 válidos."""
    brutos = []
    if isinstance(dados.get("objetivo"), (str, dict)):
        brutos.append(dados["objetivo"])
    if isinstance(dados.get("objetivos"), list):
        brutos.extend(dados["objetivos"])
    hoje = date.today()
    saida = []
    for item in brutos[:50]:
        if len(saida) == 5:
            break
        if isinstance(item, str):
            item = {"titulo": item}
        if not isinstance(item, dict):
            continue
        titulo = item.get("titulo")
        titulo = " ".join(titulo.split())[:200] if isinstance(titulo, str) else ""
        if not titulo:
            continue
        detalhes = item.get("detalhes", item.get("descricao"))
        detalhes = detalhes.strip()[:500] if isinstance(detalhes, str) else ""
        prazo = item.get("prazo")
        try:
            prazo = datetime.strptime(prazo, "%Y-%m-%d").date() if isinstance(prazo, str) else None
        except ValueError:
            prazo = None
        if prazo and not (hoje <= prazo <= hoje + timedelta(days=3653)):
            prazo = None
        saida.append({"titulo": titulo, "descricao": detalhes or None, "prazo": prazo.isoformat() if prazo else None,
                      "fragmentar": item.get("fragmentar") is True})
    return saida


def _criar_objetivo_do_cadastro(id_usuario, obj):
    """Cria o objetivo. Se o banco desta versão não aceitar 'descricao', cria sem ela: o cadastro nunca quebra por isso."""
    try:
        return db.criar_objetivo(id_usuario, obj["titulo"], descricao=obj["descricao"], prazo=obj["prazo"])
    except TypeError:
        return db.criar_objetivo(id_usuario, obj["titulo"], prazo=obj["prazo"])


'''

LACO_NOVO = '''    id_para_fragmentar = None
    for obj in _objetivos_do_onboarding(dados):
        id_objetivo = _criar_objetivo_do_cadastro(id_usuario, obj)
        if obj["fragmentar"] and id_para_fragmentar is None and id_objetivo:
            id_para_fragmentar = id_objetivo
'''

# o laço ORIGINAL do projeto e o da correção anterior (v1)
LACO_ORIGINAL = re.compile(
    r'[ \t]*for obj in \(dados\.get\("objetivos"\) or \[\]\):\n'
    r'[ \t]*    titulo = \(obj\.get\("titulo"\) or ""\)\.strip\(\)\n'
    r'[ \t]*    if titulo:\n'
    r'[ \t]*        db\.criar_objetivo\(id_usuario, titulo, prazo=obj\.get\("prazo"\) or None\)\n')
LACO_V1 = re.compile(
    r'[ \t]*for titulo, prazo in _objetivos_do_onboarding\(dados\):\n'
    r'[ \t]*    db\.criar_objetivo\(id_usuario, titulo, prazo=prazo\)\n')
AJUDANTE_V1 = re.compile(r'def _objetivos_do_onboarding\(dados\):\n.*?    return saida\n\n\n', re.S)

RETORNO_CADASTRO = '    return jsonify({"redirect": url_for("cadastro_sucesso")})\n'
SUCESSO_ANTIGO = '''def cadastro_sucesso():
    return render_template("cadastro_sucesso.html")
'''
SUCESSO_NOVO = '''def cadastro_sucesso():
    pedido = session.get("abrir_fragmentacao")   # quem pediu ajuda com os passos do objetivo segue para a prévia
    proximo = url_for("objetivos", fragmentar=pedido) if pedido else url_for("tarefas")
    return render_template("cadastro_sucesso.html", proximo=proximo)
'''
OBJ_ROTA_ANTIGA = '''        db_fragmentos=fragmentos,
'''
OBJ_ROTA_ANTES = '''    return render_template(
        "objetivos.html",
        objetivos=lista,
'''

SCRIPT_ABRIR = '''{% if abrir_fragmentacao %}
<script>
  // [ONBOARDING] a pessoa pediu ajuda para dividir o objetivo em passos: abre a prévia uma vez
  window.addEventListener('load', function () {
    var id = {{ abrir_fragmentacao.id_objetivo|tojson }}, titulo = {{ abrir_fragmentacao.titulo|tojson }};
    abrirFragmentacaoAutomatica(id, titulo);
    var h = document.querySelector('#fragAutoPerguntas h3');
    if (h) {
      var p = document.createElement('p');
      p.style.cssText = 'margin:-8px 0 16px;font-size:14px;line-height:1.5;color:var(--nc-text2);';
      p.textContent = 'Vamos dividir \\u201c' + titulo + '\\u201d em passos pequenos. Escolha como você prefere:';
      h.insertAdjacentElement('afterend', p);
    }
    if (window.history && history.replaceState) history.replaceState(null, '', location.pathname);   // atualizar a página não reabre
  });
</script>
{% endif %}
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
    except ImportError:
        return True, "(jinja2 não encontrado: não consegui conferir o template)"
    try:
        jinja2.Environment().parse(texto)
        return True, ""
    except jinja2.TemplateSyntaxError as e:
        return False, f"{e.message} (linha {e.lineno})"


# ------------------------------------------------------------------ app.py
def preparar_app(texto):
    if MARCA in texto:
        return None, "app.py: já está atualizado (nada a fazer)."
    rota_perfil = re.search(r'^@app\.route\("/cadastro/perfil"', texto, re.M)
    if not rota_perfil or texto.count(RETORNO_CADASTRO) != 1 or texto.count(SUCESSO_ANTIGO) != 1 or texto.count(OBJ_ROTA_ANTES) != 1 or texto.count(OBJ_ROTA_ANTIGA) != 1:
        return None, ("app.py: NÃO reconheci a rota do cadastro, a do sucesso ou a de /objetivos (esta versão do arquivo é diferente da que eu conheço).\n"
                      "  O app.py ficou como estava. Me mande o arquivo e eu ajusto.")

    # 1) ajudante (substitui o da correção anterior, se existir)
    if AJUDANTE_V1.search(texto):
        texto = AJUDANTE_V1.sub(lambda m: AJUDANTES_PY, texto, count=1)
    else:
        rota_perfil = re.search(r'^@app\.route\("/cadastro/perfil"', texto, re.M)
        texto = texto[:rota_perfil.start()] + AJUDANTES_PY + texto[rota_perfil.start():]

    # 2) laço que cria os objetivos
    laco = LACO_V1.search(texto) or LACO_ORIGINAL.search(texto)
    if not laco:
        return None, ("app.py: NÃO reconheci o trecho que cria os objetivos no cadastro.\n"
                      "  Troque o laço por:  for obj in _objetivos_do_onboarding(dados): ...  (veja o corpo em LACO_NOVO neste script).")
    texto = texto[:laco.start()] + LACO_NOVO + texto[laco.end():]

    # 3) guarda o pedido de passos na sessão, logo antes do retorno do cadastro
    texto = texto.replace(RETORNO_CADASTRO, '''    if id_para_fragmentar:   # pediu ajuda para dividir o objetivo em passos: a tela de Objetivos abre a prévia depois do cadastro
        session["abrir_fragmentacao"] = id_para_fragmentar

''' + RETORNO_CADASTRO, 1)

    # 4) tela de sucesso: o botão leva para a prévia quando ela foi pedida
    texto = texto.replace(SUCESSO_ANTIGO, SUCESSO_NOVO, 1)

    # 5) /objetivos: abre a prévia uma vez (só se o objetivo é da pessoa e ainda não tem passos)
    texto = texto.replace(OBJ_ROTA_ANTES, '''    # [ONBOARDING] pediu ajuda para dividir o objetivo em passos: abre a prévia uma vez (só se o objetivo é dela e ainda não tem passos)
    pedido = request.args.get("fragmentar", type=int) or session.get("abrir_fragmentacao")
    session.pop("abrir_fragmentacao", None)
    abrir = next((o for o in lista if o["id_objetivo"] == pedido and not fragmentos[o["id_objetivo"]]), None) if pedido else None
''' + OBJ_ROTA_ANTES, 1)
    texto = texto.replace(OBJ_ROTA_ANTIGA, OBJ_ROTA_ANTIGA + "        abrir_fragmentacao=abrir,\n", 1)
    return texto, "app.py: o cadastro cria o objetivo (título, detalhes, prazo) e /objetivos abre a prévia dos passos quando pedida."


# ------------------------------------------------------------------ templates
def preparar_onboarding_html(texto):
    if "onboarding_objetivo.js" in texto:
        return None, "onboarding.html: já carrega o módulo do objetivo (nada a fazer)."
    padrao = re.compile(r"([ \t]*)(<script src=\"\{\{ url_for\('static', filename='onboarding\.js'\) \}\}\"></script>)")
    achados = padrao.findall(texto)
    if len(achados) != 1:
        return None, ("onboarding.html: NÃO achei a linha que carrega o onboarding.js.\n"
                      "  Faça à mão: logo depois dela, acrescente\n"
                      "  <script src=\"{{ url_for('static', filename='onboarding_objetivo.js') }}\"></script>")
    return padrao.sub(lambda m: m.group(1) + m.group(2) + "\n" + m.group(1) + "<script src=\"{{ url_for('static', filename='onboarding_objetivo.js') }}\"></script>", texto, count=1), \
        "onboarding.html: carrega o módulo do passo de objetivo depois do onboarding.js."


def preparar_objetivos_html(texto):
    ja_descricao, ja_script = "o.descricao" in texto, "abrir_fragmentacao" in texto
    if ja_descricao and ja_script:
        return None, "objetivos.html: já mostra os detalhes e abre a prévia (nada a fazer)."
    novo = texto
    if not ja_descricao:
        titulo_p = re.compile(r'(<p style="[^"]*">\{\{ o\.titulo \}\}</p>)')
        if len(titulo_p.findall(novo)) != 1:
            return None, ("objetivos.html: NÃO achei o título do objetivo no card (o trecho <p ...>{{ o.titulo }}</p>).\n"
                          "  Faça à mão: logo depois dele, acrescente\n"
                          "  {% if o.descricao %}<p style=\"margin:0 0 6px;font-size:13px;color:var(--nc-text2);white-space:pre-wrap;\">{{ o.descricao }}</p>{% endif %}")
        novo = titulo_p.sub(lambda m: m.group(1) + '\n          {% if o.descricao %}<p style="margin:0 0 6px;font-size:13px;line-height:1.5;color:var(--nc-text2);'
                            'white-space:pre-wrap;overflow-wrap:anywhere;">{{ o.descricao }}</p>{% endif %}', novo, count=1)
    if not ja_script:
        fim = list(re.finditer(r"\{% endblock %\}", novo))
        if not fim or "abrirFragmentacaoAutomatica" not in novo:
            return None, "objetivos.html: NÃO reconheci a página (sem a função abrirFragmentacaoAutomatica ou sem o fim do bloco). O arquivo ficou como estava."
        ultimo = fim[-1]
        novo = novo[:ultimo.start()] + SCRIPT_ABRIR + novo[ultimo.start():]
    return novo, "objetivos.html: mostra os detalhes do objetivo e abre a prévia dos passos quando pedida."


def preparar_sucesso_html(texto):
    if "proximo or url_for" in texto:
        return None, "cadastro_sucesso.html: já usa o botão com destino dinâmico (nada a fazer)."
    alvo = "href=\"{{ url_for('tarefas') }}\""
    if texto.count(alvo) != 1:
        return None, ("cadastro_sucesso.html: NÃO achei o botão que leva para Tarefas.\n"
                      "  Sem isso a prévia ainda abre, mas só quando a pessoa entrar em Objetivos (o app.py guarda o pedido na sessão).\n"
                      "  Faça à mão: troque  href=\"{{ url_for('tarefas') }}\"  por  href=\"{{ proximo or url_for('tarefas') }}\"")
    return texto.replace(alvo, "href=\"{{ proximo or url_for('tarefas') }}\"", 1), "cadastro_sucesso.html: o botão leva para a prévia quando ela foi pedida."


def mostrar_diff(nome, antes, depois):
    linhas = list(difflib.unified_diff(antes.splitlines(), depois.splitlines(), f"{nome} (atual)", f"{nome} (novo)", lineterm="", n=1))
    print("\n".join(linhas[:60]) + ("\n   ... (diff cortado)" if len(linhas) > 60 else ""))


def main():
    ap = argparse.ArgumentParser(description="Liga o novo passo de objetivo do onboarding ao servidor e às telas.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()

    alvos = [(RAIZ / "app.py", preparar_app, python_confere), (RAIZ / "templates" / "onboarding.html", preparar_onboarding_html, jinja_confere),
             (RAIZ / "templates" / "objetivos.html", preparar_objetivos_html, jinja_confere), (RAIZ / "templates" / "cadastro_sucesso.html", preparar_sucesso_html, jinja_confere)]
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    if not (RAIZ / "static" / "onboarding_objetivo.js").exists():
        print("ATENÇÃO: não achei static/onboarding_objetivo.js. Copie esse arquivo do pacote para a pasta static/ antes de usar o onboarding novo.\n")

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
        print("Nada foi alterado. Para aplicar:  python atualizar_objetivo_onboarding.py --aplicar")
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
    print("\nPronto. Reinicie o servidor e refaça um cadastro até o passo de objetivo.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
