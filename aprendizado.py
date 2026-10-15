"""
NEOCORTEX — aprendizado.py

Fecha o circuito:

    EVENTO (tarefa concluída, adiada, cancelada, recomendação aceita...)
      -> ANÁLISE (padrões e taxas calculados do histórico REAL)
      -> ATUALIZAÇÃO (padrão observado, métricas, memória)
      -> EFEITO FUTURO (decisao.py usa isso para sugerir horários)

IMPORTANTE — o que isto É e o que NÃO é:
  É aprendizado PARAMÉTRICO: estatística descritiva + regras com limiares
  mínimos de evidência. Os "parâmetros" aprendidos são o período em que a
  pessoa de fato conclui tarefas, as taxas de conclusão por período, o atraso
  típico e a taxa de aceitação de recomendações.
  NÃO é Machine Learning preditivo (não há treino de modelo). Ver
  ml_preparacao.py para a preparação e para os critérios de quando o ML passaria
  a valer a pena.

Princípios (todos cobertos por testes):
  - Uma ocorrência isolada não vira padrão (mínimo de evidências).
  - Um padrão forte não é derrubado por uma ocorrência isolada.
  - Um padrão não fica eterno: só vale a janela recente (60 dias) e é
    trocado quando a evidência nova é forte e consistente.
  - O que o usuário DISSE (padrão 'energia', do onboarding) é guardado à
    parte do que ele FEZ (padrão 'periodo_conclusao_observado').
  - Métrica só é gravada quando há dados suficientes. Nunca se inventa número.
"""

import logging
import statistics
from datetime import datetime, timedelta

import db
from periodos import JANELA_LOTE_MIN, PERIODOS, normalizar_periodo, periodo_da_hora

log = logging.getLogger("neocortex.aprendizado")

# ---- parâmetros (ajuste aqui, não no meio do código) ----------------
JANELA_RECENTE_DIAS = 60        # só o comportamento recente conta
MIN_EVENTOS_PADRAO = 5          # mínimo de eventos para existir um padrão
PARTICIPACAO_MIN = 0.5          # o período dominante precisa de >= 50% dos eventos
MIN_EVENTOS_TROCA = 8           # para TROCAR um padrão de confiança média/alta
PARTICIPACAO_TROCA = 0.6        # ...o novo precisa dominar com >= 60%
MIN_TAREFAS_PERIODO = 5         # mínimo de tarefas encerradas por período p/ taxa
MIN_AMOSTRA_METRICA = 5         # mínimo para atraso mediano / taxa de adiamento
MIN_RESULTADOS_ACEITACAO = 5    # mínimo de reações para taxa de aceitação
HORAS_VALIDADE_TAREFA_AGORA = 6 # recomendação 'tarefa_agora' vence após N horas
PERIODO_REF = f"ultimos_{JANELA_RECENTE_DIAS}d"

PADRAO_PERIODO_OBSERVADO = "periodo_conclusao_observado"
MEMORIA_PERIODO = "periodo_conclusao_preferido"

_ORDEM = {"baixa": 1, "media": 2, "alta": 3}
_NIVEIS = {1: "baixa", 2: "media", 3: "alta"}


# ============================================================
# 1. PADRÃO: período em que a pessoa realmente conclui
# ============================================================
def deduplicar_lotes(momentos, janela_min=JANELA_LOTE_MIN):
    """
    concluido_em é o horário do CLIQUE em "concluir", não de quando a pessoa
    fez a tarefa. Quem marca várias de uma vez parece "noturna" só pelo
    horário do clique. Conclusões muito próximas contam como UM evento.
    """
    eventos, ultimo = [], None
    for m in sorted(momentos):
        if ultimo is None or (m - ultimo) > timedelta(minutes=janela_min):
            eventos.append(m)
        ultimo = m
    return eventos


def classificar_confianca(n, participacao):
    if n >= 15 and participacao >= 0.7:
        return "alta"
    if n >= 8 and participacao >= 0.6:
        return "media"
    if n >= MIN_EVENTOS_PADRAO and participacao >= PARTICIPACAO_MIN:
        return "baixa"
    return None


