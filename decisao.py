"""
NEOCORTEX — decisao.py

Motor de decisão DETERMINÍSTICO (sem LLM). A IA só pede o resultado e o
explica em linguagem natural; quem decide é uma regra rastreável.

Cada decisão registra:
  contexto + critérios + decisão   -> tabela decisoes
  recomendação ligada à tarefa     -> tabela recomendacoes
e, depois, a REAÇÃO do usuário vira resultado (aprendizado.py / db.py).
"""

from datetime import datetime, timedelta

import agenda
import aprendizado
import db

JANELA_VINCULO_SUGESTAO_H = 3   # sugestão de horário só vira "recomendação aceita" se a tarefa for criada em até N h
MAX_CANDIDATAS_AGORA = 3
HORIZONTE_PROXIMA_H = 3         # "começa já, já" = próximas 3 horas
# [APRENDIZADO-APLICADO] folga reservada DEPOIS da tarefa, pelo atraso e pelo adiamento que a própria pessoa tem
FOLGA_ATRASO_ACIONA_MIN = 10    # só reserva folga se o atraso mediano for de pelo menos 10 min
FOLGA_PASSO_MIN = 15            # a folga é arredondada para cima de 15 em 15 min
FOLGA_MAX_MIN = 60              # teto: nunca reserva mais que 1 hora
ADIAMENTO_ALTO = 0.4            # adiou 40% ou mais das tarefas recentes
FOLGA_EXTRA_ADIAMENTO_MIN = 15  # folga a mais para quem adia muito
DESCANSO_MIN_LIVRE = 30         # só convida para um hobby se houver pelo menos 30 min livres
# [CRONOMETRO] margem de preparo ANTES da tarefa, pelo atraso que a pessoa tem para COMEÇAR (medido pelo cronômetro opcional)
PREPARO_ACIONA_MIN = 10         # só reserva margem se ela costuma começar 10 min ou mais depois do horário marcado
PREPARO_MAX_MIN = 60            # teto: nunca reserva mais que 1 hora


def _contexto_aprendido(id_usuario, categoria=None):
    """Padrões e taxas relevantes para escolher horário (cada item diz de onde vem).
    [APRENDIZADO-APLICADO] Com categoria, traz também o que se aprendeu SOBRE ela (ex.: estudo)."""
    aprendizado.garantir_vigente(id_usuario)   # [LOTE-1.1] snapshot vencido é recalculado antes de ler (com trava de frequência)
    padroes = {p["tipo_padrao"]: p for p in db.listar_padroes(id_usuario)}
    metricas = {m["nome_metrica"]: float(m["valor"]) for m in db.listar_metricas(id_usuario)}
    return {
        "observado": padroes.get(aprendizado.PADRAO_PERIODO_OBSERVADO),
        "declarado": agenda.normalizar_periodo((padroes.get("energia") or {}).get("valor")),
        "metricas": metricas,
        "categoria": categoria,
        "observado_categoria": padroes.get(f"{aprendizado.PADRAO_PERIODO_OBSERVADO}:{categoria}") if categoria else None,
    }


def _pontuar(periodo, ctx):
    """Pontuação de um período do dia + as razões, na ordem em que pesam.
    [APRENDIZADO-APLICADO] Para uma categoria, o que se aprendeu sobre ELA vale mais que o geral."""
    pontos, base = 0.0, []
    categoria = ctx.get("categoria")
    obs_cat = ctx.get("observado_categoria")
    obs = obs_cat or ctx["observado"]
    escopo = f" nas suas tarefas de {categoria}" if obs_cat and categoria else ""
    if obs and obs.get("valor") == periodo:
        if obs.get("confianca") in ("media", "alta"):
            pontos += 2
            base.append(f"período em que você mais conclui{escopo} (observado, confiança {obs['confianca']})")
        else:
            pontos += 1
            base.append(f"período em que você tende a concluir{escopo} (observado, confiança baixa)")
    if ctx["declarado"] == periodo:
        pontos += 1
        base.append("período de energia que você declarou")
    taxa_cat = ctx["metricas"].get(f"taxa_conclusao_{categoria}_{periodo}") if categoria else None
    taxa = taxa_cat if taxa_cat is not None else ctx["metricas"].get(f"taxa_conclusao_{periodo}")
    if taxa is not None:
        pontos += taxa
        de = f" de {categoria}" if taxa_cat is not None else ""
        base.append(f"você concluiu {taxa:.0%} das tarefas{de} agendadas nesse período")
    return pontos, base


