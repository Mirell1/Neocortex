"""
NEOCORTEX - podar_orfaos.py            (SOMENTE LEITURA: não apaga, não move e não altera nada)

Procura, na pasta do projeto, arquivos que provavelmente não são mais usados e mostra a EVIDÊNCIA de cada achado,
para a pessoa decidir. Rode na pasta do projeto (a mesma do app.py), com a venv ativa:

    python podar_orfaos.py              # relatório
    python podar_orfaos.py --comandos   # relatório + os comandos 'git' sugeridos (impressos, NÃO executados)
    python podar_orfaos.py --historico  # também lista o que só existe no histórico do Git (já removido da pasta)

Como decide:
  - Python: parte do app.py e segue os imports. Arquivos com "if __name__ == '__main__'" são ferramentas avulsas
    (rodam à mão), não órfãos. test_*.py são testes.
  - Templates: parte dos nomes citados em qualquer .py e segue extends/include/import.
  - static/: vale se o nome aparece em template alcançável, em .py, ou em outro css/js (url(), @import, fetch).
    Montagens dinâmicas como 'tema_' ~ tema_ativo ~ '.css' são reconhecidas.
Nenhum valor de senha ou chave é impresso: só arquivo, linha e tipo.
"""
import argparse
import ast
import fnmatch
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(".").resolve()
PASTAS_IGNORADAS = {".git", ".venv", "venv", "env", "node_modules", ".idea", ".vscode", "build", "dist", ".pytest_cache"}
ENTRADAS_PY = {"app", "wsgi", "run", "manage"}
PREFIXOS_FERRAMENTA = ("testar_", "seed_", "verificar_", "podar_", "analise_", "migrar_", "importar_", "exportar_", "gerar_", "conftest", "setup")
SEMPRE_USADOS_STATIC = ("favicon", "apple-touch-icon", "robots.txt", "manifest", "sw.js")
EXT_TEXTO = {".py", ".html", ".css", ".js", ".json", ".txt", ".md", ".sql", ".ini", ".cfg", ".toml", ".yml", ".yaml", ".env", ".example"}

LIXO = [   # (padrão, por quê)
    ("__pycache__/*", "bytecode gerado pelo Python"), ("*.pyc", "bytecode gerado pelo Python"), ("*.pyo", "bytecode gerado pelo Python"),
    ("desktop.ini", "arquivo de pasta do Windows"), ("*/desktop.ini", "arquivo de pasta do Windows"), ("_desktop.ini", "arquivo de pasta do Windows"),
    ("Thumbs.db", "miniaturas do Windows"), (".DS_Store", "arquivo do macOS"), ("*.log", "log de execução"),
    ("*.tmp", "temporário"), ("*.bak", "backup"), ("*~", "backup de editor"), ("*.swp", "temporário de editor"),
    ("analise_saida/*", "saída gerada pelo analise_energia.py (dados derivados de uso: não vai para o repositório)"),
    (".pytest_cache/*", "cache de testes"),
]
PADRAO_COPIA = re.compile(r"^(?P<base>.+?)(?:[ _-]?copy|[ _-]?copia|[ _-]?cópia|\s*\(\d+\)|_\d+|_[0-9a-f]{6,8})(?P<ext>\.\w+)$", re.I)
SEGREDOS = [
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "chave de API do Google/Gemini"),
    (re.compile(r"postgres(?:ql)?://[^\s:@/]+:[^\s@]+@"), "endereço de banco com senha"),
    (re.compile(r"""(?i)\b(password|passwd|senha|secret_key|api_key|apikey|token)\b\s*[:=]\s*['"]([^'"\s]{6,})['"]"""), "valor fixo em campo sensível"),
]
IGNORA_LINHA_SEGREDO = re.compile(r"(?i)os\.getenv|environ|input\(|request\.|form\.|\.get\(|placeholder|exemplo|example|<|\.\.\.|xxx|\*\*\*|seu_|sua_|sua senha|senha123|teste|fake|dummy|hash|bcrypt")


def sh(*args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=RAIZ)
        return r.stdout if r.returncode == 0 else None
    except (OSError, ValueError):
        return None