def calcular_periodo_observado(concluidas_em, agora):
    """
    Período (manha/tarde/noite) em que a pessoa mais conclui, usando só a
    janela recente. Retorna None quando não há evidência suficiente ou não
    há um período dominante claro.
    """
    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    eventos = deduplicar_lotes([m for m in concluidas_em if corte <= m <= agora])
    n = len(eventos)
    if n < MIN_EVENTOS_PADRAO:
        return None

    contagem = {p: 0 for p in PERIODOS}
    for e in eventos:
        contagem[periodo_da_hora(e.hour)] += 1
    ordenado = sorted(contagem.items(), key=lambda kv: kv[1], reverse=True)
    (topo, qtd_topo), (_, qtd_segundo) = ordenado[0], ordenado[1]
    if qtd_topo == qtd_segundo:      # empate no topo: não há período dominante
        return None

    participacao = qtd_topo / n
    confianca = classificar_confianca(n, participacao)
    if confianca is None:
        return None
    return {"valor": topo, "n": n, "participacao": round(participacao, 3), "confianca": confianca}


def decidir_atualizacao(atual, novo):
    """
    Regra de atualização do padrão (função pura, fácil de testar).

    atual: {'valor','confianca','evidencias'} ou None
    novo : saída de calcular_periodo_observado() ou None
    Retorna (acao, estado) com acao em: criar | reforcar | trocar | manter
    """
    if novo is None:
        return "manter", atual          # sem evidência suficiente agora: nada muda
    if atual is None:
        return "criar", novo

    if atual["valor"] == novo["valor"]:
        confianca = novo["confianca"]
        if _ORDEM[confianca] < _ORDEM[atual["confianca"]]:
            # a confiança desce no máximo um nível por recálculo
            confianca = _NIVEIS[_ORDEM[atual["confianca"]] - 1]
        return "reforcar", {**novo, "confianca": confianca}

    # o dominante mudou: exige evidência nova FORTE para trocar
    if atual["confianca"] == "baixa":
        pode_trocar = novo["n"] >= MIN_EVENTOS_PADRAO and novo["participacao"] >= PARTICIPACAO_MIN
    else:
        pode_trocar = novo["n"] >= MIN_EVENTOS_TROCA and novo["participacao"] >= PARTICIPACAO_TROCA
    if not pode_trocar:
        return "manter", atual

    confianca = novo["confianca"]
    if _ORDEM[confianca] > _ORDEM["media"]:
        confianca = "media"             # padrão recém-trocado nasce com confiança no máximo média
    return "trocar", {**novo, "confianca": confianca}


# ============================================================
# 2. MÉTRICAS: planejado x realizado
# ============================================================
def _tarefas_encerradas(tarefas, agora):
    """Concluídas, ou abertas com prazo vencido. Canceladas ficam de fora."""
    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    encerradas = []
    for t in tarefas:
        if t["data_inicio"] < corte or t["status"] == "cancelada":
            continue
        concluida = t["status"] == "concluida"
        vencida = t["status"] in ("pendente", "em_andamento") and t["data_fim"] < agora
        if concluida or vencida:
            encerradas.append((t, concluida))
    return encerradas


def calcular_taxas_por_periodo(tarefas, agora):
    """
    Taxa de conclusão das tarefas ENCERRADAS, por período em que foram
    AGENDADAS. É a medida mais robusta (não depende de quando a pessoa
    clica). Só devolve períodos com pelo menos MIN_TAREFAS_PERIODO tarefas.
    """
    por_periodo = {p: [0, 0] for p in PERIODOS}      # [concluidas, total]
    for t, concluida in _tarefas_encerradas(tarefas, agora):
        p = periodo_da_hora(t["data_inicio"].hour)
        por_periodo[p][1] += 1
        por_periodo[p][0] += 1 if concluida else 0
    return {
        p: {"n": total, "concluidas": ok, "taxa": round(ok / total, 4)}
        for p, (ok, total) in por_periodo.items() if total >= MIN_TAREFAS_PERIODO
    }


def calcular_atraso_mediano_min(tarefas, agora):
    """
    Mediana de (concluido_em - data_fim) em minutos. Negativo = costuma
    terminar antes do fim planejado. None se houver menos de MIN_AMOSTRA_METRICA.
    """
    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    atrasos = [
        (t["concluido_em"] - t["data_fim"]).total_seconds() / 60
        for t in tarefas
        if t["status"] == "concluida" and t["concluido_em"] and t["data_inicio"] >= corte
    ]
    if len(atrasos) < MIN_AMOSTRA_METRICA:
        return None
    return round(statistics.median(atrasos), 1), len(atrasos)


