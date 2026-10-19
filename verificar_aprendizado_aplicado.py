"""
NEOCORTEX - verificar_aprendizado_aplicado.py

Verifica, com o banco falso do próprio projeto (sem PostgreSQL e sem Gemini), o que o pacote "aprendizado aplicado" faz:
folga pelo atraso e pelo adiamento, aprendizado e sugestão por categoria, reservas, convite a um hobby no tempo livre e a
ferramenta da IA com categoria. Serve também como documentação executável do comportamento.

Uso (na pasta do projeto; precisa de test_agenda_servicos.py e test_ai_fluxo.py, que já estão no repositório):
    python verificar_aprendizado_aplicado.py
"""
import sys, os
from datetime import date, datetime, time, timedelta
ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")   # sem argumento: a pasta atual (o projeto)
os.chdir(ARV); sys.path.insert(0, ARV)
import test_ai_fluxo as TA                      # instala o SDK do Gemini de mentira e o banco falso do projeto
import test_agenda_servicos as T
import agenda, aprendizado as ap, decisao
ai = sys.modules["ai"]; banco = T.banco
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
dia, agora = date(2026, 11, 2), datetime(2026, 10, 19, 10, 0)
def zera(): banco.limpar(); banco.listar_hobbies_usuario = None
def pad(**kw): banco.padroes = [{"tipo_padrao": k, "valor": v[0], "confianca": v[1]} if isinstance(v, tuple) else {"tipo_padrao": k, "valor": v} for k, v in kw.items()]
def met(**kw): banco.metricas = [{"nome_metrica": k, "valor": v} for k, v in kw.items()]
def comp(ini, fim, d=dia): banco.criar_compromisso(1, "x", datetime.combine(d, ini), datetime.combine(d, fim))
hm = lambda s: datetime.fromisoformat(s)
def sug(**kw): return decisao.sugerir_horarios(1, kw.pop("dia", dia), kw.pop("dur", 60), kw.pop("agora", agora), kw.pop("mx", 3), **kw)
print("=== 1) FOLGA pelo atraso e pelo adiamento ===")
zera(); pad(energia="manha"); met(atraso_mediano_min=40.9); r = sug()
checa("atraso mediano de 40,9 min: cada sugestão reserva 45 min de folga e explica o motivo", len(r["sugestoes"]) == 3 and all(s["folga_min"] == 45 for s in r["sugestoes"]) and all("reservei 45 min de folga depois (você costuma terminar ~41 min depois do previsto)" in s["base"] for s in r["sugestoes"]))
checa("o fim da sugestão continua sendo o fim da TAREFA (60 min), e as sugestões não se atropelam: entre uma e outra há a folga", all((hm(s["fim"]) - hm(s["inicio"])) == timedelta(minutes=60) for s in r["sugestoes"]) and all(hm(b["inicio"]) - hm(a["fim"]) >= timedelta(minutes=45) for a, b in zip(sorted(r["sugestoes"], key=lambda s: s["inicio"]), sorted(r["sugestoes"], key=lambda s: s["inicio"])[1:])))
zera(); met(atraso_mediano_min=40.9, taxa_adiamento=0.5); r = sug()
checa("atraso + adiamento de 50%: 45 + 15 = 60 min, e as duas razões aparecem", r["sugestoes"][0]["folga_min"] == 60 and "você costuma terminar ~41 min depois do previsto e você adiou 50% das tarefas recentes" in r["sugestoes"][0]["base"][-1])
zera(); met(atraso_mediano_min=5, taxa_adiamento=0.45); r = sug(); checa("atraso pequeno (5 min) mas adia 45%: só a folga extra de 15 min", r["sugestoes"][0]["folga_min"] == 15 and "adiou 45%" in r["sugestoes"][0]["base"][-1] and "terminar" not in r["sugestoes"][0]["base"][-1])
zera(); met(atraso_mediano_min=200); r = sug(); checa("atraso enorme (200 min): a folga tem teto de 60 min", r["sugestoes"][0]["folga_min"] == 60)
zera(); met(atraso_mediano_min=-20, taxa_adiamento=0.1); r = sug(); checa("quem termina ANTES do previsto, ou quase não adia: nenhuma folga e nenhuma mudança", all("folga_min" not in s for s in r["sugestoes"]))
zera(); met(atraso_mediano_min=9.9); r = sug(); checa("atraso abaixo de 10 min não aciona folga", all("folga_min" not in s for s in r["sugestoes"]))
zera(); met(atraso_mediano_min=40.9); r = sug(usar_folga=False); checa("usar_folga=False desliga a folga mesmo com atraso aprendido", all("folga_min" not in s for s in r["sugestoes"]))
zera(); met(atraso_mediano_min=40.9); comp(time(7), time(19)); comp(time(20), time(22)); r = sug(mx=1)
s = r["sugestoes"][0]; checa("janela de exatamente 60 min (19h-20h): a folga não cabe, então oferece SEM folga e avisa 'não coube a folga de 45 min'", s["inicio"].endswith("19:00") and "folga_min" not in s and "não coube a folga de 45 min que você costuma precisar" in s["base"])
zera(); met(atraso_mediano_min=40.9); comp(time(7), time(22)); r = sug(); checa("dia cheio: continua sem sugestões e com a mensagem de sempre", r["sugestoes"] == [] and r["observacao"] == "Não há janela livre desse tamanho nesse dia.")
print("\n=== 2) CATEGORIA: o que se aprendeu sobre ela pesa mais que o geral ===")
zera(); pad(energia="tarde", periodo_conclusao_observado=("noite", "media"), **{"periodo_conclusao_observado:estudo": ("manha", "media")}); met(taxa_conclusao_noite=.8, taxa_conclusao_estudo_manha=.9)
geral, estudo, trab = sug(mx=1), sug(mx=1, categoria="estudo"), sug(mx=1, categoria="trabalho")
checa("sem categoria: o melhor horário é à noite (padrão geral)", geral["sugestoes"][0]["periodo"] == "noite" and "categoria" not in geral)
checa("para ESTUDO: o melhor horário é de manhã, e a razão diz 'nas suas tarefas de estudo'", estudo["sugestoes"][0]["periodo"] == "manha" and estudo["categoria"] == "estudo" and any("nas suas tarefas de estudo" in b for b in estudo["sugestoes"][0]["base"]))
checa("a taxa de conclusão usada também é a da categoria ('90% das tarefas de estudo agendadas nesse período')", any("90% das tarefas de estudo agendadas nesse período" in b for b in estudo["sugestoes"][0]["base"]))
checa("categoria SEM aprendizado próprio (trabalho): cai no geral, sem inventar nada", trab["sugestoes"][0]["periodo"] == "noite" and not any("nas suas tarefas de" in b for b in trab["sugestoes"][0]["base"]))
print("\n=== 3) RESERVAS: propostas diferentes não disputam o mesmo horário ===")
checa("_descontar parte a janela no meio e descarta o que está inteiro reservado", decisao._descontar([(datetime(2026, 11, 2, 7), datetime(2026, 11, 2, 22))], [(datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 12))]) == [(datetime(2026, 11, 2, 7), datetime(2026, 11, 2, 10)), (datetime(2026, 11, 2, 12), datetime(2026, 11, 2, 22))] and decisao._descontar([(datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))], [(datetime(2026, 11, 2, 8), datetime(2026, 11, 2, 11))]) == [])
zera(); pad(energia="manha"); r1 = sug(mx=1); res = [(hm(r1["sugestoes"][0]["inicio"]), hm(r1["sugestoes"][0]["fim"]))]; r2 = sug(mx=1, reservas=res)
checa("com o horário da 1ª proposta reservado, a 2ª pede outro (e nunca sobreposto)", r2["sugestoes"][0]["inicio"] != r1["sugestoes"][0]["inicio"] and (hm(r2["sugestoes"][0]["inicio"]) >= res[0][1] or hm(r2["sugestoes"][0]["fim"]) <= res[0][0]))
print("\n=== 4) HOBBY no tempo livre ===")
H = [{"nome": "Leitura"}, {"nome": "Violão"}]; t0 = datetime(2026, 10, 19, 15, 0)
zera(); banco.listar_hobbies_usuario = lambda uid: H; r = decisao.recomendar_tarefa_agora(1, t0)
checa("sem nada urgente e livre o resto do dia: convida para um hobby do perfil (e o texto aparece em 'observacao', que é o que o assistente mostra)", r["sugestao_descanso"]["hobby"] in ("Leitura", "Violão") and "Que tal um dos seus hobbies:" in r["observacao"] and r["observacao"].startswith("Não há tarefas abertas relevantes para agora."))
zera(); banco.listar_hobbies_usuario = lambda uid: H; comp(time(15, 20), time(17), date(2026, 10, 19)); r = decisao.recomendar_tarefa_agora(1, t0); checa("só 20 min livres até o próximo compromisso: não convida", "sugestao_descanso" not in r)
zera(); banco.listar_hobbies_usuario = lambda uid: H; comp(time(15, 50), time(17), date(2026, 10, 19)); r = decisao.recomendar_tarefa_agora(1, t0); checa("50 min livres: convida e diz '50 min livres'", "50 min livres" in r["sugestao_descanso"]["texto"])
zera(); banco.listar_hobbies_usuario = lambda uid: H; comp(time(14, 30), time(16), date(2026, 10, 19)); r = decisao.recomendar_tarefa_agora(1, t0); checa("ocupado agora: não convida", "sugestao_descanso" not in r)
zera(); banco.listar_hobbies_usuario = lambda uid: H; banco.criar_tarefa(1, "Estudar", datetime(2026, 10, 19, 15, 0), datetime(2026, 10, 19, 16, 0), "estudo"); r = decisao.recomendar_tarefa_agora(1, datetime(2026, 10, 19, 15, 10)); checa("há tarefa para agora: recomenda a tarefa, não o hobby", r.get("recomendada") and "sugestao_descanso" not in r)
for h, rot in ((6, "6h da manhã"), (23, "23h")):
    zera(); banco.listar_hobbies_usuario = lambda uid: H; r = decisao.recomendar_tarefa_agora(1, datetime(2026, 10, 19, h, 0)); checa(f"fora do horário do dia ({rot}): não convida", "sugestao_descanso" not in r)
