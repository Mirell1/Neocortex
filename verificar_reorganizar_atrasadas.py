"""
NEOCORTEX - verificar_reorganizar_atrasadas.py

Executa o código da rota de prévia de "Reorganizar atrasadas" contra o decisao.py e a agenda.py REAIS do projeto, com o banco
falso do próprio projeto (sem PostgreSQL e sem Gemini), e confere: estudo na manhã e trabalho à tarde (aprendizado por categoria),
propostas que não disputam horário, folga pelo atraso típico, respeito ao prazo do objetivo e dias cheios.

Uso (na pasta do projeto; precisa do test_agenda_servicos.py, que já está no repositório):
    python verificar_reorganizar_atrasadas.py
"""
import sys, os, re
from datetime import date, datetime, time, timedelta
ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")   # sem argumento: a pasta atual (o projeto)
os.chdir(ARV); sys.path.insert(0, ARV)
import test_agenda_servicos as T
import agenda, decisao
banco = T.banco; falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
FIXO = datetime(2026, 10, 19, 10, 0)
class DT(datetime):
    @classmethod
    def now(cls, tz=None): return FIXO
src = open("app.py", encoding="utf-8").read().replace("\r\n", "\n")
bloco = src[src.index("REORG_MAX_TAREFAS = 12"):src.index("def _conflitos_da_reorganizacao")]
class _App:
    def route(self, *a, **k): return lambda f: f
ns = {"db": banco, "decisao": decisao, "datetime": DT, "timedelta": timedelta, "jsonify": lambda **k: k, "usuario_logado": lambda: 1, "login_obrigatorio": lambda f: f, "app": _App()}
exec(bloco, ns)
previa = ns["reorganizar_previa"]
def zera(): banco.limpar()
def pad(**kw): banco.padroes = [{"tipo_padrao": k, "valor": v[0], "confianca": v[1]} if isinstance(v, tuple) else {"tipo_padrao": k, "valor": v} for k, v in kw.items()]
def met(**kw): banco.metricas = [{"nome_metrica": k, "valor": v} for k, v in kw.items()]
def atrasada(titulo, horas_atras, cat, dur=60, prazo=None):
    fim = FIXO - timedelta(hours=horas_atras); i = banco.criar_tarefa(1, titulo, fim - timedelta(minutes=dur), fim, cat)
    if prazo: banco.tarefas[i]["objetivo_prazo"] = prazo
    return i