def calcular_taxa_adiamento(tarefas, eventos, agora):
    """Fração das tarefas recentes que foram adiadas ao menos uma vez."""
    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    recentes = {t["id_tarefa"] for t in tarefas if t["data_inicio"] >= corte and t["status"] != "cancelada"}
    if len(recentes) < MIN_AMOSTRA_METRICA:
        return None
    adiadas = {e["id_tarefa"] for e in eventos if e["tipo_evento"] == "adiou" and e["id_tarefa"] in recentes}
    return round(len(adiadas) / len(recentes), 4), len(recentes)


# ============================================================
# 3. RECOMENDAÇÃO -> REAÇÃO -> RESULTADO
# ============================================================
def resolver_recomendacoes(id_usuario, agora=None):
    """
    Fecha as recomendações que ainda não têm reação, olhando o que o usuário
    de fato fez com a tarefa recomendada:

      concluída (a tempo)     -> aceitou
      cancelada               -> recusou
      prazo passou em aberto  -> ignorou
      (adiou/excluiu são registrados na hora, pelo db.py)

    Idempotente: só olha recomendações sem resultado.
    """
    agora = agora or datetime.now()
    contagem = {"aceitou": 0, "recusou": 0, "ignorou": 0}
    for r in db.listar_recomendacoes_sem_resultado(id_usuario):
        validade = timedelta(hours=HORAS_VALIDADE_TAREFA_AGORA)
        acao = resultado = None

        if r["tarefa_status"] == "concluida":
            dentro_da_janela = (
                r["tipo"] != "tarefa_agora"
                or (r["tarefa_concluido_em"] and r["tarefa_concluido_em"] - r["criado_em"] <= validade)
            )
            acao, resultado = ("aceitou", "concluida") if dentro_da_janela else ("ignorou", "concluida_fora_da_janela")
        elif r["tarefa_status"] == "cancelada":
            acao, resultado = "recusou", "cancelada"
        else:
            limite = r["criado_em"] + validade if r["tipo"] == "tarefa_agora" else r["tarefa_data_fim"]
            if agora > limite:
                acao, resultado = "ignorou", "prazo_vencido"

        if acao:
            db.salvar_resultado_recomendacao(r["id_recomendacao"], id_usuario, acao, resultado)
            contagem[acao] += 1
    return contagem


# ============================================================
# 4. ORQUESTRAÇÃO
# ============================================================
def recalcular_aprendizado(id_usuario, agora=None):
    """
    Recalcula tudo o que dá para aprender com o histórico do usuário e
    persiste o resultado. Barato (algumas consultas por usuário).
    """
    agora = agora or datetime.now()
    resumo = {"recomendacoes": resolver_recomendacoes(id_usuario, agora)}

    tarefas = db.listar_tarefas(
        id_usuario,
        data_inicio=agora - timedelta(days=JANELA_RECENTE_DIAS),
    )
    eventos = db.listar_eventos_usuario(
        id_usuario,
        desde=agora - timedelta(days=JANELA_RECENTE_DIAS),
    )

    # --- período em que a pessoa de fato conclui ---
    concluidas_em = [t["concluido_em"] for t in tarefas if t["status"] == "concluida" and t["concluido_em"]]
    novo = calcular_periodo_observado(concluidas_em, agora)
    padrao = db.obter_padrao(id_usuario, PADRAO_PERIODO_OBSERVADO)
    atual = None
    if padrao and padrao.get("confianca"):
        atual = {"valor": padrao["valor"], "confianca": padrao["confianca"], "evidencias": padrao.get("evidencias")}

    acao, estado = decidir_atualizacao(atual, novo)
    if acao in ("criar", "reforcar", "trocar"):
        db.salvar_padrao_observado(id_usuario, PADRAO_PERIODO_OBSERVADO, estado["valor"],
                                   estado["confianca"], estado["n"])
        db.substituir_memoria(
            id_usuario, MEMORIA_PERIODO,
            f"Costuma concluir tarefas no período da {estado['valor']}.",
            estado["confianca"], estado["n"], origem="observado",
        )
    resumo["periodo_observado"] = {"acao": acao, "estado": estado}

    # --- métricas (só com dados suficientes) ---
    metricas = {}
    for periodo, d in calcular_taxas_por_periodo(tarefas, agora).items():
        metricas[f"taxa_conclusao_{periodo}"] = d["taxa"]
        metricas[f"tarefas_encerradas_{periodo}"] = d["n"]
    atraso = calcular_atraso_mediano_min(tarefas, agora)
    if atraso:
        metricas["atraso_mediano_min"] = atraso[0]
    adiamento = calcular_taxa_adiamento(tarefas, eventos, agora)
    if adiamento:
        metricas["taxa_adiamento"] = adiamento[0]
    contagem = db.contar_resultados_recomendacoes(id_usuario)
    total_reacoes = sum(contagem.values())
    if total_reacoes >= MIN_RESULTADOS_ACEITACAO:
        metricas["taxa_aceitacao_recomendacoes"] = round(contagem.get("aceitou", 0) / total_reacoes, 4)

    for nome, valor in metricas.items():
        db.salvar_metrica_unica(id_usuario, nome, valor, PERIODO_REF)
    resumo["metricas"] = metricas
    return resumo


