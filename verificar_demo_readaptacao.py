"""
NEOCORTEX - verificar_demo_readaptacao.py

Garante, SEM banco e SEM Gemini, que a conta criada pelo seed_demo.py MOSTRA o aprendizado e a readaptação em qualquer dia de gravação.
Para 28 dias seguidos a partir de hoje, reproduz o seed (semente real), roda o MESMO recálculo do aprendizado e o MESMO código da
rota "Reorganizar atrasadas", e confere:
  1. o NEOCORTEX aprende que a Ana conclui à noite (ela DECLARA "tarde"), com confiança média ou alta, no geral e no estudo;
  2. a taxa de conclusão do estudo à noite é alta (>= 70%) e a da tarde pelo menos 25 pontos menor;
  3. ao sugerir horário de estudo, ele passa da tarde (só o declarado) para a noite (observado), e a razão diz isso;
  4. o botão "Reorganizar atrasadas" tem de 3 a 12 tarefas e a prévia não apresenta uma taxa baixa como motivo.

Uso (na pasta do projeto, que tem o seed_demo.py e o test_agenda_servicos.py):  python verificar_demo_readaptacao.py
"""
import contextlib
import importlib.util
import io
import os
import random
import re
import sys
from datetime import date, datetime, time, timedelta

ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
os.chdir(ARV); sys.path.insert(0, ARV)
with contextlib.redirect_stdout(io.StringIO()):
    import test_agenda_servicos as T
import aprendizado as ap   # noqa: E402
import decisao             # noqa: E402
banco = T.banco
spec = importlib.util.spec_from_file_location("seed_demo", os.path.join(ARV, "seed_demo.py")); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)

ESTADO = {"agora": datetime.now()}
class DT(datetime):
    @classmethod
    def now(cls, tz=None): return ESTADO["agora"]
src = open("app.py", encoding="utf-8").read().replace("\r\n", "\n")
bloco = src[src.index("REORG_MAX_TAREFAS = 12"):src.index("def _conflitos_da_reorganizacao")]
class _App:
    def route(self, *a, **k): return lambda f: f
ns = {"db": banco, "decisao": decisao, "datetime": DT, "timedelta": timedelta, "jsonify": lambda **k: k, "usuario_logado": lambda: 1, "login_obrigatorio": lambda f: f, "app": _App()}
exec(bloco, ns)

def montar(hoje, agora):
    random.seed(S.SEMENTE); tarefas = []
    for i, (titulo, ini, fim, cat, desloc) in enumerate(S.planejar_tarefas(hoje), 1):
        destino, quando = S.decidir_destino(ini, fim, desloc, agora)
        tarefas.append(dict(id_tarefa=i, id_usuario=1, titulo=titulo, categoria=cat, status=destino, data_inicio=ini, data_fim=fim, concluido_em=quando, criado_em=agora, origem="manual", tempo_execucao_s=None))
    n = len(tarefas)
    for obj in S.OBJETIVOS:
        for k, frag in enumerate(obj["fragmentos"]):
            n += 1; ini = datetime.combine(hoje + timedelta(weeks=k - obj["feitos"], days=1), time(16)); feito = k < obj["feitos"]
            tarefas.append(dict(id_tarefa=n, id_usuario=1, titulo=frag, categoria=None, status="concluida" if feito else "pendente", data_inicio=ini, data_fim=ini + timedelta(minutes=30), concluido_em=ini + timedelta(minutes=35) if feito else None, criado_em=agora, origem="manual", tempo_execucao_s=None))
    return tarefas

def preparar(hoje, agora):
    tarefas = montar(hoje, agora); banco.limpar(); banco.tarefas = {t["id_tarefa"]: t for t in tarefas}
    for dias, desc, ini, fim in S.ROTINA:
        for d in dias: banco.adicionar_rotina(1, d, desc, ini, fim)
    banco.listar_hobbies_usuario = lambda uid: []
    banco.listar_tarefas_aprendizado = lambda uid, desde, ate: [dict(t) for t in tarefas if t["data_fim"] >= desde or (t["status"] == "concluida" and t["concluido_em"] and desde <= t["concluido_em"] <= ate)]
    banco.listar_eventos_usuario = lambda *a, **k: []; banco.obter_padrao = lambda *a: None; banco.contar_resultados_recomendacoes = lambda *a, **k: {}; banco.proxima_expiracao_resultados = lambda *a: None
    cap = []; banco.publicar_aprendizado = lambda *a: cap.append(a); ap.resolver_recomendacoes = lambda *a: {}
    ap.recalcular_aprendizado(1, agora); pad, met = cap[-1][1], cap[-1][2]
    declarado = [{"tipo_padrao": "energia", "valor": S.ENERGIA_DECLARADA, "fonte": "declarado"}]
    aprendido = [{"tipo_padrao": k, "valor": v["valor"], "confianca": v["confianca"], "evidencias": v["n"], "fonte": "observado"} for k, v in pad.items()]
    return pad, met, declarado, aprendido