zera(); banco.listar_hobbies_usuario = lambda uid: []; r = decisao.recomendar_tarefa_agora(1, t0); checa("sem hobbies no perfil: a mensagem é exatamente a de antes", r["observacao"] == "Não há tarefas abertas relevantes para agora." and "sugestao_descanso" not in r)
zera(); def_falha = lambda uid: (_ for _ in ()).throw(RuntimeError("banco fora")); banco.listar_hobbies_usuario = def_falha; r = decisao.recomendar_tarefa_agora(1, t0); checa("se buscar os hobbies falhar, a recomendação segue normal (nunca quebra)", r["observacao"] == "Não há tarefas abertas relevantes para agora." and "sugestao_descanso" not in r)
zera(); banco.listar_hobbies_usuario = lambda uid: H; a = decisao.recomendar_tarefa_agora(1, t0)["sugestao_descanso"]["hobby"]; b = decisao.recomendar_tarefa_agora(1, t0 + timedelta(days=1))["sugestao_descanso"]["hobby"]; checa("o hobby sugerido varia de um dia para o outro", a != b)
print("\n=== 5) A IA pode pedir horários de uma categoria ===")
zera(); pad(energia="tarde", periodo_conclusao_observado=("noite", "media"), **{"periodo_conclusao_observado:estudo": ("manha", "media")}); met(taxa_conclusao_noite=.8)
ex = ai._construir_executores(1, agora); r = ex["sugerir_horarios"]("2026-11-02", 60, "estudo"); r0 = ex["sugerir_horarios"]("2026-11-02", 60); rx = ex["sugerir_horarios"]("2026-11-02", 60, "categoria-que-nao-existe")
checa("a ferramenta aceita 'categoria' e usa o aprendizado dela", r["categoria"] == "estudo" and r["sugestoes"][0]["periodo"] == "manha")
checa("sem categoria, ou com uma categoria inválida, o comportamento é o geral (nada quebra)", "categoria" not in r0 and "categoria" not in rx and r0["sugestoes"][0]["periodo"] == "noite")
checa("o contrato de argumentos da ferramenta lista a categoria", ai.CONTRATO_ARGUMENTOS["sugerir_horarios"] == "data, duracao_minutos, categoria")

