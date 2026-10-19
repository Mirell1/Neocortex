import sys, os
from datetime import date, datetime, time, timedelta
ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "."); os.chdir(ARV); sys.path.insert(0, ARV)
import test_ai_fluxo as TA
import test_agenda_servicos as T
import agenda, decisao
banco = T.banco; falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
dia, agora = date(2026, 11, 2), datetime(2026, 10, 19, 10, 0)
def zera(): banco.limpar()
def pad(**kw): banco.padroes = [{"tipo_padrao": k, "valor": v} for k, v in kw.items()]
def met(**kw): banco.metricas = [{"nome_metrica": k, "valor": v} for k, v in kw.items()]
def comp(ini, fim): banco.criar_compromisso(1, "x", datetime.combine(dia, ini), datetime.combine(dia, fim))
hm = lambda s: datetime.fromisoformat(s)
def sug(**kw): return decisao.sugerir_horarios(1, kw.pop("dia", dia), kw.pop("dur", 60), agora, kw.pop("mx", 3), **kw)
print("=== a FOLGA depois usa o tempo realmente medido ===")
zera(); met(excesso_duracao_mediano_min=40.9, atraso_mediano_min=5); r = sug(); s = r["sugestoes"][0]
checa("o cronômetro mediu +41 min de excesso: a folga é de 45 min e diz que foi 'medido pelo cronômetro' (o atraso pequeno do clique é ignorado)", s["folga_min"] == 45 and any("levar ~41 min a mais que o previsto (medido pelo cronômetro)" in b for b in s["base"]) and not any("terminar" in b for b in s["base"]))
zera(); met(excesso_duracao_mediano_min=5, atraso_mediano_min=60); r = sug(); checa("o cronômetro mediu que a pessoa leva só +5 min (no tempo): NÃO há folga, mesmo que o clique em concluir tenha sido tardio (o cronômetro, que é a medida real, vence)", all("folga_min" not in x for x in r["sugestoes"]))
zera(); met(excesso_duracao_mediano_min=-20, atraso_mediano_min=60); r = sug(); checa("quem termina antes do previsto (excesso negativo): sem folga", all("folga_min" not in x for x in r["sugestoes"]))
zera(); met(atraso_mediano_min=40.9); r = sug(); checa("SEM cronômetro, o comportamento é o de antes: folga de 45 min pelo atraso do clique", r["sugestoes"][0]["folga_min"] == 45 and any("terminar ~41 min depois do previsto" in b for b in r["sugestoes"][0]["base"]))
zera(); met(excesso_duracao_mediano_min=30, taxa_adiamento=0.5); r = sug(); checa("o adiamento continua somando: 30 -> 30 min + 15 min extras = 45 min, com as duas razões", r["sugestoes"][0]["folga_min"] == 45 and "levar ~30 min a mais" in r["sugestoes"][0]["base"][-1] and "adiou 50%" in r["sugestoes"][0]["base"][-1])
print("\n=== a MARGEM DE PREPARO antes (quando a pessoa costuma começar depois do horário) ===")
zera(); comp(time(7), time(10)); r0 = sug(); met(atraso_inicio_mediano_min=25); r = sug()
checa("sem a medição, o 1º horário depois do compromisso das 10h é às 10:00; com ela (começa ~25 min atrasada), 30 min livres antes: 10:30", min(hm(x["inicio"]) for x in r0["sugestoes"]).hour == 10 and min(hm(x["inicio"]) for x in r0["sugestoes"]).minute == 0 and min(hm(x["inicio"]) for x in r["sugestoes"]) >= datetime.combine(dia, time(10, 30)))
s = min(r["sugestoes"], key=lambda x: x["inicio"]); checa("cada sugestão informa a margem (preparo_min=30) e o motivo: 'deixei 30 min livres antes (você costuma começar ~25 min depois do horário marcado)'", s["preparo_min"] == 30 and any("deixei 30 min livres antes" in b and "começar ~25 min depois do horário marcado (medido pelo cronômetro)" in b for b in s["base"]))
zera(); met(atraso_inicio_mediano_min=25); r = sug(); checa("no começo do dia (nada antes), a margem não é necessária: o horário das 07:00 continua disponível", any(hm(x["inicio"]).time() == time(7, 0) for x in sug(mx=5)["sugestoes"]) or min(hm(x["inicio"]) for x in sug(mx=5)["sugestoes"]).hour == 7)
zera(); met(atraso_inicio_mediano_min=9); comp(time(7), time(10)); r = sug(); checa("atraso de início pequeno (9 min, abaixo de 10): não reserva margem", all("preparo_min" not in x for x in r["sugestoes"]))
zera(); met(atraso_inicio_mediano_min=500); comp(time(7), time(10)); r = sug(); checa("atraso de início enorme: a margem tem teto de 60 min", max(x.get("preparo_min", 0) for x in r["sugestoes"]) == 60)
zera(); met(atraso_inicio_mediano_min=-15); comp(time(7), time(10)); r = sug(); checa("quem começa ANTES do horário: nenhuma margem", all("preparo_min" not in x for x in r["sugestoes"]))
print("\n=== folga e preparo juntos: as sugestões não se atropelam ===")
zera(); met(excesso_duracao_mediano_min=40.9, atraso_inicio_mediano_min=25); comp(time(7), time(10)); r = sug(mx=3); ss = sorted(r["sugestoes"], key=lambda x: x["inicio"])
checa("cada sugestão tem 30 min livres antes e 45 min de folga depois", all(x["preparo_min"] == 30 and x["folga_min"] == 45 for x in ss))
checa("entre o fim de uma tarefa e o começo da próxima há pelo menos folga + preparo (45 + 30 = 75 min): nenhuma ocupa o espaço da outra", all(hm(b["inicio"]) - hm(a["fim"]) >= timedelta(minutes=75) for a, b in zip(ss, ss[1:])) and len(ss) == 3)
print("\n=== quando a margem não cabe: oferece sem ela e avisa ===")
zera(); met(atraso_inicio_mediano_min=25); comp(time(7), time(10)); comp(time(11), time(22)); r = sug(mx=1); s = r["sugestoes"][0]
checa("janela livre de exatamente 60 min (10h-11h): a margem de 30 min não cabe; oferece 10:00 SEM ela e diz 'não coube a margem de 30 min de preparo'", s["inicio"].endswith("10:00") and "preparo_min" not in s and "não coube a margem de 30 min de preparo que você costuma precisar" in s["base"])
zera(); met(atraso_inicio_mediano_min=25, excesso_duracao_mediano_min=40.9); comp(time(7), time(10)); comp(time(11), time(22)); r = sug(mx=1); s = r["sugestoes"][0]
checa("e se nem a folga cabe: oferece o horário sem nenhuma das duas, avisando das duas", s["inicio"].endswith("10:00") and "preparo_min" not in s and "folga_min" not in s and any("não coube a margem de 30 min" in b for b in s["base"]) and any("não coube a folga de 45 min" in b for b in s["base"]))
zera(); met(atraso_inicio_mediano_min=25, excesso_duracao_mediano_min=40.9); comp(time(7), time(10)); r = sug(usar_folga=False); checa("usar_folga=False desliga a folga E a margem de preparo", all("preparo_min" not in x and "folga_min" not in x for x in r["sugestoes"]))
zera(); met(atraso_inicio_mediano_min=25); comp(time(7), time(22)); r = sug(); checa("dia cheio continua sem sugestões e com a mensagem de sempre", r["sugestoes"] == [] and r["observacao"] == "Não há janela livre desse tamanho nesse dia.")
print("\n=== reservas de outras propostas (reorganizar atrasadas) ===")
zera(); met(atraso_inicio_mediano_min=25); comp(time(7), time(10)); r1 = sug(mx=1); i1 = hm(r1["sugestoes"][0]["inicio"]); res = [(i1 - timedelta(minutes=30), hm(r1["sugestoes"][0]["fim"]))]; r2 = sug(mx=1, reservas=res); i2 = hm(r2["sugestoes"][0]["inicio"])
checa("com o espaço da 1ª proposta reservado (inclusive a margem antes dela), a 2ª não invade nem a tarefa nem a margem", i2 - timedelta(minutes=30) >= hm(r1["sugestoes"][0]["fim"]) or hm(r2["sugestoes"][0]["fim"]) <= i1 - timedelta(minutes=30))
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
