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
  - A confiança é derivada da amostra atual, não da frequência de recálculo.
  - Um padrão não fica eterno: só vale a janela recente (60 dias) e é
    trocado quando a evidência nova é forte e consistente.
  - O que o usuário DISSE (padrão 'energia', do onboarding) é guardado à
    parte do que ele FEZ (padrão 'periodo_conclusao_observado').
  - Métrica só é gravada quando há dados suficientes. Nunca se inventa número.
"""

import logging
import statistics
import threading
import time
from datetime import datetime, timedelta

import cronometro
import db
from periodos import JANELA_LOTE_MIN, PERIODOS, normalizar_periodo, periodo_da_hora

log = logging.getLogger("neocortex.aprendizado")

# ---- parâmetros (ajuste aqui, não no meio do código) ----------------
JANELA_RECENTE_DIAS = 60        # só o comportamento recente conta
MIN_EVENTOS_PADRAO = 5          # mínimo de eventos para existir um padrão
PARTICIPACAO_MIN = 0.5          # o período dominante precisa de >= 50% dos eventos
MIN_TAREFAS_PERIODO = 5         # mínimo de tarefas encerradas por período p/ taxa
MIN_AMOSTRA_METRICA = 5         # mínimo para atraso mediano / taxa de adiamento
MIN_RESULTADOS_ACEITACAO = 5    # mínimo de reações para taxa de aceitação
HORAS_VALIDADE_TAREFA_AGORA = 6 # recomendação 'tarefa_agora' vence após N horas
CATEGORIAS_APRENDIDAS = ("estudo", "trabalho", "hobby", "pessoal", "saude")   # [POR-CATEGORIA] "outro" não ensina nada
MIN_TAREFAS_CRONOMETRADAS = 5       # [CRONOMETRO] abaixo disso, o ritmo medido pelo cronômetro não é confiável
LIMITE_ATRASO_INICIO_H = 12         # começar a mais de 12 h do horário marcado não é "atraso para começar": fica de fora
PERIODO_REF = f"ultimos_{JANELA_RECENTE_DIAS}d"

PADRAO_PERIODO_OBSERVADO = "periodo_conclusao_observado"
MEMORIA_PERIODO = "periodo_conclusao_preferido"

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
    return {"valor": topo, "n": n, "participacao": round(participacao, 3), "confianca": confianca,
            "dias_distintos": len({e.date() for e in eventos}),
            "primeira_evidencia": min(eventos).isoformat(), "ultima_evidencia": max(eventos).isoformat()}


def decidir_atualizacao(atual, novo):
    """
    Regra de atualização do padrão (função pura, fácil de testar).

    atual: {'valor','confianca','evidencias'} ou None
    novo : saída de calcular_periodo_observado() ou None
    Retorna criar | reforcar | trocar | manter | expirar. Sem histerese por execução.
    """
    if novo is None:
        return ("expirar" if atual else "manter"), None
    if atual is None:
        return "criar", novo
    return ("reforcar" if atual["valor"] == novo["valor"] else "trocar"), novo


# ============================================================
# 2. MÉTRICAS: planejado x realizado
# ============================================================
def _tarefas_encerradas(tarefas, agora):
    """Coorte de prazos já vencidos na janela; conclusão deve ser conhecida."""
    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    encerradas = []
    for t in tarefas:
        if not corte <= t["data_fim"] < agora or t["status"] == "cancelada":
            continue
        concluida = t["status"] == "concluida" and bool(t.get("concluido_em")) and t["concluido_em"] <= agora
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
        if t["status"] == "concluida" and t["concluido_em"] and corte <= t["concluido_em"] <= agora and t["data_fim"] <= agora
    ]
    if len(atrasos) < MIN_AMOSTRA_METRICA:
        return None
    return round(statistics.median(atrasos), 1), len(atrasos)


def calcular_taxa_adiamento(tarefas, eventos, agora):
    """Fração da coorte de prazos vencidos com adiamento observado na janela."""
    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    recentes = {t["id_tarefa"] for t, _ in _tarefas_encerradas(tarefas, agora)}
    if len(recentes) < MIN_AMOSTRA_METRICA:
        return None
    adiadas = {e["id_tarefa"] for e in eventos if e["tipo_evento"] == "adiou" and e["id_tarefa"] in recentes and corte <= e["data_hora"] <= agora}
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
def calcular_metricas_cronometro(tarefas, eventos, agora):
    """
    [CRONOMETRO] O ritmo REAL da pessoa, medido pelo cronômetro opcional (só tarefas concluídas com ele):
      atraso_inicio_mediano_min    quando ela COMEÇA em relação ao horário marcado (positivo = começa depois)
      excesso_duracao_mediano_min  quanto ela LEVA a mais (ou a menos, se negativo) do que o previsto
    Só com MIN_TAREFAS_CRONOMETRADAS ciclos plausíveis. Devolve um dict com as métricas, ou None.
    """
    por_tarefa = {}
    for e in eventos:
        if agora - timedelta(days=JANELA_RECENTE_DIAS) <= e["data_hora"] <= agora:
            por_tarefa.setdefault(e["id_tarefa"], []).append(e)
    atrasos, excessos = [], []
    for t in tarefas:
        if t["status"] != "concluida" or not t.get("concluido_em") or not agora - timedelta(days=JANELA_RECENTE_DIAS) <= t["concluido_em"] <= agora:
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


def recalcular_aprendizado(id_usuario, agora=None):
    """
    Recalcula tudo o que dá para aprender com o histórico do usuário e
    persiste o resultado. Barato (algumas consultas por usuário).
    """
    agora = agora or datetime.now()
    resumo = {"recomendacoes": resolver_recomendacoes(id_usuario, agora)}

    corte = agora - timedelta(days=JANELA_RECENTE_DIAS)
    tarefas = db.listar_tarefas_aprendizado(id_usuario, corte, agora)
    eventos = db.listar_eventos_usuario(
        id_usuario,
        desde=agora - timedelta(days=JANELA_RECENTE_DIAS),
    )
    # Relógios do banco e da aplicação podem divergir ligeiramente.
    # Um evento futuro não é evidência nem deve vencer imediatamente o snapshot.
    eventos = [e for e in eventos if corte <= e["data_hora"] <= agora]

    # --- período em que a pessoa de fato conclui ---
    concluidas_em = [t["concluido_em"] for t in tarefas if t["status"] == "concluida" and t["concluido_em"]]
    novo = calcular_periodo_observado(concluidas_em, agora)
    padrao = db.obter_padrao(id_usuario, PADRAO_PERIODO_OBSERVADO)
    atual = None
    if padrao and padrao.get("confianca"):
        atual = {"valor": padrao["valor"], "confianca": padrao["confianca"], "evidencias": padrao.get("evidencias")}

    acao, estado = decidir_atualizacao(atual, novo)
    padroes_novos = {}
    if estado:
        padroes_novos[PADRAO_PERIODO_OBSERVADO] = estado
    resumo["periodo_observado"] = {"acao": acao, "estado": estado}

    # --- [POR-CATEGORIA] o mesmo aprendizado, separado por categoria (estudo, trabalho...): o horário em que a pessoa
    #     rende pode ser outro para cada tipo de tarefa. Só entra com evidência suficiente, com as mesmas regras do geral.
    metricas_categoria = {}
    amostras = {}
    por_categoria = {}
    for t in tarefas:
        if t.get("categoria") in CATEGORIAS_APRENDIDAS:
            por_categoria.setdefault(t["categoria"], []).append(t)
    resumo["por_categoria"] = {}
    # A publicação substitui todas as categorias próprias, inclusive as ausentes.
    for cat, ts in por_categoria.items():
        chave = f"{PADRAO_PERIODO_OBSERVADO}:{cat}"
        concl_cat = [t["concluido_em"] for t in ts if t["status"] == "concluida" and t["concluido_em"]]
        padrao_cat = db.obter_padrao(id_usuario, chave)
        atual_cat = None
        if padrao_cat and padrao_cat.get("confianca"):
            atual_cat = {"valor": padrao_cat["valor"], "confianca": padrao_cat["confianca"], "evidencias": padrao_cat.get("evidencias")}
        acao_cat, estado_cat = decidir_atualizacao(atual_cat, calcular_periodo_observado(concl_cat, agora))
        if estado_cat:
            padroes_novos[chave] = estado_cat
        resumo["por_categoria"][cat] = {"acao": acao_cat, "estado": estado_cat}
        for periodo, d in calcular_taxas_por_periodo(ts, agora).items():
            metricas_categoria[f"taxa_conclusao_{cat}_{periodo}"] = d["taxa"]
            amostras[f"taxa_conclusao_{cat}_{periodo}"] = d["n"]

    # --- métricas (só com dados suficientes) ---
    metricas = {}
    for periodo, d in calcular_taxas_por_periodo(tarefas, agora).items():
        metricas[f"taxa_conclusao_{periodo}"] = d["taxa"]
        metricas[f"tarefas_encerradas_{periodo}"] = d["n"]
        amostras[f"taxa_conclusao_{periodo}"] = d["n"]
    atraso = calcular_atraso_mediano_min(tarefas, agora)
    if atraso:
        metricas["atraso_mediano_min"] = atraso[0]
        amostras["atraso_mediano_min"] = atraso[1]
    adiamento = calcular_taxa_adiamento(tarefas, eventos, agora)
    if adiamento:
        metricas["taxa_adiamento"] = adiamento[0]
        amostras["taxa_adiamento"] = adiamento[1]
    contagem = db.contar_resultados_recomendacoes(id_usuario, desde=corte, ate=agora)
    total_reacoes = sum(contagem.values())
    if total_reacoes >= MIN_RESULTADOS_ACEITACAO:
        metricas["taxa_aceitacao_recomendacoes"] = round(contagem.get("aceitou", 0) / total_reacoes, 4)
        amostras["taxa_aceitacao_recomendacoes"] = total_reacoes

    cronometrado = calcular_metricas_cronometro(tarefas, eventos, agora)   # [CRONOMETRO]
    if cronometrado:
        metricas.update(cronometrado)
    metricas.update(metricas_categoria)   # [POR-CATEGORIA]
    # Limite conservador: reavaliar diariamente ou antes da próxima mudança temporal.
    limites = [agora + timedelta(days=1)]
    for t in tarefas:
        for campo in ("concluido_em", "data_fim"):
            instante = t.get(campo)
            if instante:
                limites.extend(x if x > agora else agora + timedelta(microseconds=1)
                               for x in (instante, instante + timedelta(days=JANELA_RECENTE_DIAS)) if x >= agora)
    for e in eventos:
        instante = e["data_hora"]
        limites.extend(x if x > agora else agora + timedelta(microseconds=1)
                       for x in (instante, instante + timedelta(days=JANELA_RECENTE_DIAS)) if x >= agora)
    # Uma reação pode vencer antes das evidências de tarefas.
    validade_reacoes = db.proxima_expiracao_resultados(id_usuario, corte, agora, JANELA_RECENTE_DIAS)
    if validade_reacoes:
        limites.append(validade_reacoes)
    resumo["metricas"] = metricas
    resumo["amostras_metricas"] = amostras
    resumo["validade"] = min(limites).isoformat()
    db.publicar_aprendizado(id_usuario, padroes_novos, metricas, PERIODO_REF,
                            agora, min(limites), resumo)
    return resumo


# ============================================================
# [LOTE-1.1] ATUALIZAÇÃO AO LER
# ============================================================
INTERVALO_MIN_TENTATIVAS_S = 300      # no máximo uma tentativa de recálculo por pessoa a cada 5 minutos
_ultima_tentativa = {}
_trava_tentativas = threading.Lock()


def garantir_vigente(id_usuario, agora=None):
    """
    Para quem LÊ o aprendizado para decidir (sugerir horário, "o que fazer agora"): se não há um snapshot válido (nunca
    calculado, vencido ou legado), recalcula ANTES de ler. Sem isso, quem fica um dia sem concluir ou editar tarefas
    voltaria à preferência declarada sem que nada tivesse sido reavaliado.
    Com trava de frequência (uma falha não vira uma tempestade de recálculos) e sem nunca levantar erro: se não for
    possível verificar ou recalcular, a leitura segue (e, sem snapshot válido, o banco só devolve o declarado).
    Devolve True se recalculou.
    """
    agora = agora or datetime.now()
    try:
        if db.aprendizado_vigente(id_usuario, agora):
            return False
    except Exception:
        return False
    with _trava_tentativas:
        ultima = _ultima_tentativa.get(id_usuario)
        if ultima is not None and time.monotonic() - ultima < INTERVALO_MIN_TENTATIVAS_S:
            return False
        _ultima_tentativa[id_usuario] = time.monotonic()
    try:
        recalcular_aprendizado(id_usuario, agora)
        return True
    except Exception:
        log.exception("Falha ao atualizar o aprendizado vencido do usuário %s", id_usuario)
        return False


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
            "O horário do registro não comprova energia nem horário de execução."
        )
    if not metricas and not any(p["fonte"] == "observado" for p in padroes):
        saida["observacao"] = "Ainda não há histórico suficiente para padrões observados."
    return saida


if __name__ == "__main__":
    print(f"Aprendizado recalculado para {recalcular_todos()} usuário(s).")