print("\n=== 6) APRENDIZADO POR CATEGORIA (gravação) ===")
SALVOS, METRICAS = {}, {}
banco.listar_tarefas = lambda uid, **kw: TAREFAS
banco.listar_eventos_usuario = lambda uid, desde=None: []
banco.obter_padrao = lambda uid, tipo: SALVOS.get(tipo)
banco.salvar_padrao_observado = lambda uid, tipo, valor, conf, n: SALVOS.__setitem__(tipo, {"valor": valor, "confianca": conf, "evidencias": n})
banco.substituir_memoria = lambda *a, **k: None
banco.salvar_metrica_unica = lambda uid, nome, valor, ref: METRICAS.__setitem__(nome, valor)
banco.contar_resultados_recomendacoes = lambda uid: {}
ap.resolver_recomendacoes = lambda *a, **k: {}
hoje = datetime(2026, 10, 19, 12, 0); TAREFAS = []; idt = [0]
def tarefa(cat, dias_atras, hora, ok, atraso=15):
    idt[0] += 1; ini = (hoje - timedelta(days=dias_atras)).replace(hour=hora, minute=0, second=0); fim = ini + timedelta(hours=1)
    TAREFAS.append({"id_tarefa": idt[0], "categoria": cat, "status": "concluida" if ok else "pendente", "data_inicio": ini, "data_fim": fim, "concluido_em": fim + timedelta(minutes=atraso) if ok else None})
