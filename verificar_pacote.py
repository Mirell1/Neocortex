"""
NEOCORTEX - verificar_pacote.py

Confere se um pacote de arquivos recebido (temas, mascote, telas) NÃO desfez o que já
estava funcionando. Rode na pasta do projeto, DEPOIS de copiar os arquivos do pacote:

    python verificar_pacote.py

Só lê arquivos: não muda nada. Termina com código 1 se achar algum problema.
"""
import ast
import collections
import re
import sys
from pathlib import Path

RAIZ = Path(".")
problemas = 0


def ler(caminho):
    p = RAIZ / caminho
    return p.read_text(encoding="utf-8", errors="replace").replace("\r", "") if p.exists() else None


def checa(descricao, ok, dica=""):
    global problemas
    if ok:
        print(f"  OK     {descricao}")
    else:
        problemas += 1
        print(f"  FALTA  {descricao}" + (f"\n         -> {dica}" if dica else ""))


def contem(texto, *trechos):
    return texto is not None and all(t in texto for t in trechos)


# ------------------------------------------------------------------ app.py
print("\napp.py")
app = ler("app.py")
if app is None:
    checa("app.py existe (rode este script na pasta do projeto)", False)
else:
    try:
        arvore = ast.parse(app)
        checa("compila sem erro de sintaxe", True)
        nomes = [n.name for n in arvore.body if isinstance(n, ast.FunctionDef)]
        repetidas = [n for n, c in collections.Counter(nomes).items() if c > 1]
        checa("nenhuma função com nome repetido", not repetidas, f"repetidas: {repetidas} (a última sobrescreve as outras em silêncio)")
    except SyntaxError as e:
        checa("compila sem erro de sintaxe", False, f"linha {e.lineno}: {e.msg}")
    checa("os eventos do mascote são consumidos num único lugar", app.count('session.pop("mascote_eventos"') == 1,
          "dois context processors fazendo pop deixam o segundo com lista vazia")
    checa("acessório e cor guardados por mascote", contem(app, "_chave_mascote", "CORES_MASCOTE"))
    checa("liberação de temas pelo mecanismo genérico", contem(app, "_liberar_tema", "_temas_liberados"))
    checa("equipar acessório bloqueado continua dando 403", contem(app, "abort(403)"))

# --------------------------------------------------------------- mascote_robo.js
print("\nstatic/mascote_robo.js")
js = ler("static/mascote_robo.js")
checa("arquivo existe", js is not None)
if js:
    checa("atalho: passar o mouse mostra a dica", "addEventListener('mouseenter'" in js, "o pacote pode ter voltado ao 'clique = dica'")
    checa("atalho: clicar abre o Assistente", "raiz.dataset.assistenteUrl" in js)
    checa("atalho: tela de toque e teclado continuam acessíveis", contem(js, "(hover: none)", ":focus-visible"))
    checa("cor e brilho vêm do HTML (data-cor)", "raiz.dataset.cor" in js)
    svgs = re.findall(r"const (SVG_[A-Z]+) = `(.*?)`;", js, re.S)
    checa(f"há mascotes no arquivo ({', '.join(n for n, _ in svgs)})", len(svgs) >= 3)
    for nome, corpo in svgs:
        falta = [a for a in ("gorro", "oculos", "cachecol") if f"nc-acessorio-{a}" not in corpo]
        checa(f"{nome}: tem os 3 encaixes de acessório", not falta, f"faltando: {falta}")

