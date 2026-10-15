"""
NEOCORTEX — agenda.py

FONTE ÚNICA DO CALENDÁRIO. A interface (calendário e /api/eventos), os serviços
(servicos.py) e a IA leem a agenda por aqui, então não existe "calendário da
tela" diferente do "calendário que a IA consulta".

Fontes combinadas:
  tarefas, compromissos, rotina_fixa (expandida por dia), restricoes e
  disponibilidades.

Tudo é calculado de forma determinística (sem LLM).

DESEMPENHO: cada operação carrega o intervalo UMA vez (5 consultas, não importa
quantos dias tenha) e depois trabalha em memória. Antes, cada dia refazia todas
as consultas.
"""

from datetime import datetime, time, timedelta

import db
from periodos import PERIODOS, normalizar_periodo, normalizar_texto, periodo_da_hora  # noqa: F401

DIAS_SEMANA = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

# Janela em que o sistema sugere horários (fora disso não se sugere nada).
INICIO_DIA = time(7, 0)
FIM_DIA = time(22, 0)
PASSO_MIN = 30

# Quando dois blocos cobrem o mesmo instante, este é o que "ocupa" o usuário.
# (compromisso e rotina são obrigações externas: pesam mais que uma tarefa que o próprio usuário marcou)
_PRIORIDADE_BLOCO = {"compromisso": 0, "rotina": 1, "restricao": 2, "indisponivel": 3, "tarefa": 4}


# ------------------------------------------------------------
# Utilidades de texto e hora
# ------------------------------------------------------------
# periodo_da_hora, normalizar_texto e normalizar_periodo vivem em periodos.py (regra única do projeto)
_normalizar = normalizar_texto  # nome antigo, mantido por compatibilidade


def _hhmm_para_minutos(valor):
    """'9:00', '09:00' ou '09:00:00' -> minutos desde 00:00. None se inválido."""
    try:
        partes = str(valor).strip().split(":")
        h, m = int(partes[0]), int(partes[1])
        if 0 <= h <= 24 and 0 <= m < 60:
            return h * 60 + m
    except (ValueError, IndexError):
        pass
    return None


def _inicio_do_dia(dia):
    """date ou datetime -> datetime às 00:00 desse dia."""
    return datetime.combine(dia.date() if isinstance(dia, datetime) else dia, time(0, 0))


def _sobrepoe(a_ini, a_fim, b_ini, b_fim):
    return a_ini < b_fim and a_fim > b_ini


# ------------------------------------------------------------
# Rotina fixa -> ocorrências em datas reais
# ------------------------------------------------------------
def expandir_rotina(linhas_rotina, inicio, fim):
    """
    Transforma a rotina semanal ('segunda 09:00-18:00') em ocorrências com
    data real que sobrepõem [inicio, fim). Turnos que viram a noite
    (22:00-06:00) são tratados: o fim cai no dia seguinte.
    """
    ocorrencias = []
    dia = inicio.date() - timedelta(days=1)  # um dia antes: pega turno que atravessa a meia-noite
    while _inicio_do_dia(dia) < fim:
        nome_dia = DIAS_SEMANA[dia.weekday()]
        for r in linhas_rotina:
            if r["dia_semana"] != nome_dia:
                continue
            ini_min = _hhmm_para_minutos(r["hora_inicio"])
            fim_min = _hhmm_para_minutos(r["hora_fim"])
            if ini_min is None or fim_min is None:
                continue
            ini = _inicio_do_dia(dia) + timedelta(minutes=ini_min)
            fi = _inicio_do_dia(dia) + timedelta(minutes=fim_min)
            if fi <= ini:
                fi += timedelta(days=1)
            if ini < fim and fi > inicio:
                ocorrencias.append({
                    "id_rotina": r["id_rotina"],
                    "descricao": r["descricao"],
                    "inicio": ini,
                    "fim": fi,
                })
        dia += timedelta(days=1)
    ocorrencias.sort(key=lambda o: o["inicio"])
    return ocorrencias