def norm(p):
    return str(p).replace("\\", "/")


def listar_arquivos():
    """(todos, rastreados): usa o Git se existir; senão percorre as pastas."""
    rastreados = sh("git", "ls-files")
    if rastreados is not None:
        rast = {norm(l) for l in rastreados.splitlines() if l}
        outros = sh("git", "ls-files", "--others", "--exclude-standard") or ""
        todos = rast | {norm(l) for l in outros.splitlines() if l}
        return {t for t in todos if (RAIZ / t).is_file()}, rast
    todos = set()
    for dp, dns, fns in os.walk(RAIZ):
        dns[:] = [d for d in dns if d not in PASTAS_IGNORADAS]
        for f in fns:
            todos.add(norm((Path(dp) / f).relative_to(RAIZ)))
    return todos, set()


def ler(rel):
    p = RAIZ / rel
    try:
        if p.stat().st_size > 1_500_000 or Path(rel).suffix.lower() not in EXT_TEXTO:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def eh_lixo(rel):
    return next((porque for padrao, porque in LIXO if fnmatch.fnmatch(rel, padrao) or fnmatch.fnmatch(Path(rel).name, padrao)), None)


# ----------------------------------------------------------------------------- Python
def analisar_python(todos):
    py = {rel: Path(rel).stem for rel in todos if rel.endswith(".py") and "/" not in rel}
    mods = set(py.values())
    arv = {}
    for rel, mod in py.items():
        try:
            arv[mod] = ast.parse(ler(rel))
        except SyntaxError:
            arv[mod] = None
    importa, strings_no_codigo = {}, defaultdict(set)
    for mod, a in arv.items():
        alvos = set()
        if a is not None:
            for n in ast.walk(a):
                if isinstance(n, ast.Import):
                    alvos |= {x.name.split(".")[0] for x in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    alvos.add(n.module.split(".")[0])
                elif isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in {"import_module", "__import__"} \
                        and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    alvos.add(n.args[0].value.split(".")[0])   # importlib.import_module("x") ou __import__("x")
        importa[mod] = (alvos & mods) - {mod}
    eh_teste = {m for m in mods if m.startswith("test_") or m.endswith("_test")}
    def parece_ferramenta(m):
        texto = ler(f"{m}.py")
        return ("__main__" in texto or "argparse" in texto or m.startswith(PREFIXOS_FERRAMENTA)) and m not in eh_teste and m not in ENTRADAS_PY
    eh_script_bruto = {m for m in mods if arv.get(m) is not None and parece_ferramenta(m)}

    def alcancar(partidas):
        vistos, fila = set(), [m for m in partidas if m in mods]
        while fila:
            m = fila.pop()
            if m in vistos:
                continue
            vistos.add(m)
            fila += [x for x in importa.get(m, ()) if x not in vistos]
        return vistos

    do_app = alcancar(ENTRADAS_PY & mods)
    eh_script = eh_script_bruto - do_app            # se o app importa, é módulo normal (mesmo com bloco __main__)
    dos_testes = alcancar(eh_teste)
    dos_scripts = alcancar(eh_script)
    quem_importa = defaultdict(set)
    for m, alvos in importa.items():
        for x in alvos:
            quem_importa[x].add(m)
    achados = []
    for rel, mod in sorted(py.items()):
        if mod in do_app or mod in eh_teste or mod in eh_script or mod in ENTRADAS_PY:
            continue
        usado_por = sorted(quem_importa.get(mod, ()))
        if mod in dos_testes or mod in dos_scripts:
            achados.append((rel, "MÉDIA", "só é usado por testes ou ferramentas avulsas: " + ", ".join(usado_por)))
        else:
            achados.append((rel, "MÉDIA", "o app não chega nele" + (f" (só é importado por: {', '.join(usado_por)})" if usado_por else " (ninguém o importa)")))
    resumo = {"app": sorted(do_app), "scripts": sorted(eh_script), "testes": sorted(eh_teste)}
    return achados, resumo, arv


# ----------------------------------------------------------------------------- Templates e static
RE_HTML = re.compile(r"""['"]([\w./ -]+\.html)['"]""")
RE_TPL = re.compile(r"""\{%-?\s*(?:extends|include|import|from)\s+['"]([^'"]+)['"]""")
RE_DINAMICO = re.compile(r"""['"]([\w./-]*)['"]\s*~[^~'"]+~\s*['"]([\w.-]*)['"]""")


def analisar_templates(todos):
    tpls = {rel[len("templates/"):] for rel in todos if rel.startswith("templates/") and rel.endswith((".html", ".jinja", ".htm"))}
    citados = set()
    dinamico = False
    for rel in todos:
        if rel.endswith(".py") and "/" not in rel and not Path(rel).stem.startswith("test_"):
            codigo = ler(rel)
            citados |= {m for m in RE_HTML.findall(codigo)}
            if re.search(r"render_template\(\s*[^'\"\s]", codigo):
                dinamico = True
    alcancados, fila = set(), [t for t in tpls if t in citados]
    while fila:
        t = fila.pop()
        if t in alcancados:
            continue
        alcancados.add(t)
        for alvo in RE_TPL.findall(ler(f"templates/{t}")):
            if alvo in tpls and alvo not in alcancados:
                fila.append(alvo)
    quem_estende = defaultdict(set)
    for t in tpls:
        for alvo in RE_TPL.findall(ler(f"templates/{t}")):
            quem_estende[alvo].add(t)
    achados = []
    for t in sorted(tpls - alcancados):
        usado = sorted(quem_estende.get(t, ()))
        achados.append((f"templates/{t}", "ALTA" if not dinamico else "MÉDIA",
                        "nenhum .py o renderiza" + (f"; só é usado por outros templates órfãos: {', '.join(usado)}" if usado else "") +
                        ("  (há render_template com nome dinâmico: confira)" if dinamico else "")))
    return achados, alcancados, tpls


def analisar_static(todos, templates_alcancados):
    estaticos = sorted(rel for rel in todos if rel.startswith("static/") and not eh_lixo(rel))
    corpo, dinamicos = [], []
    for rel in todos:
        if rel.endswith(".py") and "/" not in rel and not Path(rel).stem.startswith("test_"):
            corpo.append((rel, ler(rel)))
        elif rel.startswith("templates/") and rel[len("templates/"):] in templates_alcancados:
            corpo.append((rel, ler(rel)))
        elif rel.startswith("static/") and rel.endswith((".css", ".js")):
            corpo.append((rel, ler(rel)))
    for _, texto in corpo:
        dinamicos += [(a, b) for a, b in RE_DINAMICO.findall(texto) if b.startswith(".") and len(a) >= 2]
    so_em_orfao, achados = {}, []
    todos_templates = {rel: ler(rel) for rel in todos if rel.startswith("templates/")}
    for rel in estaticos:
        nome, sub = Path(rel).name, rel[len("static/"):]
        if any(nome.lower().startswith(s) or nome.lower() == s for s in SEMPRE_USADOS_STATIC):
            continue
        limite = lambda txt: re.compile(r"(?<![\w.-])" + re.escape(txt) + r"(?![\w-])")   # evita 'style.css' dentro de 'style.cssText'
        padrao, padrao_sub = limite(nome), limite(sub)
        achou = any(origem != rel and (padrao_sub.search(texto) or padrao.search(texto)) for origem, texto in corpo)
        if not achou and any(nome.startswith(a) and nome.endswith(b) for a, b in dinamicos):
            achou = True
        if achou:
            continue
        so_orfaos = [t for t, texto in todos_templates.items() if t[len("templates/"):] not in templates_alcancados and (padrao_sub.search(texto) or padrao.search(texto))]
        achados.append((rel, "ALTA" if not so_orfaos else "MÉDIA",
                        "nenhum template, .py, css ou js usa este arquivo" if not so_orfaos else "só é usado por template(s) órfão(s): " + ", ".join(sorted(so_orfaos))))
    return achados


# ----------------------------------------------------------------------------- Cópias, segredos, histórico
def achar_quebradas(todos):
    """O contrário da poda: o código CITA um arquivo que não existe mais (a tela/rota que o usa daria erro)."""
    tpls = {rel[len("templates/"):] for rel in todos if rel.startswith("templates/")}
    achados = defaultdict(set)
    for rel in sorted(todos):
        texto = ler(rel)
        if not texto:
            continue
        if rel.endswith(".py") and "/" not in rel and not Path(rel).name.startswith("test_"):
            for nome in re.findall(r"(?:render_template|get_template)\(\s*['\"]([\w./ -]+)['\"]", texto):
                if nome not in tpls:
                    achados[f"templates/{nome}"].add(rel)
        if rel.startswith("templates/"):
            for alvo in RE_TPL.findall(texto):
                if alvo not in tpls:
                    achados[f"templates/{alvo}"].add(rel)
            for nome in re.findall(r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"{}~]+)['\"]\s*\)", texto):
                if f"static/{nome}" not in todos:
                    achados[f"static/{nome}"].add(rel)
    return [(arq, "ALTA", "citado em " + ", ".join(sorted(onde)) + ", mas o arquivo não existe") for arq, onde in sorted(achados.items())]


def achar_copias(todos):
    nomes = {Path(rel).name: rel for rel in todos}
    achados = []
    for rel in sorted(todos):
        m = PADRAO_COPIA.match(Path(rel).name)
        if m:
            original = m.group("base") + m.group("ext")
            if original in nomes and nomes[original] != rel:
                achados.append((rel, "ALTA", f"parece cópia de {nomes[original]}"))
            elif re.search(r"_[0-9a-f]{6,8}\.\w+$", Path(rel).name) or re.search(r"\(\d+\)", Path(rel).name):
                achados.append((rel, "MÉDIA", "nome de cópia/versão, sem o original ao lado"))
    return achados


def achar_segredos(todos, rastreados):
    achados = []
    for rel in sorted(todos):
        nome = Path(rel).name
        if nome in {"podar_orfaos.py", "verificar_pacote.py"}:
            continue
        if nome == ".env" or (nome.startswith(".env") and not nome.endswith(".example")):
            achados.append((rel, 0, "arquivo de segredos" + (" RASTREADO pelo Git (deveria estar no .gitignore)" if rel in rastreados else " presente (ok se estiver no .gitignore)")))
            continue
        texto = ler(rel)
        if not texto:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            for regex, tipo in SEGREDOS:
                if regex.search(linha) and not (regex is SEGREDOS[2][0] and IGNORA_LINHA_SEGREDO.search(linha)):
                    achados.append((rel, n, tipo))
                    break
    return achados


def so_no_historico(todos):
    saida = sh("git", "log", "--all", "--diff-filter=A", "--name-only", "--format=")
    if saida is None:
        return None
    historico = {norm(l) for l in saida.splitlines() if l.strip()}
    return sorted(historico - todos)


# ----------------------------------------------------------------------------- relatório
def secao(titulo, itens, formato):
    print(f"\n{titulo}  ({len(itens)})")
    print("-" * (len(titulo) + len(str(len(itens))) + 4))
    if not itens:
        print("  nenhum achado")
    for i in itens:
        print("  " + formato(i))


def main():
    ap = argparse.ArgumentParser(description="Procura arquivos órfãos, lixo gerado, cópias e segredos (somente leitura).")
    ap.add_argument("--comandos", action="store_true", help="imprime os comandos git sugeridos (não executa)")
    ap.add_argument("--historico", action="store_true", help="lista arquivos que só existem no histórico do Git")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Não achei o app.py aqui. Rode este script na pasta do projeto (a mesma do app.py).")
        sys.exit(2)

    todos, rastreados = listar_arquivos()
    usa_git = bool(rastreados)
    print(f"Pasta: {RAIZ}\nArquivos analisados: {len(todos)}" + (f" ({len(rastreados)} rastreados pelo Git)" if usa_git else " (sem Git: percorri as pastas)"))

    lixo = [(rel, "ALTA", eh_lixo(rel)) for rel in sorted(todos) if eh_lixo(rel) and (rel in rastreados or not usa_git)]
    py_achados, resumo, _arv = analisar_python(todos)
    tpl_achados, alcancados, _ = analisar_templates(todos)
    st_achados = analisar_static(todos, alcancados)
    copias = achar_copias(todos)
    segredos = achar_segredos(todos, rastreados)

    quebradas = achar_quebradas(todos)
    if quebradas:
        secao("0. ATENÇÃO: o código CITA arquivos que NÃO existem (essas telas/rotas dão erro 500)", quebradas, lambda i: f"[{i[1]}] {i[0]}  - {i[2]}")
    secao("1. LIXO GERADO que não deveria estar no repositório", lixo, lambda i: f"[{i[1]}] {i[0]}  - {i[2]}")
    secao("2. CÓPIAS e versões numeradas", copias, lambda i: f"[{i[1]}] {i[0]}  - {i[2]}")
    secao("3. TEMPLATES órfãos", tpl_achados, lambda i: f"[{i[1]}] {i[0]}  - {i[2]}")
    secao("4. ARQUIVOS DE static/ órfãos", st_achados, lambda i: f"[{i[1]}] {i[0]}  - {i[2]}")
    if _arv.get("app") is None:
        print("\nAVISO: não consegui ler o app.py (erro de sintaxe?). As seções 3, 4 e 5 NÃO são confiáveis até ele rodar.")
    secao("5. MÓDULOS PYTHON que o app não usa", py_achados, lambda i: f"[{i[1]}] {i[0]}  - {i[2]}")
    secao("6. POSSÍVEIS SEGREDOS no código (só arquivo e linha, o valor NÃO é mostrado)", segredos,
          lambda i: f"{i[0]}" + (f":{i[1]}" if i[1] else "") + f"  - {i[2]}")
    print("\nFerramentas avulsas (rodam à mão, não são órfãs):", ", ".join(resumo["scripts"]) or "nenhuma")
    print("Testes:", ", ".join(resumo["testes"]) or "nenhum")

    sql = sorted(r for r in todos if r.endswith(".sql") and "/" not in r)
    docs = sorted(r for r in todos if r.endswith((".md", ".txt")) and "/" not in r and not r.startswith("requirements") and r.lower() != "readme.md")
    if sql or docs:
        print("\nPara organizar (NÃO são órfãos, só estão soltos na raiz):")
        if sql:
            print("  migrações/schema:", ", ".join(sql), " -> considere a pasta sql/")
        if docs:
            print("  documentos:", ", ".join(docs), " -> considere a pasta docs/ (o README fica na raiz)")

    hist = None
    if args.historico:
        hist = so_no_historico(todos)
        secao("7. SÓ NO HISTÓRICO do Git (já não existem na pasta, mas o histórico ainda guarda)", hist or [], lambda i: i)

    if args.comandos:
        print("\n" + "=" * 70 + "\nCOMANDOS SUGERIDOS (nada foi executado; revise antes de rodar)\n" + "=" * 70)
        rast_lixo = [r for r, _, _ in lixo if r in rastreados]
        if rast_lixo:
            print("\n# Lixo gerado: tira do Git SEM apagar da pasta, e passa a ignorar")
            for r in rast_lixo:
                print(f'git rm --cached -- "{r}"')
            print("# acrescente ao .gitignore (se ainda não estiver):  __pycache__/  *.pyc  desktop.ini  analise_saida/  .env")
        altos = [r for r, c, _ in copias + tpl_achados + st_achados if c == "ALTA"]
        if altos:
            print("\n# Confiança ALTA: tira do Git e apaga da pasta (o histórico ainda guarda uma cópia)")
            for r in sorted(set(altos)):
                print(f'git rm -- "{r}"')
        medios = [r for r, c, _ in tpl_achados + st_achados + py_achados if c == "MÉDIA"]
        if medios:
            print("\n# Confiança MÉDIA: confira o motivo acima; se quiser guardar sem poluir, mova para uma pasta _arquivo/")
            for r in sorted(set(medios)):
                print(f'#   git mv -- "{r}" "_arquivo/{Path(r).name}"')
    print("\nFim do relatório. Este script não alterou nenhum arquivo.")


if __name__ == "__main__":
    main()