# --------------------------------------------------------------- base_app_novo.html
print("\ntemplates/base_app_novo.html")
base = ler("templates/base_app_novo.html")
checa("arquivo existe", base is not None)
if base:
    checa("acessibilidade no <html> (fonte, contraste, tipografia)", contem(base, "data-fonte=", "data-contraste=", "data-tipografia="))
    checa("fonte Lexend (dislexia) e VLibras", contem(base, "family=Lexend", "vlibras-plugin.js"))
    checa("menu com Jornada e Loja", contem(base, "url_for('jornada')", "url_for('mascote_loja')"))
    checa("mascote pelo parcial (acessório, cor e atalho)", contem(base, 'include "partials/mascote.html"'))
    checa("eventos do mascote protegidos contra lista ausente", "(mascote_eventos or [])" in base)
    checa("mascote sobe acima do botão + em Rotina e Objetivos", contem(base, "'rotina'", "'objetivos'", "acima-do-fab"))
    ifs, fim = len(re.findall(r"{%-?\s*if\b", base)), len(re.findall(r"{%-?\s*endif\b", base))
    checa(f"{{% if %}} e {{% endif %}} balanceados ({ifs} e {fim})", ifs == fim)

print("\ntemplates/partials/mascote.html")
parcial = ler("templates/partials/mascote.html")
checa("passa skin, cor e o atalho para o Assistente", contem(parcial, "data-skin=", "data-cor=", "data-assistente-url="))

# ------------------------------------------------------------------ CSS dos temas
print("\nCSS dos temas")
estaticos = sorted((RAIZ / "static").glob("*.css")) if (RAIZ / "static").exists() else []
comum = ler("static/temas_comum.css") or ""
variaveis_titulo = set()
for css in estaticos:
    texto = css.read_text(encoding="utf-8", errors="replace")
    variaveis_titulo |= set(re.findall(r"(--[a-z]+-titulo)\s*:", texto))
    checa(f"{css.name}: chaves balanceadas", texto.count("{") == texto.count("}"))
sem_cobertura = sorted(v for v in variaveis_titulo if f"{v}: 'Lexend'" not in comum)
checa("fonte para dislexia vale em todos os títulos temáticos", not sem_cobertura and bool(comum),
      f"em temas_comum.css, a regra html[data-tipografia=\"dislexia\"] precisa redefinir: {sem_cobertura}")

# ------------------------------------------------------------------ interface clássica
print("\nInterface clássica (a original, base de todo mundo)")
dash, cal, conf = ler("templates/dashboard.html"), ler("templates/calendario.html"), ler("templates/configuracoes.html")
checa("a tela inicial original (cartão 'Progresso de hoje') continua no dashboard.html", contem(dash, "nc-hero-progresso", "Progresso de hoje"),
      "a interface original não pode ser descartada: ela é a de todo mundo até liberar a imersiva")
checa("o Início só vira imersivo quando há tema_semana (clássico é o padrão)", contem(dash, "tema_semana") and "if (mascote_ativo and tema_semana)" in (dash or ""),
      "sem isso a tela imersiva volta a ser a única")
checa("a Agenda original (Hoje, Semana, Mês) funciona sem aba temática", contem(cal, "'Hoje'", "'Semana'", "'Mês'", "|| null"))
checa("no Início clássico o mascote continua flutuando", contem(base, "not (pagina == 'dashboard' and tema_semana)"))
checa("a imersiva é prêmio e opção: pontos, preferência e rota de escolha", contem(app, "PONTOS_INTERFACE_IMERSIVA", "interface_modo", "def salvar_interface"))
checa("Configurações oferece a escolha entre clássica e imersiva", contem(conf, 'name="interface"', "salvar_interface"))

# ------------------------------------------------------------------ acessórios por mascote
print("\nAcessórios (cada mascote com os seus)")
catalogo = None
try:
    for no in ast.parse(app or "").body:
        if isinstance(no, ast.Assign) and any(getattr(t, "id", "") == "ACESSORIOS_POR_MASCOTE" for t in no.targets):
            catalogo = ast.literal_eval(no.value)
except Exception:
    catalogo = None
css_mascote = ler("static/mascote_robo.css") or ""
checa("o catálogo ACESSORIOS_POR_MASCOTE existe no app.py", bool(catalogo),
      "sem ele a Loja volta a oferecer os mesmos acessórios para todos os mascotes")