DATAS = [date.today() + timedelta(days=k) for k in range(28)]; ruins = {k: [] for k in ("geral", "estudo", "taxas", "atrasadas", "vira", "motivo")}; exemplo = None
for hoje in DATAS:
    agora = datetime.combine(hoje, time(11)); ESTADO["agora"] = agora
    pad, met, declarado, aprendido = preparar(hoje, agora)
    banco.padroes = declarado + aprendido; banco.metricas = [{"nome_metrica": k, "valor": v} for k, v in met.items()]
    o, e = pad.get("periodo_conclusao_observado"), pad.get("periodo_conclusao_observado:estudo")
    if not (o and o["valor"] == "noite" and o["confianca"] in ("media", "alta")): ruins["geral"].append(hoje)
    if not (e and e["valor"] == "noite" and e["confianca"] in ("media", "alta")): ruins["estudo"].append(hoje)
    tn, tt = met.get("taxa_conclusao_estudo_noite"), met.get("taxa_conclusao_estudo_tarde")
    if not (tn is not None and tn >= 0.7 and (tt is None or tt <= tn - 0.25)): ruins["taxas"].append(hoje)
    atrasadas = ns["_atrasadas_para_reorganizar"](1, agora)
    if not 3 <= len(atrasadas) <= 12: ruins["atrasadas"].append(hoje)
    viraria = False
    for k in range(1, 8):
        dia = hoje + timedelta(days=k)
        banco.padroes, banco.metricas = declarado, []; antes = decisao.sugerir_horarios(1, datetime.combine(dia, time(0)), 60, agora, max_sugestoes=1, categoria="estudo")["sugestoes"]
        banco.padroes, banco.metricas = declarado + aprendido, [{"nome_metrica": a, "valor": b} for a, b in met.items()]; depois = decisao.sugerir_horarios(1, datetime.combine(dia, time(0)), 60, agora, max_sugestoes=1, categoria="estudo")["sugestoes"]
        if antes and depois and antes[0]["periodo"] == "tarde" and depois[0]["periodo"] == "noite" and "observado" in " ".join(depois[0]["base"]):
            viraria = True; exemplo = exemplo or (dia, antes[0], depois[0]); break
    if not viraria: ruins["vira"].append(hoje)
    r = ns["reorganizar_previa"]()
    props = r["propostas"] if isinstance(r, dict) else []
    baixas = [(p["titulo"], int(m.group(1))) for p in props if p.get("categoria") == "estudo" for m in [re.search(r"concluiu (\d+)%", " ".join(p["motivo"]))] if m and int(m.group(1)) < 50]
    if not props or baixas: ruins["motivo"].append((hoje, baixas[:1]))
def resultado(chave, descricao):
    r = ruins[chave]; checa(f"{descricao}: {len(DATAS) - len(r)} de {len(DATAS)} dias" + (f" (falha em {', '.join(str(x) for x in r[:4])})" if r else ""), not r)
print(f"=== a conta do seed_demo.py nos próximos {len(DATAS)} dias (de {DATAS[0]:%d/%m} a {DATAS[-1]:%d/%m}) ===")
resultado("geral", "1) aprende que a Ana conclui à NOITE (declarou 'tarde'), com confiança média ou alta")
resultado("estudo", "   e o mesmo para as tarefas de ESTUDO (também com confiança média ou alta)")
resultado("taxas", "2) taxa de conclusão do estudo à noite >= 70% e a da tarde pelo menos 25 pontos menor")
resultado("vira", "3) a sugestão de horário de estudo passa da TARDE (só o declarado) para a NOITE, com a razão 'observado'")
resultado("atrasadas", "4) o botão 'Reorganizar atrasadas' tem de 3 a 12 tarefas")
resultado("motivo", "   e a prévia nunca apresenta uma taxa baixa (<50%) como motivo de um horário de estudo")
if exemplo: print(f"\nExemplo ({exemplo[0]:%d/%m}): antes {exemplo[1]['inicio'][11:]} ({'; '.join(exemplo[1]['base'])}) -> depois {exemplo[2]['inicio'][11:]} ({exemplo[2]['base'][0]})")
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