# ------------------------------------------------------------
# Leitura da agenda (usada pela interface, pelos serviços E pela IA)
# ------------------------------------------------------------
def carregar_agenda(id_usuario, inicio, fim):
    """
    Tudo que ocupa a agenda do usuário em [inicio, fim) — 3 consultas:
    {'tarefas': [...], 'compromissos': [...], 'rotina': [...]}
    Tarefas canceladas ficam de fora.
    """
    return {
        "tarefas": db.listar_tarefas_janela(id_usuario, inicio, fim),
        "compromissos": db.listar_compromissos_janela(id_usuario, inicio, fim),
        "rotina": expandir_rotina(db.listar_rotina(id_usuario), inicio, fim),
    }


def carregar_contexto(id_usuario, inicio, fim):
    """carregar_agenda + restrições + disponibilidades (5 consultas, uma vez só)."""
    contexto = carregar_agenda(id_usuario, inicio, fim)
    contexto["restricoes"] = db.listar_restricoes(id_usuario)
    contexto["disponibilidades"] = db.listar_disponibilidades(id_usuario)
    return contexto


# ------------------------------------------------------------
# Blocos ocupados (em memória, a partir de um contexto já carregado)
# ------------------------------------------------------------
def blocos_do_dia(contexto, dia, ignorar_id_tarefa=None):
    """
    Blocos que NÃO podem receber outra atividade no dia, ordenados:
    [{'tipo','titulo','inicio','fim', ...}]. Não consulta o banco.

    Tarefas concluídas não bloqueiam (o tempo já passou/foi usado).
    """
    inicio = _inicio_do_dia(dia)
    fim = inicio + timedelta(days=1)
    blocos = []

    for t in contexto["tarefas"]:
        if (t["status"] in ("pendente", "em_andamento") and t["id_tarefa"] != ignorar_id_tarefa
                and _sobrepoe(t["data_inicio"], t["data_fim"], inicio, fim)):
            blocos.append({"tipo": "tarefa", "titulo": t["titulo"], "categoria": t.get("categoria"),
                           "id": t["id_tarefa"], "inicio": t["data_inicio"], "fim": t["data_fim"]})
    for c in contexto["compromissos"]:
        if _sobrepoe(c["data_inicio"], c["data_fim"], inicio, fim):
            blocos.append({"tipo": "compromisso", "titulo": c["titulo"],
                           "id": c["id_compromisso"], "inicio": c["data_inicio"], "fim": c["data_fim"]})
    for r in contexto["rotina"]:
        if _sobrepoe(r["inicio"], r["fim"], inicio, fim):
            blocos.append({"tipo": "rotina", "titulo": r["descricao"],
                           "id": r["id_rotina"], "inicio": r["inicio"], "fim": r["fim"]})

    nome_dia = DIAS_SEMANA[inicio.weekday()]

    # restrições com horário definido
    for r in contexto.get("restricoes", []):
        if r.get("dia_semana") != nome_dia:
            continue
        ini_min = _hhmm_para_minutos(r.get("hora_inicio"))
        fim_min = _hhmm_para_minutos(r.get("hora_fim"))
        if ini_min is None or fim_min is None or fim_min <= ini_min:
            continue  # restrição sem horário não bloqueia faixa nenhuma
        blocos.append({"tipo": "restricao", "titulo": r["descricao"], "id": r["id_restricao"],
                       "inicio": inicio + timedelta(minutes=ini_min),
                       "fim": inicio + timedelta(minutes=fim_min)})

    # disponibilidades: 'indisponível' bloqueia; se houver faixas 'disponível', o resto do dia bloqueia
    livres = []
    for d in contexto.get("disponibilidades", []):
        if d["dia_semana"] != nome_dia:
            continue
        ini_min = _hhmm_para_minutos(d["hora_inicio"])
        fim_min = _hhmm_para_minutos(d["hora_fim"])
        if ini_min is None or fim_min is None or fim_min <= ini_min:
            continue
        faixa = (inicio + timedelta(minutes=ini_min), inicio + timedelta(minutes=fim_min))
        if d["disponivel"]:
            livres.append(faixa)
        else:
            blocos.append({"tipo": "indisponivel", "titulo": "indisponível", "id": d["id_disponibilidade"],
                           "inicio": faixa[0], "fim": faixa[1]})
    if livres:
        livres.sort()
        cursor = inicio
        for ini, fi in livres:
            if ini > cursor:
                blocos.append({"tipo": "indisponivel", "titulo": "fora da disponibilidade",
                               "inicio": cursor, "fim": ini})
            cursor = max(cursor, fi)
        if cursor < fim:
            blocos.append({"tipo": "indisponivel", "titulo": "fora da disponibilidade",
                           "inicio": cursor, "fim": fim})

    blocos.sort(key=lambda b: b["inicio"])
    return blocos