if catalogo and js:
    svgs = dict(re.findall(r"const (SVG_[A-Z]+) = `(.*?)`;", js, re.S))
    nomes_svg = {"robo": "SVG_ROBO", "grao": "SVG_GRAO", "boltz": "SVG_BOLTZ", "rabisco": "SVG_RABISCO"}
    m = re.search(r"const FRASES_EXTRA = \{(.*?)\n  \};", js, re.S)
    falas = {}
    if m:
        partes = re.split(r"\n    (\w+): \{", "\n" + m.group(1))
        falas = {partes[i]: partes[i + 1] for i in range(1, len(partes), 2)}
    for skin, itens in catalogo.items():
        svg = svgs.get(nomes_svg.get(skin, ""), "")
        sem_desenho = [a["id"] for a in itens if f"nc-acessorio-{a['id']}" not in svg]
        sem_css = [a["id"] for a in itens if not re.search(r'\[data-acessorio="' + a["id"] + r'"\][^{]*\.nc-acessorio-' + a["id"], css_mascote)]
        sem_fala = [a["id"] for a in itens if f"acessorio_{a['id']}:" not in falas.get(skin, "")]
        ids = ", ".join(a["id"] for a in itens)
        checa(f"{skin} ({ids}): todo item tem desenho no SVG", not sem_desenho, f"sem desenho: {sem_desenho} (grupo .nc-acessorio-<id> em mascote_robo.js)")
        checa(f"{skin}: todo item tem a regra de CSS que o mostra", not sem_css, f"sem regra: {sem_css} (mascote_robo.css)")
        checa(f"{skin}: todo item tem fala própria ao ser equipado", not sem_fala, f"sem fala: {sem_fala} (FRASES_EXTRA em mascote_robo.js)")

# ------------------------------------------------------------------ rotas chamadas pelos templates
print("\nRotas chamadas pelos templates (url_for)")
try:
    funcoes = {n.name for n in ast.walk(ast.parse(app or "")) if isinstance(n, ast.FunctionDef)}
except SyntaxError:
    funcoes = set()
existentes = funcoes | set(re.findall(r"endpoint\s*=\s*[\"'](\w+)[\"']", app or "")) | {"static"}
faltando = {}
for arq in sorted((RAIZ / "templates").rglob("*.html")):
    for nome in re.findall(r"url_for\(\s*['\"]([\w.]+)['\"]", arq.read_text(encoding="utf-8", errors="replace")):
        if nome not in existentes and "." not in nome:
            faltando.setdefault(nome, set()).add(str(arq.relative_to(RAIZ)).replace("\\", "/"))
sem_arquivo = {}
for arq in sorted((RAIZ / "templates").rglob("*.html")):
    for nome in re.findall(r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"{}~]+)['\"]\s*\)", arq.read_text(encoding="utf-8", errors="replace")):
        if not (RAIZ / "static" / nome).exists():
            sem_arquivo.setdefault(nome, set()).add(str(arq.relative_to(RAIZ)).replace("\\", "/"))
checa("todo arquivo de static/ que os templates carregam existe", not sem_arquivo,
      "; ".join(f"static/{n} (usado em {', '.join(sorted(a))})" for n, a in sem_arquivo.items()) + "  -> copie também a pasta static/ do pacote")
existentes_tpl = {str(p.relative_to(RAIZ / "templates")).replace("\\", "/") for p in (RAIZ / "templates").rglob("*") if p.is_file()} if (RAIZ / "templates").exists() else set()
sem_template = {}
for py in sorted(RAIZ.glob("*.py")):
    if py.name.startswith("test_"):
        continue
    for nome in re.findall(r"(?:render_template|get_template)\(\s*['\"]([\w./ -]+)['\"]", py.read_text(encoding="utf-8", errors="replace")):
        if nome not in existentes_tpl:
            sem_template.setdefault(nome, set()).add(py.name)
