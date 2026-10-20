"""
NEOCORTEX - verificar_responsivo.py

Verifica, SEM banco e SEM navegador, o pacote responsivo (celular e tablet):
  - os templates trazem o menu em gaveta, as classes e os nomes para leitor de tela;
  - a sintaxe dos 5 templates está correta e as <div> da linha de tarefa fecham certo;
  - o static/responsivo.css só muda a aparência abaixo de 900 px: FORA de @media existem só 4 regras neutras
    (esconder o botão ☰ e dois agrupamentos que não geram caixa), que no computador não alteram nada.

Uso (na pasta do projeto): python verificar_responsivo.py
"""
import re
import sys
from pathlib import Path

RAIZ = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
if not (RAIZ / "static/responsivo.css").exists():
    print("FALTA static/responsivo.css: extraia o zip do pacote responsivo na pasta do projeto (a mesma do app.py) e rode de novo.")
    sys.exit(2)
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
ler = lambda rel: (RAIZ / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")

print("=== CSS: o computador não muda ===")
css = re.sub(r"/\*.*?\*/", "", ler("static/responsivo.css"), flags=re.S)
topo, profundidade, ini, atual = [], 0, 0, ""
for k, ch in enumerate(css):
    if ch == "{":
        if profundidade == 0: atual = css[ini:k].strip(); corpo_ini = k + 1
        profundidade += 1
    elif ch == "}":
        profundidade -= 1
        if profundidade == 0: topo.append((atual, css[corpo_ini:k].strip())); ini = k + 1
checa("as chaves do CSS estão balanceadas", profundidade == 0 and len(topo) > 0)
medias = [s for s, _ in topo if s.startswith("@media")]; fora = [(s, " ".join(c.split())) for s, c in topo if not s.startswith("@media")]
NEUTRAS = {".app-menu-btn": "display: none;", ".app-topbar-esq": "display: contents;", ".app-menu-fundo[hidden]": "display: none;", ".t-acoes": "display: contents;"}
checa(f"fora de @media existem só as 4 regras neutras esperadas ({len(fora)} encontradas)", {s for s, _ in fora} == set(NEUTRAS))
checa("cada regra neutra só faz uma coisa: esconder o botão ☰ ou não gerar caixa (display: none / contents)", all(c == NEUTRAS.get(s) for s, c in fora))
checa(f"as {len(medias)} regras de tela pequena só valem abaixo de 900 px (max-width: 900px ou 640px)", medias and all("max-width" in s and ("900px" in s or "640px" in s) for s in medias))
corpo_todo = "\n".join(c for s, c in topo if s.startswith("@media"))
checa("o CSS cobre a gaveta, as janelas, o Login, a linha de Tarefas, o botão + e o mascote", all(x in corpo_todo for x in (".app-sidebar", ".modal-box", ".auth-layout", ".t-linha", ".fab", ".nc-mascote-dock")))
print("\n=== templates ===")
base, login, tar, cal, cfg = (ler(f"templates/{n}") for n in ("base_app_novo.html", "login.html", "tarefas.html", "calendario.html", "configuracoes.html"))
checa("base: menu com id, botão ☰ com nome e aria-expanded/aria-controls, fundo escuro e link do CSS", all(x in base for x in ('id="menuLateral"', 'id="btnMenu"', 'aria-expanded="false"', 'aria-controls="menuLateral"', 'id="menuFundo"', "responsivo.css")))
checa("base: o script fecha com Esc, ao tocar fora e ao escolher uma tela, e devolve o foco", all(x in base for x in ("'Escape'", "fundo.addEventListener('click'", "e.target.closest('a')", "btn.focus()")))
checa("login: classes do layout e link do CSS", all(x in login for x in ('class="auth-layout"', 'class="auth-direita"', "responsivo.css")))
ini_laco = tar.index("{% for t in tarefas %}"); corte = tar[ini_laco:tar.index("{% endfor %}", ini_laco)]
checa("tarefas: linha, título e agrupamento dos botões com as classes certas, e o botão de concluir com nome", all(x in corte for x in ('class="t-linha"', 'class="t-titulo"', 'class="t-acoes"', 'class="t-check"', "aria-label=\"{{ 'Desfazer conclusão de '")))
checa("tarefas: as <div> da linha abrem e fecham na mesma conta (%d abrem, %d fecham)" % (corte.count("<div"), corte.count("</div>")), corte.count("<div") == corte.count("</div>"))
checa("agenda: a barra tem a classe cal-barra", 'class="cal-barra"' in cal)
checa("configurações: as 3 caixas (contraste, dislexia, notificações) têm nome para leitor de tela", all(x in cfg for x in ('aria-label="Alto contraste"', 'aria-label="Fonte para dislexia (Lexend)"', 'aria-label="Receber notificações"')))
try:
    import jinja2
    for n, t in (("base", base), ("login", login), ("tarefas", tar), ("calendario", cal), ("configuracoes", cfg)): jinja2.Environment().parse(t)
    checa("a sintaxe dos 5 templates (Jinja) está correta", True)
except ImportError:
    print("(jinja2 não instalado: pulei a checagem de sintaxe dos templates)")
except Exception as e:
    checa(f"a sintaxe dos 5 templates (Jinja) está correta: {e}", False)
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
