import sys, os, types
from datetime import datetime, timedelta
from unittest.mock import MagicMock
ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "."); os.chdir(ARV); sys.path.insert(0, ARV)
sys.modules["db"] = MagicMock()
import aprendizado as ap
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
AGORA = datetime(2026, 10, 19, 12, 0); idt = [0]; EV = []
def tarefa(prev_min=60, comeca_depois=10, leva=60, status="concluida", cronometrar=True, dias_atras=3, hora=9, pausa=0):
    """uma tarefa concluída: previsto, quanto atrasou para começar e quanto levou de verdade (com ou sem cronômetro)"""
    idt[0] += 1; ini = (AGORA - timedelta(days=dias_atras)).replace(hour=hora, minute=0, second=0); t = {"id_tarefa": idt[0], "status": status, "data_inicio": ini, "data_fim": ini + timedelta(minutes=prev_min), "concluido_em": ini + timedelta(minutes=prev_min + 5), "categoria": "estudo"}
    if cronometrar:
        c = ini + timedelta(minutes=comeca_depois); ev = [("iniciou", c)]
        if pausa: ev += [("pausou", c + timedelta(minutes=leva / 2)), ("retomou", c + timedelta(minutes=leva / 2 + pausa))]; fim = c + timedelta(minutes=leva + pausa)
        else: fim = c + timedelta(minutes=leva)
        ev.append(("concluiu", fim)); EV.extend({"id_evento": len(EV) + 1, "id_tarefa": t["id_tarefa"], "tipo_evento": a, "data_hora": b} for a, b in ev)
    return t
def zera(): EV.clear(); idt[0] = 0
print("=== o ritmo REAL medido pelo cronômetro ===")
zera(); ts = [tarefa(60, c, l) for c, l in ((10, 70), (20, 90), (15, 60), (25, 80), (5, 50), (30, 100))]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA)
checa("6 tarefas cronometradas: atraso de início mediano = 17,5 min, excesso de duração mediano = +15 min (levou 60 a mais em 3 delas... mediana), e conta as 6", m["tarefas_cronometradas"] == 6 and m["atraso_inicio_mediano_min"] == 17.5 and m["excesso_duracao_mediano_min"] == 15.0)
zera(); ts = [tarefa(60, c, l) for c, l in ((10, 70), (20, 90), (15, 60), (25, 80))]; checa("só 4 tarefas cronometradas: evidência insuficiente, NADA é aprendido (nenhuma métrica)", ap.calcular_metricas_cronometro(ts, EV, AGORA) is None)
zera(); ts = [tarefa(60, 10, 60) for _ in range(5)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("exatamente 5 (o mínimo): já aprende; quem começa e termina no horário dá atraso 10 e excesso 0", m is not None and m["tarefas_cronometradas"] == 5 and m["excesso_duracao_mediano_min"] == 0.0 and m["atraso_inicio_mediano_min"] == 10.0)
zera(); ts = [tarefa(60, 0, 40) for _ in range(5)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("quem termina ANTES do previsto: o excesso é NEGATIVO (-20), e isso é informação válida (a folga depois só liga com excesso positivo)", m["excesso_duracao_mediano_min"] == -20.0)
zera(); ts = [tarefa(60, 15, 60, pausa=45) for _ in range(5)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("pausa de 45 min no meio: o tempo de pausa NÃO entra (levou 60, previsto 60, excesso 0)", m["excesso_duracao_mediano_min"] == 0.0)
print("\n=== o que NÃO conta ===")
zera(); ts = [tarefa(60, 10, 70) for _ in range(5)] + [tarefa(60, status="pendente") for _ in range(4)] + [tarefa(cronometrar=False) for _ in range(6)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA)
checa("tarefas pendentes e as concluídas SEM cronômetro ficam de fora: só as 5 cronometradas entram", m["tarefas_cronometradas"] == 5)
zera(); ts = [tarefa(60, 10, 70) for _ in range(5)] + [tarefa(60, 10, 0.5), tarefa(60, 10, 13 * 60)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("ciclos implausíveis (30 s, ou ligado por 13 h: cronômetro esquecido) ficam de fora", m["tarefas_cronometradas"] == 5)
zera(); ts = [tarefa(60, 10, 70) for _ in range(5)] + [tarefa(60, 20 * 60, 70)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("começou 20 h depois do horário marcado: não é 'atraso para começar'. Entra na duração, mas fica fora do atraso de início", m["tarefas_cronometradas"] == 6 and m["atraso_inicio_mediano_min"] == 10.0)
zera(); ts = [tarefa(60, c, 70) for c in (10, 20 * 60, 21 * 60, 22 * 60, 23 * 60)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("se sobrarem menos de 5 atrasos de início válidos, só o excesso de duração é aprendido (sem inventar o atraso)", m is not None and "excesso_duracao_mediano_min" in m and "atraso_inicio_mediano_min" not in m)
zera(); ts = [tarefa(0, 10, 30) for _ in range(5)] + [tarefa(60, 10, 70) for _ in range(5)]; m = ap.calcular_metricas_cronometro(ts, EV, AGORA); checa("tarefa com duração prevista zero não entra (não há com o que comparar)", m["tarefas_cronometradas"] == 5)
print("\n=== integração: o recálculo grava as métricas e NADA muda para quem não usa o cronômetro ===")
SALVOS, METR = {}, {}
fake = types.SimpleNamespace(); sys.modules["db"].listar_tarefas = lambda uid, **kw: TAREFAS; sys.modules["db"].listar_eventos_usuario = lambda uid, desde=None: EV
sys.modules["db"].obter_padrao = lambda uid, tipo: SALVOS.get(tipo); sys.modules["db"].salvar_padrao_observado = lambda uid, tipo, v, c, n: SALVOS.__setitem__(tipo, {"valor": v})
sys.modules["db"].substituir_memoria = lambda *a, **k: None; sys.modules["db"].salvar_metrica_unica = lambda uid, nome, valor, ref: METR.__setitem__(nome, valor); sys.modules["db"].contar_resultados_recomendacoes = lambda uid: {}
ap.resolver_recomendacoes = lambda *a, **k: {}
zera(); TAREFAS = [tarefa(60, c, l, dias_atras=d + 1) for d, (c, l) in enumerate(((10, 70), (20, 90), (15, 60), (25, 80), (5, 50), (30, 100)))]; ap.recalcular_aprendizado(1, AGORA)
checa("com 6 tarefas cronometradas, o recálculo grava: atraso de início, excesso de duração e quantas tarefas cronometradas", METR.get("atraso_inicio_mediano_min") == 17.5 and METR.get("excesso_duracao_mediano_min") == 15.0 and METR.get("tarefas_cronometradas") == 6)
METR.clear(); zera(); TAREFAS = [tarefa(60, 10, 70, cronometrar=False, dias_atras=d + 1) for d in range(8)]; ap.recalcular_aprendizado(1, AGORA)
checa("para quem NÃO usa o cronômetro: nenhuma métrica do cronômetro é gravada (o resto do aprendizado segue como antes)", not any(k in METR for k in ("atraso_inicio_mediano_min", "excesso_duracao_mediano_min", "tarefas_cronometradas")) and "atraso_mediano_min" in METR)
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