# ============================================================
# SUGERIR HORÁRIOS
# ============================================================
def _descontar(livres, reservas):
    """[REORGANIZAR] Tira das janelas livres os intervalos já reservados por outras propostas (pares (ini, fim) de datetime)."""
    for r_ini, r_fim in reservas:
        novas = []
        for ini, fim in livres:
            if r_fim <= ini or r_ini >= fim:
                novas.append((ini, fim))
                continue
            if ini < r_ini:
                novas.append((ini, r_ini))
            if r_fim < fim:
                novas.append((r_fim, fim))
        livres = novas
    return livres


def _folga_aprendida(ctx):
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
    return saida


def vincular_sugestao_a_tarefa(id_usuario, id_tarefa, data_inicio, agora=None):
    """
    Se a tarefa recém-criada começa em um horário que o sistema sugeriu há
    pouco, registra a recomendação ligada à tarefa. A reação (concluiu,
    adiou, cancelou, ignorou) passa a ser medida. Retorna id_recomendacao ou None.
    """
    agora = agora or datetime.now()
    inicio_iso = db._como_datetime(data_inicio).isoformat(timespec="minutes")
    for d in db.listar_decisoes(id_usuario, limite=10):
        if not d["decisao_tomada"].startswith("SUGESTOES:"):
            continue
        if agora - d["criado_em"] > timedelta(hours=JANELA_VINCULO_SUGESTAO_H):
            break  # listar_decisoes vem da mais recente para a mais antiga
        if inicio_iso in d["decisao_tomada"][len("SUGESTOES:"):].split(";"):
            return db.salvar_recomendacao(
                id_usuario, f"Horário sugerido pelo sistema: {inicio_iso}",
                id_decisao=d["id_decisao"], id_tarefa=id_tarefa, tipo="horario",
            )
    return None


# ============================================================
# RECOMENDAR TAREFA PARA AGORA
# ============================================================
def _sugestao_descanso(id_usuario, agora, situacao):
    """[BEM-ESTAR] Sem nada urgente e com tempo livre, convida para um hobby do perfil.
    É só um convite (nunca cria nada) e nunca atrapalha a recomendação: qualquer falha aqui devolve None."""
    try:
        if situacao.get("atual") or not (agenda.INICIO_DIA <= agora.time() < agenda.FIM_DIA):
            return None
        livres = situacao.get("minutos_livres_ate_proximo")
        if livres is not None and livres < DESCANSO_MIN_LIVRE:
            return None
        hobbies = [h["nome"] for h in db.listar_hobbies_usuario(id_usuario) if h.get("nome")]
        if not hobbies:
            return None
        hobby = hobbies[(agora.toordinal() + id_usuario) % len(hobbies)]      # varia de um dia para o outro
        tempo = f"{livres} min livres" if livres is not None else "o resto do dia livre"
        return {"hobby": hobby, "minutos_livres": livres,
                "texto": f"Você tem {tempo} e nada urgente. Que tal um dos seus hobbies: {hobby}?",
                "base": ["hobby do seu perfil", "nenhuma tarefa urgente agora", tempo]}
    except Exception:
        return None


