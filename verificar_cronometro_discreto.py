"""
NEOCORTEX - verificar_cronometro_discreto.py

Verifica, SEM banco e SEM navegador, a lógica do cronômetro discreto que está no app.py: só a PRÓXIMA tarefa ganha a pílula 'Começar',
as outras ficam só com o ícone; com um cronômetro rodando ninguém ganha pílula; desligar em Configurações esconde os botões de começar
sem prender quem já está em andamento. Confere também que as telas e a rota trazem o que precisam.

Uso (na pasta do projeto): python verificar_cronometro_discreto.py
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(RAIZ))
import cronometro  # noqa: E402

falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)

app_src = (RAIZ / "app.py").read_bytes().decode("utf-8").replace("\r\n", "\n")
bloco = app_src[app_src.index("def _cronometro_ativo():"):app_src.index("\n\n\ndef _render_tarefas(")]
PREFS, ESTADOS = {}, {}
class _Db:
    @staticmethod
    def buscar_preferencia(uid, chave):
        if PREFS.get("falha"): raise RuntimeError("banco fora")
        return PREFS.get(chave)
class _Serv:
    hora_do_cronometro = staticmethod(lambda: datetime.now())
    @staticmethod
    def estado_do_cronometro(uid, i, agora=None): return ESTADOS.get(i, {"estado": "parado", "acumulado_s": 0.0, "esquecido": False})
ns = {"db": _Db, "servicos": _Serv, "cronometro": cronometro, "datetime": datetime, "usuario_logado": lambda: 1}
exec(bloco, ns)
anexar = ns["_anexar_cronometro"]
AG = datetime.now()
def t(i, ini, fim, status="pendente"): return {"id_tarefa": i, "status": status, "data_inicio": ini, "data_fim": fim}
def destaques(lista): return [x["id_tarefa"] for x in lista if x["comecar_destaque"]]
def podem(lista): return [x["id_tarefa"] for x in lista if x["pode_comecar"]]
def cenario(): return [t(1, AG - timedelta(days=1), AG - timedelta(days=1) + timedelta(hours=1)), t(2, AG - timedelta(minutes=10), AG + timedelta(minutes=50)), t(3, AG + timedelta(minutes=1), AG + timedelta(hours=2)), t(4, AG + timedelta(minutes=30), AG + timedelta(hours=3))]
print("=== quem recebe a pílula e quem recebe o ícone ===")
PREFS.clear(); ESTADOS.clear(); r = anexar(cenario())
checa("4 tarefas pendentes de hoje: TODAS podem começar, mas só UMA recebe a pílula", podem(r) == [1, 2, 3, 4] and len(destaques(r)) == 1)
checa("a pílula vai para a que está valendo agora (a 2), e não para a atrasada de ontem (a 1)", destaques(r) == [2])
r = anexar([t(1, AG - timedelta(days=1), AG - timedelta(days=1, hours=-1)), t(2, AG - timedelta(hours=5), AG - timedelta(hours=4))]); checa("só tarefas atrasadas: ninguém é 'a próxima' (nenhuma pílula), mas podem começar pelo ícone", destaques(r) == [] and podem(r) == [1, 2])
r = anexar([t(1, AG - timedelta(minutes=20), AG + timedelta(minutes=40), "em_andamento"), t(2, AG + timedelta(minutes=1), AG + timedelta(hours=1))]); checa("sem estado de cronômetro conhecido, só a pendente pode começar", podem(r) == [2])
ESTADOS[1] = {"estado": "rodando", "acumulado_s": 300.0, "esquecido": False}; r = anexar([t(1, AG - timedelta(minutes=20), AG + timedelta(minutes=40), "em_andamento"), t(2, AG + timedelta(minutes=1), AG + timedelta(hours=1))])
checa("com um cronômetro RODANDO ninguém recebe a pílula (a pessoa já está fazendo algo), e o rótulo do tempo vem pronto (05:00)", destaques(r) == [] and r[0]["cronometro"]["rotulo"] == "05:00")
ESTADOS[1] = {"estado": "pausado", "acumulado_s": 300.0, "esquecido": False}; r = anexar([t(1, AG - timedelta(minutes=20), AG + timedelta(minutes=40), "em_andamento"), t(2, AG + timedelta(minutes=1), AG + timedelta(hours=1))]); checa("com o cronômetro PAUSADO, a próxima tarefa volta a receber a pílula", destaques(r) == [2])
ESTADOS.clear(); r = anexar([t(1, AG + timedelta(days=3), AG + timedelta(days=3, hours=1)), t(2, AG - timedelta(minutes=5), AG + timedelta(hours=1))]); checa("tarefa de dias futuros não oferece 'Começar' (evita poluir a tela)", podem(r) == [2])
r = anexar([t(1, AG - timedelta(minutes=5), AG + timedelta(hours=1), "concluida"), t(2, AG - timedelta(minutes=5), AG + timedelta(hours=1), "cancelada")]); checa("concluída e cancelada nunca oferecem 'Começar'", podem(r) == [] and destaques(r) == [])
r = anexar([t(1, AG - timedelta(minutes=5), None)]); checa("defesa: tarefa sem fim (impossível no banco) não derruba nem vira 'a próxima'", destaques(r) == [])
print("\n=== desligar em Configurações ===")
PREFS.clear(); checa("sem preferência salva, o cronômetro está LIGADO", ns["_cronometro_ativo"]() is True)
PREFS["cronometro_ativo"] = "false"; ESTADOS[1] = {"estado": "rodando", "acumulado_s": 60.0, "esquecido": False}; ESTADOS[2] = {"estado": "pausado", "acumulado_s": 60.0, "esquecido": False}
r = anexar([t(1, AG - timedelta(minutes=20), AG + timedelta(minutes=40), "em_andamento"), t(2, AG - timedelta(minutes=15), AG + timedelta(minutes=45), "em_andamento"), t(3, AG + timedelta(minutes=1), AG + timedelta(hours=1))])
checa("desligado: nenhuma tarefa pendente pode começar (nem pílula nem ícone)", podem(r) == [] and destaques(r) == [])
checa("e quem já estava em andamento CONTINUA com o estado do cronômetro (dá para pausar e retomar)", r[0]["cronometro"]["estado"] == "rodando" and r[1]["cronometro"]["estado"] == "pausado")
PREFS.clear(); PREFS["falha"] = True; checa("se ler a preferência falhar, o cronômetro segue LIGADO e nada quebra", ns["_cronometro_ativo"]() is True)
print("\n=== as telas e a rota trazem o que precisam ===")
tarefas_html = (RAIZ / "templates/tarefas.html").read_bytes().decode("utf-8"); config_html = (RAIZ / "templates/configuracoes.html").read_bytes().decode("utf-8")
checa("tarefas.html: pílula só quando t.comecar_destaque, ícone nas outras, ambos com nome para leitor de tela e explicação do que é opcional", "t.comecar_destaque" in tarefas_html and "▶ Começar</button>" in tarefas_html and tarefas_html.count('aria-label="Começar a tarefa {{ t.titulo }} com o cronômetro"') == 2 and "Opcional: cronometre esta tarefa" in tarefas_html)
checa("configuracoes.html: linha 'Cronômetro nas tarefas' com caixa, token CSRF e nome para leitor de tela", "Cronômetro nas tarefas" in config_html and "salvar_cronometro" in config_html and re.search(r'salvar_cronometro.*?csrf_token', config_html, re.S) is not None and 'aria-label="Mostrar o cronômetro nas tarefas"' in config_html)
checa("app.py: a rota /configuracoes/cronometro só aceita POST, exige login e grava a preferência", re.search(r'@app.route\("/configuracoes/cronometro", methods=\["POST"\]\)\s*@login_obrigatorio\s*def salvar_cronometro', app_src) is not None and '"cronometro_ativo", "true" if ativado else "false"' in app_src)
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