def blocos_ocupados(id_usuario, dia, agenda=None, ignorar_id_tarefa=None, contexto=None):
    """
    Blocos ocupados de UM dia. Se vários dias forem consultados em sequência,
    carregue o contexto uma vez (carregar_contexto) e passe em 'contexto'.
    'agenda' (dict com tarefas/compromissos/rotina) é aceito por compatibilidade.
    """
    if contexto is None:
        inicio = _inicio_do_dia(dia)
        fim = inicio + timedelta(days=1)
        contexto = carregar_contexto(id_usuario, inicio, fim)
        if agenda:
            contexto = {**contexto, **{k: agenda[k] for k in ("tarefas", "compromissos", "rotina") if k in agenda}}
    return blocos_do_dia(contexto, dia, ignorar_id_tarefa=ignorar_id_tarefa)


# ------------------------------------------------------------
# Conflitos e janelas livres
# ------------------------------------------------------------
def bloco_da_mesma_atividade(bloco, categoria):
    """
    Tarefa de 'trabalho' dentro do bloco de rotina 'Trabalho' não é conflito (é o
    próprio bloco); idem 'estudo'. Mesma regra para conflito E para "estou
    ocupado agora?", para que as duas respostas nunca se contradigam.
    """
    if not bloco or bloco.get("tipo") != "rotina":
        return False
    desc = normalizar_texto(bloco.get("titulo"))
    return (categoria == "trabalho" and desc.startswith("trabalho")) or \
           (categoria == "estudo" and desc.startswith("estudo"))


def conflitos_para(id_usuario, inicio, fim, categoria=None, ignorar_id_tarefa=None):
    """
    Blocos que colidem com [inicio, fim). Lista compacta, pronta para a IA:
    [{'tipo','titulo','inicio','fim'}]. Carrega o intervalo uma única vez.
    """
    primeiro_dia = inicio.date()
    ultimo_dia = (fim - timedelta(seconds=1)).date()
    contexto = carregar_contexto(
        id_usuario, _inicio_do_dia(primeiro_dia), _inicio_do_dia(ultimo_dia) + timedelta(days=1)
    )
    achados, vistos = [], set()
    dia = primeiro_dia
    while dia <= ultimo_dia:
        for b in blocos_do_dia(contexto, dia, ignorar_id_tarefa=ignorar_id_tarefa):
            if not _sobrepoe(inicio, fim, b["inicio"], b["fim"]):
                continue
            if bloco_da_mesma_atividade(b, categoria):
                continue
            chave = (b["tipo"], b.get("id"), b["titulo"], b["inicio"], b["fim"])
            if chave in vistos:   # turno que vira a noite aparece em dois dias
                continue
            vistos.add(chave)
            achados.append({
                "tipo": b["tipo"], "titulo": b["titulo"],
                "inicio": b["inicio"].isoformat(timespec="minutes"),
                "fim": b["fim"].isoformat(timespec="minutes"),
            })
        dia += timedelta(days=1)
    return achados


def janelas_livres(blocos, dia, apos=None):
    """
    Intervalos livres do dia [(inicio, fim)] dentro de INICIO_DIA–FIM_DIA,
    descontando os blocos ocupados e (se informado) tudo antes de 'apos'.
    """
    ini = datetime.combine(dia, INICIO_DIA)
    fim = datetime.combine(dia, FIM_DIA)
    if apos and apos > ini:
        ini = apos
    livres, cursor = [], ini
    for b in sorted(blocos, key=lambda x: x["inicio"]):
        if b["fim"] <= cursor:
            continue
        if b["inicio"] >= fim:
            break
        if b["inicio"] > cursor:
            livres.append((cursor, min(b["inicio"], fim)))
        cursor = max(cursor, b["fim"])
        if cursor >= fim:
            break
    if cursor < fim:
        livres.append((cursor, fim))
    return [(a, b) for a, b in livres if b > a]