def recomendar_tarefa_agora(id_usuario, agora=None):
    """
    "O que devo fazer agora?" — escolhe entre as tarefas abertas, por
    camadas (menor número = mais prioritária):

      1  está dentro do horário planejado agora
      2  atrasada (o prazo passou; mais antiga primeiro)
      3  começa nas próximas horas
      4  agendada para hoje, mais tarde

    Também informa se o usuário está ocupado agora (rotina/compromisso/tarefa),
    quanto tempo livre há até o próximo bloco e se este é um horário forte
    para ele. Registra decisão + recomendação ligadas à tarefa escolhida.
    """
    agora = agora or datetime.now()
    situacao = agenda.situacao_agora(id_usuario, agora)
    abertas = db.listar_tarefas_abertas(id_usuario, data_fim_minima=agora - timedelta(days=7))
    abertas = db.enriquecer_tarefas(id_usuario, abertas)   # prioridade, prazo do objetivo, dependência

    candidatas = []
    for t in abertas:
        if t.get("dependencia_pendente"):
            continue
        if t["data_inicio"] <= agora < t["data_fim"]:
            atual = situacao["atual"]
            # ocupado com OUTRA coisa => não recomenda; o próprio bloco da atividade
            # (tarefa de trabalho dentro do turno 'Trabalho') não conta como ocupação
            if atual and not (atual.get("tipo") == "tarefa" and atual.get("id") == t["id_tarefa"]) \
                    and not agenda.bloco_da_mesma_atividade(atual, t.get("categoria")):
                continue
            camada, motivo = 1, "está dentro do horário planejado"
        elif t["data_fim"] <= agora:
            atraso = int((agora - t["data_fim"]).total_seconds() // 60)
            camada, motivo = 2, f"está atrasada (o prazo passou há {atraso} min)"
        elif agora < t["data_inicio"] <= agora + timedelta(hours=HORIZONTE_PROXIMA_H):
            faltam = int((t["data_inicio"] - agora).total_seconds() // 60)
            camada, motivo = 3, f"começa em {faltam} min"
        elif agora < t["data_inicio"] and t["data_inicio"].date() == agora.date():
            camada, motivo = 4, f"está agendada para hoje às {t['data_inicio']:%H:%M}"
        else:
            continue
        candidatas.append((camada, t["data_inicio"], t, motivo))
    candidatas.sort(
        key=lambda c: (
            c[0],
            {"alta": 0, "media": 1, "baixa": 2}.get(c[2].get("prioridade"), 1),
            c[2].get("objetivo_prazo") or datetime.max,   # sempre datetime: nunca compara texto com data
            c[1],
        )
    )
    candidatas = candidatas[:MAX_CANDIDATAS_AGORA]

    periodo = agenda.periodo_da_hora(agora.hour)
    ctx = _contexto_aprendido(id_usuario)
    contexto_aprendido = {"periodo_atual": periodo}
    if ctx["observado"]:
        contexto_aprendido["periodo_observado"] = ctx["observado"]["valor"]
        contexto_aprendido["confianca_observado"] = ctx["observado"].get("confianca")
    if ctx["declarado"]:
        contexto_aprendido["periodo_declarado"] = ctx["declarado"]
    taxa = ctx["metricas"].get(f"taxa_conclusao_{periodo}")
    if taxa is not None:
        contexto_aprendido["taxa_conclusao_no_periodo_atual"] = taxa

    def _bloco(b):
        return None if not b else {"tipo": b["tipo"], "titulo": b["titulo"],
                                   "inicio": b["inicio"].isoformat(timespec="minutes"),
                                   "fim": b["fim"].isoformat(timespec="minutes")}

    saida = {
        "agora": agora.isoformat(timespec="minutes"),
        "ocupado_agora_com": _bloco(situacao["atual"]),
        "proximo_bloco": _bloco(situacao["proximo"]),
        "minutos_livres_ate_proximo_bloco": situacao["minutos_livres_ate_proximo"],
        "contexto_aprendido": contexto_aprendido,
        "candidatas": [
            {
                "id_tarefa": t["id_tarefa"], "titulo": t["titulo"], "categoria": t["categoria"],
                "inicio": t["data_inicio"].isoformat(timespec="minutes"),
                "fim": t["data_fim"].isoformat(timespec="minutes"), "motivo": motivo,
                **({"prioridade": t["prioridade"]} if t.get("prioridade") else {}),
                **({"objetivo_prazo": t["objetivo_prazo"].isoformat(timespec="minutes")}
                   if t.get("objetivo_prazo") else {}),
            }
            for _, _, t, motivo in candidatas
        ],
    }
    if not candidatas:
        saida["observacao"] = "Não há tarefas abertas relevantes para agora."
        descanso = _sugestao_descanso(id_usuario, agora, situacao)   # [BEM-ESTAR]
        if descanso:
            saida["sugestao_descanso"] = descanso
            saida["observacao"] += " " + descanso["texto"]
        return saida

    topo = candidatas[0][2]
    existente = db.buscar_recomendacao_aberta_recente(id_usuario, topo["id_tarefa"], "tarefa_agora")
    if existente:
        saida["id_recomendacao"] = existente["id_recomendacao"]
    else:
        _, id_rec = db.registrar_decisao_com_recomendacao(
            id_usuario,
            f"agora={agora:%Y-%m-%d %H:%M}; candidatas={len(candidatas)}; "
            f"ocupado_agora={'sim' if situacao['atual'] else 'nao'}",
            "camada (dentro do horário > atrasada > próxima > hoje); desempate por prioridade, prazo do objetivo e horário",
            f"Recomendar tarefa #{topo['id_tarefa']} '{topo['titulo']}'",
            f"{topo['titulo']}: {candidatas[0][3]}",
            id_tarefa=topo["id_tarefa"], tipo="tarefa_agora",
        )
        saida["id_recomendacao"] = id_rec
    saida["recomendada"] = topo["id_tarefa"]
    return saida
