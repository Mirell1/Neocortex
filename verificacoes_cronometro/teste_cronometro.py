import sys, os, random
from datetime import datetime, timedelta
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "."); import cronometro as C
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
T0 = datetime(2026, 10, 19, 9, 0, 0); m = lambda n: T0 + timedelta(minutes=n)
ev = lambda *pares: [{"id_evento": i + 1, "tipo_evento": t, "data_hora": m(n)} for i, (t, n) in enumerate(pares)]
print("=== estados básicos ===")
r = C.resumir([], m(5)); checa("sem eventos: parado, zero segundos", r["estado"] == "parado" and r["acumulado_s"] == 0 and r["iniciou_em"] is None)
r = C.resumir(ev(("iniciou", 0)), m(7)); checa("iniciou há 7 min: rodando, 7 min acumulados (inclui o trecho até agora)", r["estado"] == "rodando" and r["acumulado_s"] == 420 and r["iniciou_em"] == m(0) and not r["esquecido"])
r = C.resumir(ev(("iniciou", 0), ("pausou", 10)), m(60)); checa("pausou aos 10 min: pausado, e o tempo PARA de contar mesmo passada 1 hora", r["estado"] == "pausado" and r["acumulado_s"] == 600)
r = C.resumir(ev(("iniciou", 0), ("pausou", 10), ("retomou", 30)), m(35)); checa("retomou aos 30 min: rodando, 10 min antes da pausa + 5 min depois = 15 min (a pausa de 20 min não conta)", r["estado"] == "rodando" and r["acumulado_s"] == 900)
r = C.resumir(ev(("iniciou", 0), ("pausou", 10), ("retomou", 30), ("concluiu", 45)), m(999)); checa("concluiu aos 45 min: ciclo fechado com 25 min líquidos (10 + 15), e não muda com o passar do tempo", r["estado"] == "concluido" and r["acumulado_s"] == 1500 and r["concluiu_em"] == m(45) and r["iniciou_em"] == m(0))
r = C.resumir(ev(("iniciou", 0), ("concluiu", 40)), m(999)); checa("concluir direto, sem pausar: 40 min", r["estado"] == "concluido" and r["acumulado_s"] == 2400)
r = C.resumir(ev(("iniciou", 0), ("pausou", 10), ("concluiu", 50)), m(999)); checa("concluir ENQUANTO está pausado: só vale o que foi executado (10 min); o tempo parado não é inventado", r["estado"] == "concluido" and r["acumulado_s"] == 600)
print("\n=== tarefa que não foi cronometrada ===")
r = C.resumir(ev(("concluiu", 40)), m(99)); checa("concluída sem nunca ter iniciado: continua 'parado' (e portanto não ganha bônus nem entra no aprendizado)", r["estado"] == "parado" and not C.ganha_bonus(r) and not C.serve_para_aprender(r))
r = C.resumir(ev(("pausou", 5), ("retomou", 8)), m(20)); checa("pausar/retomar sem ter iniciado são ignorados", r["estado"] == "parado")
print("\n=== desfazer e cancelar apagam o ciclo ===")
r = C.resumir(ev(("iniciou", 0), ("concluiu", 40), ("desfez_conclusao", 50)), m(60)); checa("desfazer a conclusão: a tarefa volta ao começo (parado, zerada), sem bônus", r["estado"] == "parado" and r["acumulado_s"] == 0 and not C.ganha_bonus(r))
r = C.resumir(ev(("iniciou", 0), ("concluiu", 40), ("desfez_conclusao", 50), ("iniciou", 60)), m(70)); checa("desfez e começou de novo: ciclo NOVO, só os 10 min novos (não soma os 40 antigos)", r["estado"] == "rodando" and r["acumulado_s"] == 600 and r["iniciou_em"] == m(60))
r = C.resumir(ev(("iniciou", 0), ("cancelou", 15)), m(30)); checa("cancelar enquanto roda: tempo zerado e parado", r["estado"] == "parado" and r["acumulado_s"] == 0)
r = C.resumir(ev(("iniciou", 0), ("cancelou", 15), ("iniciou", 100), ("concluiu", 130)), m(200)); checa("cancelou, reativou e cronometrou de novo: vale só o último ciclo (30 min)", r["estado"] == "concluido" and r["acumulado_s"] == 1800)
print("\n=== robustez ===")
r = C.resumir(ev(("iniciou", 0), ("iniciou", 5), ("pausou", 10)), m(30)); checa("'iniciou' repetido (duplo clique) não reinicia nem soma em dobro: 10 min", r["estado"] == "pausado" and r["acumulado_s"] == 600)
r = C.resumir(ev(("iniciou", 0), ("pausou", 10), ("pausou", 12), ("concluiu", 20)), m(30)); checa("'pausou' repetido não desconta duas vezes", r["acumulado_s"] == 600)
r = C.resumir(ev(("iniciou", 0), ("pausou", 10), ("retomou", 20), ("retomou", 25), ("concluiu", 30)), m(40)); checa("'retomou' repetido não conta em dobro: 10 + 10 = 20 min", r["acumulado_s"] == 1200)
emb = ev(("concluiu", 45), ("iniciou", 0), ("retomou", 30), ("pausou", 10)); r = C.resumir(emb, m(60)); checa("eventos FORA de ordem (o banco devolve do mais novo ao mais antigo): são ordenados antes de somar", r["estado"] == "concluido" and r["acumulado_s"] == 1500)
mesmo = [{"id_evento": 2, "tipo_evento": "concluiu", "data_hora": m(10)}, {"id_evento": 1, "tipo_evento": "iniciou", "data_hora": m(10)}]; r = C.resumir(mesmo, m(20)); checa("iniciou e concluiu no MESMO instante: desempata pelo id do evento (iniciou primeiro), zero segundos, sem quebrar", r["estado"] == "concluido" and r["acumulado_s"] == 0)
r = C.resumir([{"tipo_evento": "adiou", "data_hora": m(1)}, {"tipo_evento": "criou", "data_hora": m(2)}, {"tipo_evento": "iniciou", "data_hora": m(3)}], m(8)); checa("eventos de outros tipos (adiou, criou, reagendou) são ignorados", r["estado"] == "rodando" and r["acumulado_s"] == 300)
r = C.resumir([{"tipo_evento": "iniciou", "data_hora": m(0).isoformat()}], m(2)); checa("aceita data/hora em texto ISO (como pode vir de uma exportação)", r["estado"] == "rodando" and r["acumulado_s"] == 120)
r = C.resumir([{"tipo_evento": "iniciou", "data_hora": None}, {"tipo_evento": "iniciou", "data_hora": m(0)}], m(1)); checa("evento sem data é ignorado em vez de quebrar", r["estado"] == "rodando")
r = C.resumir(ev(("iniciou", 100)), m(0)); checa("relógio do app ATRÁS do evento (diferença entre servidores): não dá tempo negativo", r["acumulado_s"] == 0 and r["estado"] == "rodando")
print("\n=== esquecido ligado ===")
r = C.resumir(ev(("iniciou", 0)), m(13 * 60)); checa("ligado há 13 h: continua 'rodando', mas marcado como esquecido", r["estado"] == "rodando" and r["esquecido"])
r = C.resumir(ev(("iniciou", 0)), m(11 * 60)); checa("ligado há 11 h: ainda não é esquecimento", not r["esquecido"])
r = C.resumir(ev(("iniciou", 0), ("pausou", 20), ("retomou", 22 * 60)), m(22 * 60 + 5)); checa("pausou e retomou muito depois: o tempo parado (mais de 21 h) não conta e não marca esquecimento", not r["esquecido"] and r["acumulado_s"] == 20 * 60 + 5 * 60)
r = C.resumir(ev(("iniciou", 0), ("concluiu", 14 * 60)), m(20 * 60)); checa("concluída depois de 14 h: ciclo fechado, mas implausível: NÃO serve para aprender (e ainda ganha o bônus, que é só pelo uso)", r["estado"] == "concluido" and not C.serve_para_aprender(r) and C.ganha_bonus(r))
print("\n=== bônus e aprendizado ===")
for minutos, bonus, aprende in ((0.5, False, False), (2, False, True), (3, True, True), (45, True, True)):
    r = C.resumir(ev(("iniciou", 0), ("concluiu", minutos)), m(999)); checa(f"{minutos} min executados: bônus {'sim' if bonus else 'não'}, serve para aprender {'sim' if aprende else 'não'}", C.ganha_bonus(r) == bonus and C.serve_para_aprender(r) == aprende)