def arredondar_para_cima(momento, passo_min=PASSO_MIN):
    """Próximo múltiplo de 'passo_min' (ex.: 14:07 -> 14:30)."""
    base = momento.replace(second=0, microsecond=0)
    resto = (base.hour * 60 + base.minute) % passo_min
    if resto == 0 and momento == base:
        return base
    return base + timedelta(minutes=passo_min - resto)


def situacao_agora(id_usuario, agora):
    """
    O que está acontecendo 'agora': bloco atual (se ocupado), próximo bloco
    e minutos livres até ele. Base de "o que eu tenho para fazer agora?".
    Uma única carga (ontem + hoje); ontem entra por causa do turno que
    atravessou a meia-noite e ainda está valendo.
    """
    hoje = agora.date()
    ontem = hoje - timedelta(days=1)
    contexto = carregar_contexto(id_usuario, _inicio_do_dia(ontem), _inicio_do_dia(hoje) + timedelta(days=1))

    blocos, vistos = [], set()
    for dia in (ontem, hoje):
        for b in blocos_do_dia(contexto, dia):
            chave = (b["tipo"], b.get("id"), b["titulo"], b["inicio"], b["fim"])
            if chave not in vistos:
                vistos.add(chave)
                blocos.append(b)
    blocos.sort(key=lambda b: b["inicio"])

    em_curso = [b for b in blocos if b["inicio"] <= agora < b["fim"]]
    atual = min(em_curso, key=lambda b: _PRIORIDADE_BLOCO.get(b["tipo"], 9)) if em_curso else None
    proximos = [b for b in blocos if b["inicio"] > agora]
    proximo = proximos[0] if proximos else None
    minutos_livres = None
    if atual is None and proximo is not None:
        minutos_livres = int((proximo["inicio"] - agora).total_seconds() // 60)
    return {"atual": atual, "proximo": proximo, "minutos_livres_ate_proximo": minutos_livres}


# ------------------------------------------------------------
# Visão por dia (calendário e /api/eventos usam a mesma função)
# ------------------------------------------------------------
def eventos_por_dia(agenda_carregada, primeiro_dia, fim_exclusivo):
    """
    Distribui o que veio de carregar_agenda() pelos dias de [primeiro_dia, fim_exclusivo).
    Retorna {date: [{'tipo','id','titulo','inicio','fim','status','categoria','cor'}]}.
    Item que atravessa vários dias aparece em cada um deles.
    """
    itens = []
    for t in agenda_carregada["tarefas"]:
        itens.append({"tipo": "tarefa", "id": t["id_tarefa"], "titulo": t["titulo"],
                      "inicio": t["data_inicio"], "fim": t["data_fim"], "status": t["status"],
                      "categoria": t.get("categoria"), "cor": t.get("cor")})
    for c in agenda_carregada["compromissos"]:
        itens.append({"tipo": "compromisso", "id": c["id_compromisso"], "titulo": c["titulo"],
                      "inicio": c["data_inicio"], "fim": c["data_fim"], "status": None,
                      "categoria": c.get("tipo"), "cor": None})
    for r in agenda_carregada["rotina"]:
        itens.append({"tipo": "rotina", "id": r["id_rotina"], "titulo": r["descricao"],
                      "inicio": r["inicio"], "fim": r["fim"], "status": None,
                      "categoria": None, "cor": None})

    por_dia = {}
    for item in itens:
        dia = max(item["inicio"].date(), primeiro_dia)
        ultimo = min((item["fim"] - timedelta(seconds=1)).date(), fim_exclusivo - timedelta(days=1))
        while dia <= ultimo:
            por_dia.setdefault(dia, []).append(item)
            dia += timedelta(days=1)
    for lista in por_dia.values():
        lista.sort(key=lambda i: i["inicio"])
    return por_dia