for arq in sorted((RAIZ / "templates").rglob("*.html")):
    for alvo in re.findall(r"\{%-?\s*(?:extends|include|import|from)\s+['\"]([^'\"]+)['\"]", arq.read_text(encoding="utf-8", errors="replace")):
        if alvo not in existentes_tpl:
            sem_template.setdefault(alvo, set()).add(str(arq.relative_to(RAIZ)).replace("\\", "/"))
checa("todo template citado (render_template, extends, include) existe em templates/", not sem_template,
      "; ".join(f"'{n}' (citado em {', '.join(sorted(a))})" for n, a in sem_template.items()) +
      "  -> restaure o template OU remova a rota/trecho que o cita (senão essa tela dá erro 500)")
checa("todo url_for(...) dos templates aponta para uma rota que existe no app.py", not faltando,
      "; ".join(f"'{n}' (usada em {', '.join(sorted(a))})" for n, a in faltando.items()) +
      "  -> o template é mais novo que o app.py: copie também o app.py do mesmo pacote")

# ------------------------------------------------------------------ segurança
print("\nSegurança")
checa("o seguranca.py existe e o app.py o usa", (RAIZ / "seguranca.py").exists() and contem(app, "import seguranca"), "copie o seguranca.py do pacote para a pasta do projeto")
checa("o login tem limite de tentativas", contem(app, "LIMITE_LOGIN", "LIMITE_LOGIN_IP", "registrar_falha"))
checa("cabeçalhos de segurança e páginas de erro registrados", contem(app, "after_request", "aplicar_cabecalhos", "errorhandler(404)", "errorhandler(500)"))
gitignore = ler(".gitignore")
checa("o .env está no .gitignore", gitignore is not None and re.search(r"(?m)^\s*/?\.env\s*$", gitignore) is not None, "acrescente a linha  .env  ao .gitignore")
try:
    import subprocess
    rastreado = subprocess.run(["git", "ls-files", ".env"], capture_output=True, text=True, cwd=RAIZ)
    if rastreado.returncode == 0:
        checa("o .env NÃO está rastreado pelo Git", rastreado.stdout.strip() == "", "rode:  git rm --cached .env   (tira do Git sem apagar o arquivo da pasta)")
except (OSError, ValueError):
    print("  (git não encontrado: não consegui checar se o .env está rastreado)")
exemplo = ler(".env.example")
checa(".env.example existe", exemplo is not None, "copie o .env.example do pacote (modelo só com os nomes das variáveis)")
if exemplo is not None:
    permitidos = {"DB_PORT", "DB_NAME", "DB_SSLMODE"}
    preenchidos = [m.group(1) for m in re.finditer(r"(?m)^[ \t]*([A-Z][A-Z0-9_]*)[ \t]*=[ \t]*(\S+)", exemplo)
                   if m.group(1) not in permitidos and not m.group(2).startswith("#")]   # só olha a MESMA linha; valor vazio ou comentário não conta
    checa(".env.example NÃO tem valores preenchidos (só os nomes)", not preenchidos, f"apague o valor destas linhas: {preenchidos}")

# ------------------------------------------------------------------ templates
print("\ntemplates (sintaxe Jinja)")
try:
    import jinja2
    env = jinja2.Environment()
    env.filters["markdown"] = lambda x: x
    for arq in sorted((RAIZ / "templates").rglob("*.html")):
        try:
            env.parse(arq.read_text(encoding="utf-8", errors="replace"))
            ok, dica = True, ""
        except jinja2.TemplateSyntaxError as e:
            ok, dica = False, f"linha {e.lineno}: {e.message}"
        checa(str(arq.relative_to(RAIZ)).replace("\\", "/"), ok, dica)
except ImportError:
    print("  (jinja2 não encontrado: ative a .venv do projeto para checar os templates)")

print("\n" + ("Tudo certo: o pacote não desfez nada do que já funcionava." if not problemas
              else f"{problemas} ponto(s) para revisar antes de seguir."))
sys.exit(1 if problemas else 0)