for d in range(1, 16): tarefa("estudo", d, 9, d != 4)
for d in range(1, 13): tarefa("trabalho", d + 1, 14, True)
for d in range(2, 6): tarefa("estudo", d, 20, False)
for d in range(1, 4): tarefa("hobby", d, 19, True)
tarefa(None, 5, 10, True); tarefa("outro", 6, 11, True)
res = ap.recalcular_aprendizado(1, hoje)
checa("o padrão GERAL fica em branco (manhã e tarde empatam), mas ESTUDO aprende 'manhã' e TRABALHO aprende 'tarde'", "periodo_conclusao_observado" not in SALVOS and SALVOS["periodo_conclusao_observado:estudo"]["valor"] == "manha" and SALVOS["periodo_conclusao_observado:trabalho"]["valor"] == "tarde")
checa("a confiança e as evidências seguem as mesmas regras do geral (12 a 14 eventos, todos num período: confiança média)", SALVOS["periodo_conclusao_observado:estudo"]["confianca"] == "media" and SALVOS["periodo_conclusao_observado:estudo"]["evidencias"] == 14 and SALVOS["periodo_conclusao_observado:trabalho"]["evidencias"] == 12)
checa("hobby, com só 3 tarefas, NÃO vira padrão (evidência mínima), e 'outro' e tarefas sem categoria são ignorados", "periodo_conclusao_observado:hobby" not in SALVOS and not any(k.endswith((":outro", ":None")) for k in SALVOS) and set(res["por_categoria"]) == {"estudo", "trabalho", "hobby"})
checa("as taxas por categoria e período só aparecem com 5 tarefas ou mais: estudo/manhã sim, estudo/noite (4 tarefas) não", abs(METRICAS["taxa_conclusao_estudo_manha"] - 14 / 15) < 0.001 and METRICAS["taxa_conclusao_trabalho_tarde"] == 1.0 and "taxa_conclusao_estudo_noite" not in METRICAS)
antes = {k: dict(v) for k, v in SALVOS.items()}; ap.recalcular_aprendizado(1, hoje); ap.recalcular_aprendizado(1, hoje)
checa("recalcular de novo não muda nada (o padrão é estável e não 'balança')", {k: v["valor"] for k, v in SALVOS.items()} == {k: v["valor"] for k, v in antes.items()})
TAREFAS.clear()
res = ap.recalcular_aprendizado(1, hoje); checa("sem nenhuma tarefa, nada quebra e nada é inventado", res["por_categoria"] == {})
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
