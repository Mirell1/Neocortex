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


def _contexto_aprendido(id_usuario):
    """Padrões e taxas relevantes para escolher horário (cada item diz de onde vem)."""
    padroes = {p["tipo_padrao"]: p for p in db.listar_padroes(id_usuario)}
    metricas = {m["nome_metrica"]: float(m["valor"]) for m in db.listar_metricas(id_usuario)}
    return {
        "observado": padroes.get(aprendizado.PADRAO_PERIODO_OBSERVADO),
        "declarado": agenda.normalizar_periodo((padroes.get("energia") or {}).get("valor")),
        "metricas": metricas,
    }


def _pontuar(periodo, ctx):
    """Pontuação de um período do dia + as razões, na ordem em que pesam."""
    pontos, base = 0.0, []
    obs = ctx["observado"]
    if obs and obs.get("valor") == periodo:
        if obs.get("confianca") in ("media", "alta"):
            pontos += 2
            base.append(f"período em que você mais conclui (observado, confiança {obs['confianca']})")
        else:
            pontos += 1
            base.append("período em que você tende a concluir (observado, confiança baixa)")
    if ctx["declarado"] == periodo:
        pontos += 1
        base.append("período de energia que você declarou")
    taxa = ctx["metricas"].get(f"taxa_conclusao_{periodo}")
    if taxa is not None:
        pontos += taxa
        base.append(f"você concluiu {taxa:.0%} das tarefas agendadas nesse período")
    return pontos, base


# ============================================================
# SUGERIR HORÁRIOS
# ============================================================
def sugerir_horarios(id_usuario, dia, duracao_min=60, agora=None, max_sugestoes=3):
    """
    Janelas livres do dia (descontando tarefas, compromissos, rotina,
    restrições e disponibilidade), ordenadas pelo que se SABE do usuário.
    Cada sugestão diz em que se baseia. Sem dados, só ordena por horário.
    """
    agora = agora or datetime.now()
    duracao = timedelta(minutes=duracao_min)
    blocos = agenda.blocos_ocupados(id_usuario, dia)
    apos = agenda.arredondar_para_cima(agora) if dia == agora.date() else None
    livres = agenda.janelas_livres(blocos, dia, apos)

    ctx = _contexto_aprendido(id_usuario)
    candidatos = []
    for ini, fim in livres:
        t = agenda.arredondar_para_cima(ini)
        while t + duracao <= fim:
            pontos, base = _pontuar(agenda.periodo_da_hora(t.hour), ctx)
            candidatos.append((pontos, t, base))
            t += timedelta(minutes=agenda.PASSO_MIN)

    candidatos.sort(key=lambda c: (-c[0], c[1]))
    escolhidas = []
    for pontos, t, base in candidatos:
        if all(t >= e["_fim"] or t + duracao <= e["_ini"] for e in escolhidas):
            escolhidas.append({"_ini": t, "_fim": t + duracao, "periodo": agenda.periodo_da_hora(t.hour), "base": base})
        if len(escolhidas) == max_sugestoes:
            break

    sugestoes = [
        {"inicio": e["_ini"].isoformat(timespec="minutes"), "fim": e["_fim"].isoformat(timespec="minutes"),
         "periodo": e["periodo"], "base": e["base"] or ["horário livre (ainda sem histórico para personalizar)"]}
        for e in escolhidas
    ]
    saida = {"dia": dia.isoformat(), "duracao_min": duracao_min, "sugestoes": sugestoes}
    if not sugestoes:
        saida["observacao"] = "Não há janela livre desse tamanho nesse dia."
        return saida

    # registra a decisão: se o usuário criar uma tarefa num desses horários, a ligação é feita depois
    db.salvar_decisao(
        id_usuario,
        f"sugestão de horário para {dia.isoformat()} ({duracao_min} min)",
        "janelas livres; padrão observado; energia declarada; taxa de conclusão por período",
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
