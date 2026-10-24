"""
NEOCORTEX - atualizar_cronometro.py

Acrescenta o CRONÔMETRO OPCIONAL de tarefas e faz o sistema aprender com ele:

  - "▶ Começar" em cada tarefa aberta (opcional), "Pausar" e "▶ Retomar"; o tempo corre no cartão; a tarefa passa a "em andamento".
    Só um cronômetro roda por vez: ao começar outra tarefa, a anterior é pausada e a pessoa é avisada.
  - Ao concluir, um aviso neutro mostra o tempo real e o previsto (sem julgar) e, se houve pelo menos 3 min de execução, +5 pontos
    (os mesmos pontos que liberam acessórios e níveis do mascote). Quem não usa o cronômetro não perde nada.
  - O sistema aprende o ritmo REAL: quando a pessoa COMEÇA em relação ao horário marcado e quanto LEVA a mais ou a menos do que o
    previsto (com pelo menos 5 tarefas cronometradas). Ao sugerir horários, a folga depois da tarefa passa a usar o tempo medido e,
    se a pessoa costuma começar atrasada, o sistema deixa uma margem livre ANTES. Se não couber, oferece sem ela e avisa.
  - "Reorganizar atrasadas" também respeita a margem de preparo.

PRECISA de uma coluna nova no banco: rode neocortex_cronometro_migracao.sql no Supabase (uma vez). O tempo executado fica na tarefa, e não
nos eventos, porque a política de retenção apaga eventos com mais de 75 dias e os pontos não podem diminuir com o tempo. Sem a coluna o
cronômetro funciona e o app não quebra: só o bônus de pontos fica de fora (e um aviso no log diz o que fazer).

DEPENDE dos pacotes "aprendizado aplicado" e "reorganizar atrasadas" (e do arquivo cronometro.py deste zip). Sem eles o script recusa e diz qual falta.
Mexe em db.py, servicos.py, aprendizado.py, decisao.py, app.py e templates/tarefas.html. É TUDO OU NADA. Por padrão só MOSTRA o que mudaria.
Rode na pasta do projeto (a do app.py):

    python atualizar_cronometro.py            # só mostra
    python atualizar_cronometro.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ALVOS = (
    ('decisao.py', '[CRONOMETRO]', (
        ('constantes da margem de preparo',
         r'''DESCANSO_MIN_LIVRE = 30         # só convida para um hobby se houver pelo menos 30 min livres
''',
         r'''DESCANSO_MIN_LIVRE = 30         # só convida para um hobby se houver pelo menos 30 min livres
# [CRONOMETRO] margem de preparo ANTES da tarefa, pelo atraso que a pessoa tem para COMEÇAR (medido pelo cronômetro opcional)
PREPARO_ACIONA_MIN = 10         # só reserva margem se ela costuma começar 10 min ou mais depois do horário marcado
PREPARO_MAX_MIN = 60            # teto: nunca reserva mais que 1 hora
'''),
        ('folga medida, margem de preparo e sugestão de horários',
         r'''def _folga_aprendida(ctx):
    """[APRENDIZADO-APLICADO] Folga (min) a reservar DEPOIS da tarefa, pelo que a pessoa costuma atrasar e adiar.
    Devolve (folga, motivos). Sem evidência suficiente (as métricas só existem com dados), devolve (0, [])."""
    m = ctx["metricas"]
    folga, motivos = 0, []
    atraso = m.get("atraso_mediano_min")
    if atraso is not None and atraso >= FOLGA_ATRASO_ACIONA_MIN:
        folga += -(-int(round(atraso)) // FOLGA_PASSO_MIN) * FOLGA_PASSO_MIN
        motivos.append(f"você costuma terminar ~{atraso:.0f} min depois do previsto")
    adiamento = m.get("taxa_adiamento")
    if adiamento is not None and adiamento >= ADIAMENTO_ALTO:
        folga += FOLGA_EXTRA_ADIAMENTO_MIN
        motivos.append(f"você adiou {adiamento:.0%} das tarefas recentes")
    return min(folga, FOLGA_MAX_MIN), motivos


def _candidatos(livres, duracao, ctx, folga_min):
    """Todos os inícios possíveis (a cada PASSO_MIN) em que a tarefa E a folga cabem na janela livre."""
    total = duracao + timedelta(minutes=folga_min)
    candidatos = []
    for ini, fim in livres:
        t = agenda.arredondar_para_cima(ini)
        while t + total <= fim:
            pontos, base = _pontuar(agenda.periodo_da_hora(t.hour), ctx)
            candidatos.append((pontos, t, base))
            t += timedelta(minutes=agenda.PASSO_MIN)
    return candidatos


def sugerir_horarios(id_usuario, dia, duracao_min=60, agora=None, max_sugestoes=3, categoria=None, reservas=None, usar_folga=True):
    """
    Janelas livres do dia (descontando tarefas, compromissos, rotina,
    restrições e disponibilidade), ordenadas pelo que se SABE do usuário.
    Cada sugestão diz em que se baseia. Sem dados, só ordena por horário.

    [APRENDIZADO-APLICADO]
      categoria  : usa o que se aprendeu SOBRE aquela categoria (ex.: estudo), quando houver.
      reservas   : intervalos (ini, fim) já tomados por outras propostas; não são oferecidos de novo.
      usar_folga : reserva uma folga DEPOIS da tarefa quando o atraso e o adiamento da pessoa pedem
                   (se não couber, oferece sem a folga e avisa).
    """
    agora = agora or datetime.now()
    duracao = timedelta(minutes=duracao_min)
    blocos = agenda.blocos_ocupados(id_usuario, dia)
    apos = agenda.arredondar_para_cima(agora) if dia == agora.date() else None
    livres = agenda.janelas_livres(blocos, dia, apos)
    if reservas:
        livres = _descontar(livres, reservas)

    ctx = _contexto_aprendido(id_usuario, categoria)
    folga, motivos_folga = _folga_aprendida(ctx) if usar_folga else (0, [])
    folga_desejada = folga
    candidatos = _candidatos(livres, duracao, ctx, folga)
    sem_folga = False
    if folga and not candidatos:       # não coube com a folga: oferece sem ela e avisa
        candidatos, folga, sem_folga = _candidatos(livres, duracao, ctx, 0), 0, True

    candidatos.sort(key=lambda c: (-c[0], c[1]))
    folga_td = timedelta(minutes=folga)
    escolhidas = []
    for pontos, t, base in candidatos:
        if all(t >= e["_fim"] or t + duracao + folga_td <= e["_ini"] for e in escolhidas):
            escolhidas.append({"_ini": t, "_fim": t + duracao + folga_td, "_fim_tarefa": t + duracao,
                               "periodo": agenda.periodo_da_hora(t.hour), "base": base})
        if len(escolhidas) == max_sugestoes:
            break

    sugestoes = []
    for e in escolhidas:
        base = list(e["base"]) or (["horário livre"] if (folga or sem_folga) else ["horário livre (ainda sem histórico para personalizar)"])
        item = {"inicio": e["_ini"].isoformat(timespec="minutes"), "fim": e["_fim_tarefa"].isoformat(timespec="minutes"),
                "periodo": e["periodo"], "base": base}
        if folga:
            item["folga_min"] = folga
            base.append(f"reservei {folga} min de folga depois ({' e '.join(motivos_folga)})")
        elif sem_folga:
            base.append(f"não coube a folga de {folga_desejada} min que você costuma precisar")
        sugestoes.append(item)
    saida = {"dia": dia.isoformat(), "duracao_min": duracao_min, "sugestoes": sugestoes}
    if categoria:
        saida["categoria"] = categoria
    if not sugestoes:
        saida["observacao"] = "Não há janela livre desse tamanho nesse dia."
        return saida

    # registra a decisão: se o usuário criar uma tarefa num desses horários, a ligação é feita depois
    db.salvar_decisao(
        id_usuario,
        f"sugestão de horário para {dia.isoformat()} ({duracao_min} min)",
        "janelas livres; padrão observado; energia declarada; taxa de conclusão por período"
        + ("; folga pelo atraso típico" if folga else "") + (f"; aprendizado da categoria {categoria}" if categoria else ""),
        "SUGESTOES:" + ";".join(s["inicio"] for s in sugestoes),
    )
    return saida''',
         r'''def _folga_aprendida(ctx):
    """[APRENDIZADO-APLICADO] Folga (min) a reservar DEPOIS da tarefa, pelo que a pessoa costuma levar a mais e adiar.
    [CRONOMETRO] Com o cronômetro, vale o tempo realmente medido; sem ele, o atraso do clique em concluir.
    Devolve (folga, motivos). Sem evidência suficiente (as métricas só existem com dados), devolve (0, [])."""
    m = ctx["metricas"]
    folga, motivos = 0, []
    medido = m.get("excesso_duracao_mediano_min")
    if medido is not None:
        if medido >= FOLGA_ATRASO_ACIONA_MIN:
            folga += -(-int(round(medido)) // FOLGA_PASSO_MIN) * FOLGA_PASSO_MIN
            motivos.append(f"você costuma levar ~{medido:.0f} min a mais que o previsto (medido pelo cronômetro)")
    else:
        atraso = m.get("atraso_mediano_min")
        if atraso is not None and atraso >= FOLGA_ATRASO_ACIONA_MIN:
            folga += -(-int(round(atraso)) // FOLGA_PASSO_MIN) * FOLGA_PASSO_MIN
            motivos.append(f"você costuma terminar ~{atraso:.0f} min depois do previsto")
    adiamento = m.get("taxa_adiamento")
    if adiamento is not None and adiamento >= ADIAMENTO_ALTO:
        folga += FOLGA_EXTRA_ADIAMENTO_MIN
        motivos.append(f"você adiou {adiamento:.0%} das tarefas recentes")
    return min(folga, FOLGA_MAX_MIN), motivos


def _margem_preparo(ctx):
    """[CRONOMETRO] Minutos livres a deixar ANTES da tarefa, pelo atraso que a pessoa costuma ter para começar. (0, []) sem medição."""
    atraso = ctx["metricas"].get("atraso_inicio_mediano_min")
    if atraso is None or atraso < PREPARO_ACIONA_MIN:
        return 0, []
    margem = min(-(-int(round(atraso)) // FOLGA_PASSO_MIN) * FOLGA_PASSO_MIN, PREPARO_MAX_MIN)
    return margem, [f"você costuma começar ~{atraso:.0f} min depois do horário marcado (medido pelo cronômetro)"]


def _candidatos(livres, duracao, ctx, folga_min, preparo_min=0):
    """Todos os inícios possíveis (a cada PASSO_MIN) em que a tarefa, a folga depois e a margem de preparo antes cabem na janela livre."""
    total = duracao + timedelta(minutes=folga_min)
    preparo = timedelta(minutes=preparo_min)
    candidatos = []
    for ini, fim in livres:
        primeiro = ini if (not preparo_min or ini.time() <= agenda.INICIO_DIA) else ini + preparo   # o começo do dia não precisa de preparo
        t = agenda.arredondar_para_cima(primeiro)
        while t + total <= fim:
            pontos, base = _pontuar(agenda.periodo_da_hora(t.hour), ctx)
            candidatos.append((pontos, t, base))
            t += timedelta(minutes=agenda.PASSO_MIN)
    return candidatos


def sugerir_horarios(id_usuario, dia, duracao_min=60, agora=None, max_sugestoes=3, categoria=None, reservas=None, usar_folga=True):
    """
    Janelas livres do dia (descontando tarefas, compromissos, rotina,
    restrições e disponibilidade), ordenadas pelo que se SABE do usuário.
    Cada sugestão diz em que se baseia. Sem dados, só ordena por horário.

    [APRENDIZADO-APLICADO]
      categoria  : usa o que se aprendeu SOBRE aquela categoria (ex.: estudo), quando houver.
      reservas   : intervalos (ini, fim) já tomados por outras propostas; não são oferecidos de novo.
      usar_folga : reserva uma folga DEPOIS da tarefa quando o atraso e o adiamento da pessoa pedem
                   (se não couber, oferece sem a folga e avisa).
    [CRONOMETRO]
      com o cronômetro opcional, a folga usa o tempo realmente medido e, se a pessoa costuma começar depois do horário,
      deixa também uma margem livre ANTES (também desligada por usar_folga=False; se não couber, oferece sem ela e avisa).
    """
    agora = agora or datetime.now()
    duracao = timedelta(minutes=duracao_min)
    blocos = agenda.blocos_ocupados(id_usuario, dia)
    apos = agenda.arredondar_para_cima(agora) if dia == agora.date() else None
    livres = agenda.janelas_livres(blocos, dia, apos)
    if reservas:
        livres = _descontar(livres, reservas)

    ctx = _contexto_aprendido(id_usuario, categoria)
    folga, motivos_folga = _folga_aprendida(ctx) if usar_folga else (0, [])
    preparo, motivos_preparo = _margem_preparo(ctx) if usar_folga else (0, [])
    folga_desejada, preparo_desejado = folga, preparo
    candidatos = _candidatos(livres, duracao, ctx, folga, preparo)
    sem_folga = sem_preparo = False
    if not candidatos and preparo:      # não coube com a margem de preparo: oferece sem ela (mantém a folga) e avisa
        preparo, sem_preparo = 0, True
        candidatos = _candidatos(livres, duracao, ctx, folga, 0)
    if not candidatos and folga:        # não coube com a folga: oferece sem ela e avisa
        candidatos, folga, sem_folga = _candidatos(livres, duracao, ctx, 0, 0), 0, True

    candidatos.sort(key=lambda c: (-c[0], c[1]))
    folga_td, preparo_td = timedelta(minutes=folga), timedelta(minutes=preparo)
    escolhidas = []
    for pontos, t, base in candidatos:
        if all(t - preparo_td >= e["_fim"] or t + duracao + folga_td <= e["_ini"] for e in escolhidas):
            escolhidas.append({"_ini": t - preparo_td, "_fim": t + duracao + folga_td, "_inicio": t, "_fim_tarefa": t + duracao,
                               "periodo": agenda.periodo_da_hora(t.hour), "base": base})
        if len(escolhidas) == max_sugestoes:
            break

    sugestoes = []
    for e in escolhidas:
        com_extras = bool(folga or sem_folga or preparo or sem_preparo)
        base = list(e["base"]) or (["horário livre"] if com_extras else ["horário livre (ainda sem histórico para personalizar)"])
        item = {"inicio": e["_inicio"].isoformat(timespec="minutes"), "fim": e["_fim_tarefa"].isoformat(timespec="minutes"),
                "periodo": e["periodo"], "base": base}
        if preparo:
            item["preparo_min"] = preparo
            base.append(f"deixei {preparo} min livres antes ({' e '.join(motivos_preparo)})")
        elif sem_preparo:
            base.append(f"não coube a margem de {preparo_desejado} min de preparo que você costuma precisar")
        if folga:
            item["folga_min"] = folga
            base.append(f"reservei {folga} min de folga depois ({' e '.join(motivos_folga)})")
        elif sem_folga:
            base.append(f"não coube a folga de {folga_desejada} min que você costuma precisar")
        sugestoes.append(item)
    saida = {"dia": dia.isoformat(), "duracao_min": duracao_min, "sugestoes": sugestoes}
    if categoria:
        saida["categoria"] = categoria
    if not sugestoes:
        saida["observacao"] = "Não há janela livre desse tamanho nesse dia."
        return saida

    # registra a decisão: se o usuário criar uma tarefa num desses horários, a ligação é feita depois
    db.salvar_decisao(
        id_usuario,
        f"sugestão de horário para {dia.isoformat()} ({duracao_min} min)",
        "janelas livres; padrão observado; energia declarada; taxa de conclusão por período"
        + ("; folga pelo atraso típico" if folga else "") + ("; margem de preparo pelo cronômetro" if preparo else "")
        + (f"; aprendizado da categoria {categoria}" if categoria else ""),
        "SUGESTOES:" + ";".join(s["inicio"] for s in sugestoes),
    )
    return saida'''),
    )),
    ('aprendizado.py', '[CRONOMETRO]', (
        ('importar o cronômetro',
         r'''import db
from periodos import JANELA_LOTE_MIN, PERIODOS, normalizar_periodo, periodo_da_hora
''',
         r'''import cronometro
import db
from periodos import JANELA_LOTE_MIN, PERIODOS, normalizar_periodo, periodo_da_hora
'''),
        ('constantes do ritmo medido',
         r'''CATEGORIAS_APRENDIDAS = ("estudo", "trabalho", "hobby", "pessoal", "saude")   # [POR-CATEGORIA] "outro" não ensina nada
''',
         r'''CATEGORIAS_APRENDIDAS = ("estudo", "trabalho", "hobby", "pessoal", "saude")   # [POR-CATEGORIA] "outro" não ensina nada
MIN_TAREFAS_CRONOMETRADAS = 5       # [CRONOMETRO] abaixo disso, o ritmo medido pelo cronômetro não é confiável
LIMITE_ATRASO_INICIO_H = 12         # começar a mais de 12 h do horário marcado não é "atraso para começar": fica de fora
'''),
        ('cálculo do ritmo medido pelo cronômetro',
         r'''def recalcular_aprendizado(id_usuario, agora=None):''',
         r'''def calcular_metricas_cronometro(tarefas, eventos, agora):
    """
    [CRONOMETRO] O ritmo REAL da pessoa, medido pelo cronômetro opcional (só tarefas concluídas com ele):
      atraso_inicio_mediano_min    quando ela COMEÇA em relação ao horário marcado (positivo = começa depois)
      excesso_duracao_mediano_min  quanto ela LEVA a mais (ou a menos, se negativo) do que o previsto
    Só com MIN_TAREFAS_CRONOMETRADAS ciclos plausíveis. Devolve um dict com as métricas, ou None.
    """
    por_tarefa = {}
    for e in eventos:
        por_tarefa.setdefault(e["id_tarefa"], []).append(e)
    atrasos, excessos = [], []
    for t in tarefas:
        if t["status"] != "concluida":
            continue
        resumo = cronometro.resumir(por_tarefa.get(t["id_tarefa"], []), agora)
        if not cronometro.serve_para_aprender(resumo):
            continue
        previsto_min = (t["data_fim"] - t["data_inicio"]).total_seconds() / 60
        if previsto_min <= 0:
            continue
        atraso_inicio = (resumo["iniciou_em"] - t["data_inicio"]).total_seconds() / 60
        if abs(atraso_inicio) <= LIMITE_ATRASO_INICIO_H * 60:
            atrasos.append(atraso_inicio)
        excessos.append(resumo["acumulado_s"] / 60 - previsto_min)
    if len(excessos) < MIN_TAREFAS_CRONOMETRADAS:
        return None
    saida = {"excesso_duracao_mediano_min": round(statistics.median(excessos), 1), "tarefas_cronometradas": len(excessos)}
    if len(atrasos) >= MIN_TAREFAS_CRONOMETRADAS:
        saida["atraso_inicio_mediano_min"] = round(statistics.median(atrasos), 1)
    return saida


def recalcular_aprendizado(id_usuario, agora=None):'''),
        ('gravar as métricas do cronômetro',
         r'''    metricas.update(metricas_categoria)   # [POR-CATEGORIA]
''',
         r'''    cronometrado = calcular_metricas_cronometro(tarefas, eventos, agora)   # [CRONOMETRO]
    if cronometrado:
        metricas.update(cronometrado)
    metricas.update(metricas_categoria)   # [POR-CATEGORIA]
'''),
    )),
    ('db.py', '[CRONOMETRO]', (
        ('eventos, hora e tempo do cronômetro',
         r'''def listar_eventos_execucao(id_tarefa, id_usuario):''',
         r'''# ============================================================
# CRONÔMETRO OPCIONAL  [CRONOMETRO]
# O estado do cronômetro sai dos eventos (iniciou, pausou, retomou, concluiu): ver cronometro.py.
# ============================================================
def registrar_evento_cronometro(id_tarefa, id_usuario, tipo_evento, novo_status=None):
    """
    Grava um evento do cronômetro NA MESMA transação da mudança de status (pendente -> em_andamento ao começar).
    Devolve True, ou None se a tarefa não existe, é de outra pessoa ou não está aberta.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status FROM tarefas
                WHERE id_tarefa = %s AND id_usuario = %s
                FOR UPDATE
                """,
                (id_tarefa, id_usuario),
            )
            linha = cur.fetchone()
            if linha is None or linha["status"] not in ("pendente", "em_andamento"):
                return None
            if novo_status and linha["status"] != novo_status:
                cur.execute(
                    "UPDATE tarefas SET status = %s WHERE id_tarefa = %s AND id_usuario = %s",
                    (novo_status, id_tarefa, id_usuario),
                )
            _registrar_evento(cur, id_tarefa, tipo_evento)
    return True


def agora_do_banco():
    """Hora do banco (a mesma dos eventos): o cronômetro compara com ela, e não com o relógio do servidor do app."""
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT LOCALTIMESTAMP AS agora")
            return cur.fetchone()["agora"]


_AVISOU_MIGRACAO_CRONOMETRO = False


def _avisar_migracao_cronometro(erro):
    global _AVISOU_MIGRACAO_CRONOMETRO
    if not _AVISOU_MIGRACAO_CRONOMETRO:
        _AVISOU_MIGRACAO_CRONOMETRO = True
        import logging
        logging.getLogger("neocortex.db").warning(
            "Não consegui usar tarefas.tempo_execucao_s (%s). Rode neocortex_cronometro_migracao.sql. "
            "Enquanto isso o cronômetro funciona, mas o bônus de pontos fica de fora.", erro)


def salvar_tempo_execucao(id_tarefa, id_usuario, segundos):
    """
    Guarda (ou limpa, com None) o tempo executado com o cronômetro. É a base do bônus de pontos: fica na tarefa, e não nos
    eventos, porque os eventos antigos são apagados pela política de retenção e os pontos não podem diminuir com o tempo.
    """
    try:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tarefas SET tempo_execucao_s = %s WHERE id_tarefa = %s AND id_usuario = %s",
                    (None if segundos is None else int(segundos), id_tarefa, id_usuario),
                )
                return cur.rowcount
    except Exception as erro:
        _avisar_migracao_cronometro(erro)
        return 0


def listar_eventos_execucao(id_tarefa, id_usuario):'''),
        ('pontos extras por tarefa cronometrada',
         r'''def calcular_pontos_mascote(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM tarefas WHERE id_usuario = %s AND status = 'concluida'",
                (id_usuario,),
            )
            tarefas = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM objetivos WHERE id_usuario = %s AND status = 'concluido'",
                (id_usuario,),
            )
            objetivos = cur.fetchone()["n"]
    return tarefas * 10 + objetivos * 50''',
         r'''def _contar_tarefas_cronometradas(id_usuario):
    """Tarefas concluídas com o cronômetro (o tempo executado é guardado na conclusão). Sem a coluna, devolve 0 e avisa uma vez."""
    import cronometro
    try:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM tarefas WHERE id_usuario = %s AND status = 'concluida' AND tempo_execucao_s >= %s",
                    (id_usuario, cronometro.MIN_SEGUNDOS_BONUS),
                )
                return cur.fetchone()["n"]
    except Exception as erro:
        _avisar_migracao_cronometro(erro)
        return 0


def calcular_pontos_mascote(id_usuario):
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM tarefas WHERE id_usuario = %s AND status = 'concluida'",
                (id_usuario,),
            )
            tarefas = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM objetivos WHERE id_usuario = %s AND status = 'concluido'",
                (id_usuario,),
            )
            objetivos = cur.fetchone()["n"]
    import cronometro   # [CRONOMETRO] incentivo opcional: pontos a mais por tarefa concluída com o cronômetro
    return tarefas * 10 + objetivos * 50 + _contar_tarefas_cronometradas(id_usuario) * cronometro.PONTOS_POR_TAREFA_CRONOMETRADA'''),
    )),
    ('servicos.py', '[CRONOMETRO]', (
        ('importar o cronômetro',
         r'''import decisao

log = logging.getLogger("neocortex.servicos")
''',
         r'''import cronometro
import decisao

log = logging.getLogger("neocortex.servicos")
'''),
        ('começar, pausar, retomar e concluir com o tempo real',
         r'''def concluir_tarefa(id_usuario, id_tarefa):
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] == "cancelada":
        return {"sucesso": False, "erro": "Essa tarefa está cancelada."}
    db.marcar_tarefa_concluida(tarefa["id_tarefa"], id_usuario)   # duplo clique não duplica evento
    _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}


def desfazer_conclusao(id_usuario, id_tarefa):
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] != "concluida":
        return {"sucesso": False, "erro": "Essa tarefa não está concluída."}
    db.desfazer_conclusao_tarefa(tarefa["id_tarefa"], id_usuario)
    _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}''',
         r'''def hora_do_cronometro():
    """[CRONOMETRO] Hora do banco (a dos eventos); se não der para obtê-la, a do servidor do app."""
    try:
        return db.agora_do_banco()
    except Exception:
        return datetime.now()


def estado_do_cronometro(id_usuario, id_tarefa, agora=None):
    """Estado do cronômetro opcional de uma tarefa (ver cronometro.resumir)."""
    return cronometro.resumir(db.listar_eventos_execucao(id_tarefa, id_usuario), agora or hora_do_cronometro())


def _fechar_cronometro(id_usuario, tarefa):
    """
    Se a tarefa foi cronometrada, guarda o tempo executado (base do bônus de pontos) e devolve o resumo para a tela.
    Nunca derruba a conclusão: qualquer falha aqui só é registrada.
    """
    try:
        resumo = estado_do_cronometro(id_usuario, tarefa["id_tarefa"])
        if resumo["estado"] != "concluido":
            return None
        bonus = cronometro.ganha_bonus(resumo)
        db.salvar_tempo_execucao(tarefa["id_tarefa"], id_usuario, resumo["acumulado_s"] if bonus else None)
        previsto = max(0, int((tarefa["data_fim"] - tarefa["data_inicio"]).total_seconds() // 60))
        return {"real_s": int(resumo["acumulado_s"]), "previsto_min": previsto, "bonus": bonus,
                "pontos": cronometro.PONTOS_POR_TAREFA_CRONOMETRADA if bonus else 0}
    except Exception:
        log.exception("Falha ao fechar o cronômetro da tarefa %s", tarefa.get("id_tarefa"))
        return None


def concluir_tarefa(id_usuario, id_tarefa):
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] == "cancelada":
        return {"sucesso": False, "erro": "Essa tarefa está cancelada."}
    db.marcar_tarefa_concluida(tarefa["id_tarefa"], id_usuario)   # duplo clique não duplica evento
    resultado = {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}
    cron = _fechar_cronometro(id_usuario, tarefa)
    if cron:
        resultado["cronometro"] = cron
    _atualizar_aprendizado(id_usuario)
    return resultado


def desfazer_conclusao(id_usuario, id_tarefa):
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] != "concluida":
        return {"sucesso": False, "erro": "Essa tarefa não está concluída."}
    db.desfazer_conclusao_tarefa(tarefa["id_tarefa"], id_usuario)
    try:
        db.salvar_tempo_execucao(tarefa["id_tarefa"], id_usuario, None)   # [CRONOMETRO] sem conclusão, sem tempo guardado
    except Exception:
        log.exception("Falha ao limpar o tempo cronometrado da tarefa %s", tarefa["id_tarefa"])
    _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}


def _pausar_outras_em_andamento(id_usuario, exceto_id):
    """Só há UM cronômetro rodando por pessoa: ao começar outra tarefa, a que estava rodando é pausada (e a pessoa é avisada)."""
    pausadas = []
    agora = hora_do_cronometro()
    for t in db.listar_tarefas_abertas(id_usuario):
        if t["id_tarefa"] == exceto_id or t["status"] != "em_andamento":
            continue
        if estado_do_cronometro(id_usuario, t["id_tarefa"], agora)["estado"] == "rodando":
            if db.registrar_evento_cronometro(t["id_tarefa"], id_usuario, "pausou"):
                pausadas.append(t["titulo"])
    return pausadas


def _transicao_do_cronometro(id_usuario, id_tarefa, acao):
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] == "concluida":
        return {"sucesso": False, "erro": "Essa tarefa já está concluída."}
    if tarefa["status"] == "cancelada":
        return {"sucesso": False, "erro": "Essa tarefa está cancelada."}
    estado = estado_do_cronometro(id_usuario, tarefa["id_tarefa"])["estado"]
    if acao == "iniciar":
        if estado == "rodando":
            return {"sucesso": False, "erro": "O cronômetro dessa tarefa já está rodando."}
        tipo = "retomou" if estado == "pausado" else "iniciou"          # começar uma tarefa pausada é retomá-la
    elif acao == "pausar":
        if estado != "rodando":
            return {"sucesso": False, "erro": "O cronômetro dessa tarefa não está rodando."}
        tipo = "pausou"
    else:
        if estado != "pausado":
            return {"sucesso": False, "erro": "Essa tarefa não está pausada."}
        tipo = "retomou"
    pausadas = [] if tipo == "pausou" else _pausar_outras_em_andamento(id_usuario, tarefa["id_tarefa"])
    if not db.registrar_evento_cronometro(tarefa["id_tarefa"], id_usuario, tipo, None if tipo == "pausou" else "em_andamento"):
        return {"sucesso": False, "erro": "Não foi possível mexer no cronômetro dessa tarefa."}
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"], "evento": tipo, "pausadas": pausadas}


def iniciar_tarefa(id_usuario, id_tarefa):
    """[CRONOMETRO] Opcional: começa (ou retoma) o cronômetro da tarefa. A tarefa passa a 'em andamento'."""
    return _transicao_do_cronometro(id_usuario, id_tarefa, "iniciar")


def pausar_tarefa(id_usuario, id_tarefa):
    return _transicao_do_cronometro(id_usuario, id_tarefa, "pausar")


def retomar_tarefa(id_usuario, id_tarefa):
    return _transicao_do_cronometro(id_usuario, id_tarefa, "retomar")'''),
    )),
    ('app.py', '[CRONOMETRO]', (
        ('importar o cronômetro',
         r'''import servicos
import decisao
import seguranca
''',
         r'''import servicos
import cronometro
import decisao
import seguranca
'''),
        ('estado do cronômetro na tela de Tarefas',
         r'''def _render_tarefas(filtro="hoje", categoria_filtro="todas", **extra):''',
         r'''def _anexar_cronometro(tarefas):
    """[CRONOMETRO] Acrescenta a cada tarefa o estado do cronômetro opcional (só quem está em andamento precisa de consulta)
    e se vale oferecer 'Começar'. Nunca derruba a tela de Tarefas."""
    hoje = datetime.now().date()
    agora = None
    for t in tarefas:
        t["cronometro"] = None
        t["pode_comecar"] = t["status"] == "pendente" and t["data_inicio"].date() <= hoje
        if t["status"] == "em_andamento":
            try:
                agora = agora or servicos.hora_do_cronometro()
                estado = servicos.estado_do_cronometro(usuario_logado(), t["id_tarefa"], agora)
                t["cronometro"] = {**estado, "rotulo": cronometro.rotulo_tempo(estado["acumulado_s"])}
            except Exception:
                t["cronometro"] = None
    return tarefas


def _render_tarefas(filtro="hoje", categoria_filtro="todas", **extra):'''),
        ('tela de Tarefas recebe o estado e o aviso',
         r'''        tarefas=tarefas_filtradas(usuario_logado(), filtro, categoria_filtro),
''',
         r'''        tarefas=_anexar_cronometro(tarefas_filtradas(usuario_logado(), filtro, categoria_filtro)),
        aviso_cronometro=session.pop("cronometro_aviso", None),   # [CRONOMETRO]
'''),
        ('aviso do tempo real ao concluir',
         r'''    # [MASCOTE] se era a última de hoje, a comemoração é de "dia concluído"
''',
         r'''    cron = resultado.get("cronometro")      # [CRONOMETRO] mostra o tempo real e o incentivo, sem julgar
    if cron and not resultado.get("erro"):
        session["cronometro_aviso"] = {"titulo": resultado.get("titulo"), "real_min": max(1, round(cron["real_s"] / 60)),
                                       "previsto_min": cron["previsto_min"], "pontos": cron["pontos"] if GAMIFICACAO_ATIVA else 0}

    # [MASCOTE] se era a última de hoje, a comemoração é de "dia concluído"
'''),
        ('rota do cronômetro',
         r'''@app.route("/tarefas/<int:id_tarefa>/desfazer", methods=["POST"])''',
         r'''@app.route("/tarefas/<int:id_tarefa>/cronometro/<acao>", methods=["POST"])
@login_obrigatorio
def cronometro_tarefa(id_tarefa, acao):
    """[CRONOMETRO] Opcional: começar, pausar ou retomar o cronômetro de uma tarefa."""
    funcao = {"iniciar": "iniciar_tarefa", "pausar": "pausar_tarefa", "retomar": "retomar_tarefa"}.get(acao)
    if funcao is None:
        abort(404)
    resultado = getattr(servicos, funcao)(usuario_logado(), id_tarefa)
    if resultado.get("nao_encontrada"):
        abort(404)
    if resultado.get("erro"):
        session["cronometro_aviso"] = {"erro": resultado["erro"]}
    elif resultado.get("pausadas"):
        session["cronometro_aviso"] = {"info": "Pausei " + ", ".join(resultado["pausadas"]) + " para você começar esta."}
    return redirect(request.referrer or url_for("tarefas"))


@app.route("/tarefas/<int:id_tarefa>/desfazer", methods=["POST"])'''),
        ('reorganizar respeita a margem de preparo',
         r'''        reservas.append((inicio, fim + timedelta(minutes=achou.get("folga_min", 0))))     # a próxima proposta não disputa este horário
''',
         r'''        reservas.append((inicio - timedelta(minutes=achou.get("preparo_min", 0)), fim + timedelta(minutes=achou.get("folga_min", 0))))     # a próxima proposta não disputa este horário
'''),
    )),
    ('templates/tarefas.html', '[CRONOMETRO]', (
        ('botões do cronômetro em cada tarefa',
         r'''      <span class="badge" style="background:{{ cor }}18;color:{{ cor }};">{{ label }}</span>
''',
         r'''      {# [CRONOMETRO] opcional: começar, pausar e retomar. Quem usa ajuda o NEOCORTEX a aprender o seu ritmo{{ " e ganha pontos" if mascote_ativo else "" }}. #}
      {% if t.cronometro and t.cronometro.estado == 'rodando' %}
      <span class="nc-cron" data-base="{{ t.cronometro.acumulado_s|int }}" style="font-variant-numeric:tabular-nums;font-size:13px;font-weight:700;color:#F59E0B;white-space:nowrap;" title="{{ 'Está rodando há muito tempo: esqueceu de pausar?' if t.cronometro.esquecido else 'Cronômetro rodando' }}">⏱ <span class="nc-cron-t">{{ t.cronometro.rotulo }}</span></span>
      <form method="POST" action="{{ url_for('cronometro_tarefa', id_tarefa=t.id_tarefa, acao='pausar') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" title="Pausar o cronômetro"
          style="height:28px;padding:0 10px;border-radius:14px;border:1.5px solid var(--nc-border);background:transparent;color:var(--nc-text);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;">Pausar</button>
      </form>
      {% elif t.cronometro and t.cronometro.estado == 'pausado' %}
      <span style="font-variant-numeric:tabular-nums;font-size:13px;font-weight:700;color:var(--nc-text2);white-space:nowrap;">pausado {{ t.cronometro.rotulo }}</span>
      <form method="POST" action="{{ url_for('cronometro_tarefa', id_tarefa=t.id_tarefa, acao='retomar') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" title="Retomar o cronômetro"
          style="height:28px;padding:0 10px;border-radius:14px;border:1.5px solid var(--nc-border);background:transparent;color:var(--nc-text);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;">▶ Retomar</button>
      </form>
      {% elif t.pode_comecar %}
      <form method="POST" action="{{ url_for('cronometro_tarefa', id_tarefa=t.id_tarefa, acao='iniciar') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" title="Opcional: cronometre esta tarefa. Ajuda o NEOCORTEX a aprender o seu ritmo{{ ' e dá +5 pontos' if mascote_ativo else '' }}."
          style="height:28px;padding:0 10px;border-radius:14px;border:1.5px solid var(--nc-border);background:transparent;color:var(--nc-text);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;">▶ Começar</button>
      </form>
      {% endif %}

      <span class="badge" style="background:{{ cor }}18;color:{{ cor }};">{{ label }}</span>
'''),
        ('aviso do tempo real e dos pontos',
         r'''  {% if n_atrasadas %}
  <div style="margin:-4px 0 16px;">   {# [REORGANIZAR] #}
''',
         r'''  {% if aviso_cronometro %}
  <div role="status" style="margin:0 0 16px;padding:12px 16px;border-radius:12px;border:1.5px solid var(--nc-border);font-size:13px;font-weight:600;line-height:1.5;color:var(--nc-text);">
    {% if aviso_cronometro.erro %}{{ aviso_cronometro.erro }}
    {% elif aviso_cronometro.info %}{{ aviso_cronometro.info }}
    {% else %}⏱ <strong>{{ aviso_cronometro.titulo }}</strong>: você levou {{ aviso_cronometro.real_min }} min (previsto: {{ aviso_cronometro.previsto_min }} min).{% if aviso_cronometro.pontos %} +{{ aviso_cronometro.pontos }} pontos por cronometrar.{% endif %}
    {% endif %}
  </div>
  {% endif %}

  {% if n_atrasadas %}
  <div style="margin:-4px 0 16px;">   {# [REORGANIZAR] #}
'''),
        ('tempo correndo na tela',
         r'''  {% endif %}
</div>
{% endblock %}''',
         r'''  {% endif %}

  {# [CRONOMETRO] faz o tempo correr na tela: o servidor manda o acumulado até o carregamento e o resto é contado aqui #}
  <script>
    (function () {
      const ativos = [].slice.call(document.querySelectorAll('.nc-cron[data-base]'));
      if (!ativos.length) return;
      const t0 = Date.now();
      const pad = (n) => String(n).padStart(2, '0');
      const rotulo = (s) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return h ? h + ':' + pad(m) + ':' + pad(x) : pad(m) + ':' + pad(x); };
      const tick = () => ativos.forEach((el) => { el.querySelector('.nc-cron-t').textContent = rotulo(Math.floor(Number(el.dataset.base) + (Date.now() - t0) / 1000)); });
      tick();
      setInterval(tick, 1000);
    })();
  </script>
</div>
{% endblock %}'''),
    ))
)

PRE_REQUISITOS = (
    ('cronometro.py', 'def resumir(', 'o arquivo cronometro.py (extraia o zip inteiro na pasta do projeto)'),
    ('app.py', '[REORGANIZAR]', "o pacote 'reorganizar atrasadas'"),
    ('templates/tarefas.html', '[REORGANIZAR]', "o pacote 'reorganizar atrasadas'"),
    ('decisao.py', '[APRENDIZADO-APLICADO]', "o pacote 'aprendizado aplicado'"),
    ('aprendizado.py', '[POR-CATEGORIA]', "o pacote 'aprendizado aplicado'"),
)


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def confere(rel, texto):
    """Python: compila. Template (.html): o Jinja precisa conseguir ler."""
    if rel.endswith(".py"):
        try:
            compile(texto, rel, "exec")
        except SyntaxError as e:
            return False, str(e)
    elif rel.endswith(".html"):
        try:
            import jinja2
            jinja2.Environment().parse(texto)
        except ImportError:
            pass
        except Exception as e:
            return False, str(e)[:200]
    return True, ""


def main():
    ap = argparse.ArgumentParser(description="Acrescenta o cronômetro opcional de tarefas.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    faltam = [msg for arq, marca, msg in PRE_REQUISITOS if not (RAIZ / arq).exists() or marca not in ler(RAIZ / arq)[0]]
    if faltam:
        print("NADA FOI GRAVADO. Falta aplicar antes:")
        for f in sorted(set(faltam)):
            print("  - " + f)
        return 1
    plano, problemas = [], []
    for rel, marca, trocas in ALVOS:
        arquivo = RAIZ / rel
        if not arquivo.exists():
            problemas.append(f"{rel}: o arquivo não existe.")
            continue
        texto, crlf = ler(arquivo)
        if marca in texto and all(depois in texto for _, _, depois in trocas):
            print(f"   {rel}: já aplicado (nada a fazer).")
            continue
        faltam = [rotulo for rotulo, antes, _ in trocas if texto.count(antes) != 1]
        if faltam:
            problemas.append(f"{rel}: NÃO reconheci: " + "; ".join(faltam))
            continue
        novo = texto
        for _, antes, depois in trocas:
            novo = novo.replace(antes, depois, 1)
        ok, motivo = confere(rel, novo)
        if not ok:
            problemas.append(f"{rel}: o arquivo novo não passou na conferência de sintaxe ({motivo})")
            continue
        print(f"-> {rel}: {len(trocas)} ajuste(s)")
        for rotulo, _, _ in trocas:
            print(f"     - {rotulo}")
        plano.append((arquivo, novo, crlf))
    if problemas:
        print("\nNADA FOI GRAVADO (é tudo ou nada). Motivo:")
        for p in problemas:
            print("  " + p)
        print("  Me mande o arquivo citado que eu ajusto.")
        return 1
    if not plano:
        return 0
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_cronometro.py --aplicar")
        return 0
    for arquivo, novo, crlf in plano:
        copia = arquivo.with_name(arquivo.name + ".bak")
        n = 1
        while copia.exists():
            n += 1
            copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
        shutil.copy2(arquivo, copia)
        arquivo.write_bytes(gravar_texto(novo, crlf))
        print(f"gravado: {arquivo.relative_to(RAIZ)}  (cópia do original: {copia.name})")
    print("\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