def ocupa(dia, ini, fim): banco.criar_compromisso(1, "x", datetime.combine(dia, ini), datetime.combine(dia, fim))
hm = lambda s: datetime.fromisoformat(s); hoje = FIXO.date()
print("=== a rota com a DECISÃO REAL (agenda, aprendizado por categoria e folga funcionando juntos) ===")
zera(); pad(energia="noite", **{"periodo_conclusao_observado:estudo": ("manha", "media"), "periodo_conclusao_observado:trabalho": ("tarde", "media")}); met(taxa_conclusao_estudo_manha=.9, taxa_conclusao_trabalho_tarde=.9)
atrasada("Estudar estatística", 5, "estudo"); atrasada("Revisar o relatório", 6, "trabalho"); r = previa(); p = {x["titulo"]: x for x in r["propostas"]}
checa("estudo vai para a MANHÃ e trabalho para a TARDE (o aprendizado por categoria decide, não só o horário livre mais cedo)", hm(p["Estudar estatística"]["inicio"]).hour < 12 and 12 <= hm(p["Revisar o relatório"]["inicio"]).hour < 18)
checa("e a razão mostrada diz que veio do que se aprendeu sobre aquela categoria", "nas suas tarefas de estudo" in " ".join(p["Estudar estatística"]["motivo"]) and "nas suas tarefas de trabalho" in " ".join(p["Revisar o relatório"]["motivo"]))
zera(); pad(periodo_conclusao_observado=("manha", "alta")); met(taxa_conclusao_manha=.9)
for i in range(4): atrasada(f"Tarefa {i + 1}", 3 + i, "estudo")
r = previa(); ini = sorted((hm(x["inicio"]), hm(x["fim"])) for x in r["propostas"])
checa("4 tarefas que preferem a manhã: nenhuma pega o mesmo horário que outra", len(r["propostas"]) == 4 and all(ini[k][1] <= ini[k + 1][0] for k in range(3)))
zera(); pad(periodo_conclusao_observado=("manha", "alta")); met(taxa_conclusao_manha=.9, atraso_mediano_min=40.9)
for i in range(4): atrasada(f"Tarefa {i + 1}", 3 + i, "estudo")
r = previa(); ini = sorted((hm(x["inicio"]), hm(x["fim"])) for x in r["propostas"])
checa("com atraso típico de ~41 min (folga de 45 min), entre uma tarefa e a próxima sobra a folga", len(ini) == 4 and all(ini[k + 1][0] - ini[k][1] >= timedelta(minutes=45) for k in range(3)))
checa("e o motivo de cada uma explica a folga reservada", all(any("reservei 45 min de folga" in b for b in x["motivo"]) for x in r["propostas"]))
zera(); pad(periodo_conclusao_observado=("manha", "alta")); atrasada("Passo com prazo amanhã", 4, "estudo", prazo=FIXO + timedelta(days=1)); atrasada("Tarefa sem objetivo", 5, "estudo"); ocupa(hoje, time(7), time(22)); ocupa(hoje + timedelta(days=1), time(7), time(22))
r = previa(); checa("passo de objetivo com prazo amanhã e os dois dias cheios: fica SEM horário (nunca vai para depois do prazo); a tarefa livre vai para o 1º dia com janela", [s_["titulo"] for s_ in r["sem_horario"]] == ["Passo com prazo amanhã"] and [x["titulo"] for x in r["propostas"]] == ["Tarefa sem objetivo"] and hm(r["propostas"][0]["inicio"]).date() >= hoje + timedelta(days=2))
zera(); pad(periodo_conclusao_observado=("manha", "alta")); atrasada("Só passo com prazo amanhã", 4, "estudo", prazo=FIXO + timedelta(days=1)); ocupa(hoje, time(7), time(22)); ocupa(hoje + timedelta(days=1), time(7), time(22))
r = previa(); checa("se NENHUMA tarefa tem onde ir, a rota devolve 409 com a explicação (e não uma lista vazia)", isinstance(r, tuple) and r[1] == 409 and "Não encontrei horário livre nos próximos 14 dias" in r[0]["erro"])
zera(); pad(energia="manha"); atrasada("Reunião longa", 4, "trabalho", dur=120); ocupa(hoje, time(7), time(20)); ocupa(hoje + timedelta(days=1), time(7), time(22)); r = previa()
checa("dias ocupados: a proposta vai para o primeiro dia com janela do tamanho certo (2 h), sem invadir compromisso", hm(r["propostas"][0]["inicio"]).date() >= hoje + timedelta(days=2) or (hm(r["propostas"][0]["inicio"]).date() == hoje and hm(r["propostas"][0]["inicio"]).hour >= 20 and hm(r["propostas"][0]["fim"]).hour <= 22))
print("\n=== [LOTE-4] NÃO TROCAR UM BOM PERÍODO POR UM RUIM SÓ PARA SER MAIS CEDO ===")
estudo_noite = {"periodo_conclusao_observado:estudo": ("noite", "media")}
zera(); pad(energia="tarde", **estudo_noite); met(taxa_conclusao_estudo_noite=1.0, taxa_conclusao_estudo_tarde=0.22); ocupa(hoje, time(18), time(23))
atrasada("Revisar estatística", 5, "estudo"); atrasada("Ler capítulo", 6, "estudo"); r = previa(); ps = r["propostas"]
checa("estudo conclui 100% à noite e 22% à tarde, e a noite de HOJE está ocupada: as propostas esperam a noite de AMANHÃ (antes iam para a tarde de hoje)", len(ps) == 2 and all(hm(x["inicio"]).date() == hoje + timedelta(days=1) and hm(x["inicio"]).hour >= 18 for x in ps))
checa("e a razão mostrada é a do período bom (observado), nunca um '22%' apresentado como motivo", all("22%" not in " ".join(x["motivo"]) and "observado" in " ".join(x["motivo"]) for x in ps))
zera(); atrasada("Sem nenhum histórico", 5, "estudo"); r = previa()
checa("sem aprendizado nenhum, nada muda: continua o primeiro horário livre (hoje)", hm(r["propostas"][0]["inicio"]).date() == hoje)
zera(); pad(energia="tarde"); atrasada("Só o declarado", 5, "estudo"); r = previa()
checa("só com a energia declarada (tarde) e a tarde livre hoje: fica hoje (amanhã não seria melhor)", hm(r["propostas"][0]["inicio"]).date() == hoje and r["propostas"][0]["motivo"][0] == "período de energia que você declarou")
zera(); pad(energia="tarde", **estudo_noite); met(taxa_conclusao_estudo_noite=1.0, taxa_conclusao_estudo_tarde=0.22)
for d in range(3): ocupa(hoje + timedelta(days=d), time(18), time(23))
atrasada("Noite só volta daqui a 3 dias", 5, "estudo"); r = previa(); x = r["propostas"][0]
checa("o período bom só volta daqui a 3 dias (além do limite de 2 dias de espera): aceita o horário de hoje em vez de empurrar a tarefa para longe", hm(x["inicio"]).date() == hoje and hm(x["inicio"]).hour < 18)
zera(); pad(energia="tarde", **estudo_noite); met(taxa_conclusao_estudo_noite=1.0, taxa_conclusao_estudo_tarde=0.22)
for d in range(2): ocupa(hoje + timedelta(days=d), time(18), time(23))
atrasada("Noite volta em 2 dias", 5, "estudo"); r = previa(); x = r["propostas"][0]
checa("o período bom volta daqui a 2 dias (dentro do limite): espera por ele", hm(x["inicio"]).date() == hoje + timedelta(days=2) and hm(x["inicio"]).hour >= 18)
zera(); met(taxa_conclusao_tarde=0.5, taxa_conclusao_noite=0.7); ocupa(hoje, time(18), time(23)); atrasada("Diferença pequena", 5, "estudo"); r = previa(); x = r["propostas"][0]
checa("a noite de amanhã seria só um pouco melhor (70% x 50%, menos de 0,5 ponto): não vale esperar, fica hoje", hm(x["inicio"]).date() == hoje)
zera(); pad(energia="tarde", **estudo_noite); met(taxa_conclusao_estudo_noite=1.0, taxa_conclusao_estudo_tarde=0.22); atrasada("Passo com prazo", 5, "estudo", prazo=FIXO + timedelta(days=1)); ocupa(hoje, time(18), time(23)); r = previa()
checa("passo de objetivo com prazo amanhã continua respeitando o prazo (a espera pelo período bom nunca passa dele)", all(hm(x["fim"]).date() <= hoje + timedelta(days=1) for x in r["propostas"]))
print("\n=== [LOTE-4] A PONTUAÇÃO SÓ APARECE QUANDO PEDIDA ===")
zera(); pad(energia="tarde", **estudo_noite); met(taxa_conclusao_estudo_noite=1.0, taxa_conclusao_estudo_tarde=0.22)
sem = decisao.sugerir_horarios(1, hoje + timedelta(days=1), 60, FIXO, max_sugestoes=1, categoria="estudo"); com = decisao.sugerir_horarios(1, hoje + timedelta(days=1), 60, FIXO, max_sugestoes=1, categoria="estudo", incluir_pontos=True)
checa("por padrão a saída de sugerir_horarios continua exatamente a de sempre (sem o campo 'pontos')", "pontos" not in sem["sugestoes"][0])
checa("com incluir_pontos=True traz a pontuação (noite de estudo: 2 do observado + 1,0 da taxa = 3,0)", com["sugestoes"][0]["pontos"] == 3.0)
atrasada("Para a prévia", 5, "estudo"); checa("e a prévia da rota NÃO expõe 'pontos' ao navegador (só título, horários e motivo)", all("pontos" not in x for x in previa()["propostas"]))
print("\n=== [LOTE-4] ATRASO LEGÍVEL ===")
th = decisao._tempo_humano
checa("40 min -> '40 min'; 89 min -> '89 min'; 90 min -> '2 h'; 5 h -> '5 h'; 47 h -> '47 h'; 48 h -> '2 dias'; 9940 min -> '7 dias'", [th(40), th(89), th(90), th(300), th(47 * 60), th(48 * 60), th(9940)] == ["40 min", "89 min", "2 h", "5 h", "47 h", "2 dias", "7 dias"])
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