r = C.resumir(ev(("iniciou", 0)), m(60)); checa("cronômetro ainda rodando: sem bônus e sem aprender (só vale ao concluir)", not C.ganha_bonus(r) and not C.serve_para_aprender(r))
checa("rótulos de tempo: 00:00, 05:09, 59:59, 1:00:00, 12:03:07, e negativo vira 00:00", [C.rotulo_tempo(x) for x in (0, 309, 3599, 3600, 43387, -5)] == ["00:00", "05:09", "59:59", "1:00:00", "12:03:07", "00:00"])
print("\n=== propriedade: o resultado não depende da ordem em que os eventos chegam ===")
rng = random.Random(3); ok = True
for _ in range(300):
    n, t, evs = rng.randint(2, 9), 0, []
    for k in range(n):
        t += rng.randint(1, 40); evs.append({"id_evento": k + 1, "tipo_evento": rng.choice(["iniciou", "pausou", "retomou", "concluiu", "adiou", "desfez_conclusao"]), "data_hora": m(t)})
    base = C.resumir(evs, m(t + 5)); emb = evs[:]; rng.shuffle(emb)
    if C.resumir(emb, m(t + 5)) != base or base["acumulado_s"] < 0: ok = False
checa("300 sequências aleatórias de eventos: o resultado é sempre o mesmo em qualquer ordem e nunca é negativo", ok)
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