def apos_evento(id_usuario):
    """
    Gancho chamado depois de conclusão/edição/cancelamento. Nunca derruba a
    ação do usuário: se o aprendizado falhar, a falha é REGISTRADA no log (com
    a causa real) e a operação principal continua.
    """
    try:
        return recalcular_aprendizado(id_usuario)
    except Exception:
        log.exception("Falha ao recalcular aprendizado do usuário %s", id_usuario)
        return None


def recalcular_todos():
    """
    Recalcula o aprendizado de TODOS os usuários a partir do histórico que já
    existe (use uma vez depois de aplicar a migração; depois disso o gancho
    apos_evento mantém tudo em dia).  python aprendizado.py
    """
    with db.conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_usuario FROM usuarios ORDER BY id_usuario")
            ids = [linha["id_usuario"] for linha in cur.fetchall()]
    for id_usuario in ids:
        apos_evento(id_usuario)
    return len(ids)


# ============================================================
# 5. LEITURA (o que a IA recebe) — separa declarado x observado
# ============================================================
def obter_aprendizado(id_usuario):
    """
    Resumo compacto do que o sistema sabe e com que grau de certeza.
    Cada item diz de onde veio (declarado pelo usuário x observado no
    comportamento) e quantas evidências o sustentam.
    """
    padroes = []
    declarado_energia = observado_periodo = None
    for p in db.listar_padroes(id_usuario):
        item = {"tipo": p["tipo_padrao"], "valor": p["valor"], "fonte": p.get("fonte") or "declarado"}
        if p.get("confianca"):
            item["confianca"] = p["confianca"]
        if p.get("evidencias") is not None:
            item["evidencias"] = p["evidencias"]
        padroes.append(item)
        if p["tipo_padrao"] == "energia":
            declarado_energia = normalizar_periodo(p["valor"])   # aceita "Manhã" do cadastro antigo
        if p["tipo_padrao"] == PADRAO_PERIODO_OBSERVADO:
            observado_periodo = p["valor"]

    metricas = {m["nome_metrica"]: float(m["valor"]) for m in db.listar_metricas(id_usuario)}
    memorias = [
        {"conteudo": m["conteudo"], "confianca": m["confianca"], "origem": m.get("origem")}
        for m in db.listar_memorias_ativas(id_usuario)
    ]

    saida = {"padroes": padroes, "metricas": metricas, "memorias": memorias}
    if declarado_energia in PERIODOS and observado_periodo in PERIODOS and declarado_energia != observado_periodo:
        saida["divergencia"] = (
            f"Declarou render mais de {declarado_energia}, mas conclui mais de {observado_periodo}. "
            "O comportamento observado é um fato; o declarado é uma preferência."
        )
    if not metricas and not any(p["fonte"] == "observado" for p in padroes):
        saida["observacao"] = "Ainda não há histórico suficiente para padrões observados."
    return saida


if __name__ == "__main__":
    print(f"Aprendizado recalculado para {recalcular_todos()} usuário(s).")
