"""
NEOCORTEX — servicos.py

CAMADA ÚNICA DE REGRAS. A tela (app.py) e a IA (ai.py) chamam as MESMAS funções
para criar, editar, concluir e cancelar. Assim uma tarefa nunca é aceita por um
lado e recusada pelo outro, e todo evento alimenta o aprendizado da mesma forma.

O que cada serviço garante:
  - o id_usuario vem do chamador (sessão); nada aqui aceita id de outro usuário;
  - conflito de agenda é checado (agenda.conflitos_para) e só passa com confirmação;
  - o histórico (eventos, recomendações) é gravado pelo db.py, na mesma transação;
  - o aprendizado é recalculado depois, com agrupamento (ver _atualizar_aprendizado).

Retorno: sempre um dict.
  {'sucesso': True, ...dados...}
  {'sucesso': False, 'conflitos': [...]}                 -> pedir confirmação
  {'sucesso': False, 'erro': '...', 'nao_encontrada': True?}
Dados inválidos levantam ValueError com mensagem pronta para mostrar.
"""

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta

import agenda
import aprendizado
import db
import cronometro
import decisao

log = logging.getLogger("neocortex.servicos")

CATEGORIAS_VALIDAS = {"trabalho", "estudo", "hobby", "pessoal", "saude", "outro"}
TIPOS_COMPROMISSO = {"aula", "consulta", "reuniao", "evento", "outro"}
ORIGENS_VALIDAS = {"manual", "ia_sugestao", "chat_inicial"}
DURACAO_PADRAO_MIN = 60
MAX_TITULO = 200

_AUSENTE = object()   # "parâmetro não informado" (diferente de None = "limpar")


# ============================================================
# VALIDAÇÃO E CONVERSÃO
# ============================================================
def parse_datetime(valor):
    """'AAAA-MM-DDTHH:MM' (ou com espaço/segundos) ou datetime -> datetime sem segundos."""
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None, second=0, microsecond=0)
    try:
        return datetime.fromisoformat(str(valor).strip().replace(" ", "T")).replace(
            tzinfo=None, second=0, microsecond=0)
    except ValueError:
        raise ValueError(f"data/hora inválida: {valor!r}. Use o formato AAAA-MM-DDTHH:MM.")


def parse_hhmm(valor):
    """'9:5', '09:05', '09:05:00' -> '09:05'. ValueError se inválido."""
    minutos = agenda._hhmm_para_minutos(valor)
    if minutos is None or minutos >= 24 * 60:
        raise ValueError(f"horário inválido: {valor!r}. Use HH:MM.")
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _titulo_valido(titulo):
    titulo = str(titulo or "").strip()
    if not titulo:
        raise ValueError("titulo é obrigatório.")
    if len(titulo) > MAX_TITULO:
        raise ValueError(f"titulo muito longo (máximo {MAX_TITULO} caracteres).")
    return titulo


def _resolver_fim(inicio, data_fim):
    """(fim, duracao_assumida_min). Sem fim informado, assume DURACAO_PADRAO_MIN."""
    if data_fim:
        fim, assumida = parse_datetime(data_fim), None
    else:
        fim, assumida = inicio + timedelta(minutes=DURACAO_PADRAO_MIN), DURACAO_PADRAO_MIN
    if fim <= inicio:
        raise ValueError("data_fim precisa ser depois de data_inicio.")
    return fim, assumida


def _iso(momento):
    return momento.isoformat(timespec="minutes")


def _nao_encontrada():
    return {"sucesso": False, "erro": "Tarefa não encontrada.", "nao_encontrada": True}


def descrever_conflitos(conflitos):
    """Texto curto para mostrar ao usuário: 'Trabalho (08/10 09:00–18:00); ...'."""
    partes = []
    for c in conflitos:
        ini, fim = datetime.fromisoformat(c["inicio"]), datetime.fromisoformat(c["fim"])
        faixa = f"{ini:%d/%m %H:%M}–{fim:%H:%M}" if ini.date() == fim.date() else f"{ini:%d/%m %H:%M} → {fim:%d/%m %H:%M}"
        partes.append(f"{c['titulo']} ({faixa})")
    return "; ".join(partes)


# ============================================================
# APRENDIZADO: recalcula depois, e UMA vez por rajada de eventos
# ============================================================
def _atraso_aprendizado_s():
    try:
        return float(os.getenv("APRENDIZADO_ATRASO_S", "3"))
    except ValueError:
        return 3.0


_pendentes = set()
_ultimo_calculo = {}   # id_usuario -> time.monotonic() do último recálculo neste processo
_trava = threading.Lock()
IDADE_MAXIMA_APRENDIZADO_MIN = 10


def _atualizar_aprendizado(id_usuario):
    """
    Concluir 5 tarefas seguidas dispara UM recálculo, não cinco: o primeiro
    evento agenda a execução e os seguintes, dentro da espera, entram no mesmo
    cálculo (que lê o banco no momento em que roda). APRENDIZADO_ATRASO_S=0
    recalcula na hora (útil em testes).
    """
    atraso = _atraso_aprendizado_s()
    if atraso <= 0:
        _rodar_aprendizado(id_usuario)
        return
    with _trava:
        if id_usuario in _pendentes:
            return
        _pendentes.add(id_usuario)

    def _rodar():
        with _trava:
            _pendentes.discard(id_usuario)   # novos eventos durante o cálculo agendam outro
        _rodar_aprendizado(id_usuario)

    temporizador = threading.Timer(atraso, _rodar)
    temporizador.daemon = True
    temporizador.start()


def _rodar_aprendizado(id_usuario):
    aprendizado.apos_evento(id_usuario)   # nunca levanta: registra a falha no log
    with _trava:
        _ultimo_calculo[id_usuario] = time.monotonic()


def garantir_aprendizado_atualizado(id_usuario, agora=None):
    """
    Para quem LÊ o aprendizado (a IA, ao responder "como estou indo?"): recalcula
    só se há evento ainda na fila de espera, se nunca calculou neste processo ou se o
    último cálculo tem mais de IDADE_MAXIMA_APRENDIZADO_MIN minutos (o tempo também
    muda o resultado: recomendações vencem). Antes recalculava a cada pergunta.
    Retorna True se recalculou.
    """
    with _trava:
        ultimo = _ultimo_calculo.get(id_usuario)
        velho = ultimo is None or (time.monotonic() - ultimo) > IDADE_MAXIMA_APRENDIZADO_MIN * 60
        if id_usuario not in _pendentes and not velho:
            return False
    aprendizado.recalcular_aprendizado(id_usuario, agora)
    with _trava:
        _ultimo_calculo[id_usuario] = time.monotonic()
    return True


# ============================================================
# TAREFAS
# ============================================================
def criar_tarefa(id_usuario, titulo, data_inicio, data_fim=None, categoria=None, descricao=None,
                 origem="manual", confirmar_conflito=False, agora=None):
    titulo = _titulo_valido(titulo)
    inicio = parse_datetime(data_inicio)
    fim, duracao_assumida = _resolver_fim(inicio, data_fim)
    categoria = categoria if categoria in CATEGORIAS_VALIDAS else None
    origem = origem if origem in ORIGENS_VALIDAS else "manual"

    conflitos = agenda.conflitos_para(id_usuario, inicio, fim, categoria=categoria)
    if conflitos and not confirmar_conflito:
        return {"sucesso": False, "criada": False, "conflitos": conflitos,
                "acao": "Informe os conflitos ao usuário e pergunte se deve criar mesmo assim."}

    id_tarefa = db.criar_tarefa(id_usuario, titulo, _iso(inicio), _iso(fim),
                                descricao=descricao, categoria=categoria, origem=origem)
    try:
        decisao.vincular_sugestao_a_tarefa(id_usuario, id_tarefa, inicio, agora)
    except Exception:
        log.exception("Falha ao ligar sugestão à tarefa %s (a tarefa foi criada normalmente)", id_tarefa)

    saida = {"sucesso": True, "id_tarefa": id_tarefa, "titulo": titulo,
             "inicio": _iso(inicio), "fim": _iso(fim)}
    if duracao_assumida:
        saida["duracao_assumida_min"] = duracao_assumida
    if conflitos:
        saida["conflitos_ignorados_com_confirmacao"] = conflitos
    return saida


def conflitos_de_passos(id_usuario, passos):
    """
    [CONFLITO-PASSOS] Confere uma lista de passos ANTES de gravar qualquer um (cada passo: dict com titulo, inicio e fim, datetime).
    Devolve [{'indice', 'titulo', 'inicio', 'fim', 'conflitos': [{'tipo', 'titulo', 'inicio', 'fim'}]}], só dos passos que colidem.
    Além da agenda (agenda.conflitos_para), considera os choques ENTRE os próprios passos da lista, que a agenda ainda não conhece.
    """
    saida = []
    for i, p in enumerate(passos):
        achados = list(agenda.conflitos_para(id_usuario, p["inicio"], p["fim"]))
        for j, q in enumerate(passos):
            if j != i and p["inicio"] < q["fim"] and q["inicio"] < p["fim"]:
                achados.append({"tipo": "passo", "titulo": q["titulo"],
                                "inicio": q["inicio"].isoformat(timespec="minutes"), "fim": q["fim"].isoformat(timespec="minutes")})
        if achados:
            saida.append({"indice": i, "titulo": p["titulo"], "inicio": p["inicio"].isoformat(timespec="minutes"),
                          "fim": p["fim"].isoformat(timespec="minutes"), "conflitos": achados})
    return saida


def atualizar_tarefa(id_usuario, id_tarefa, titulo=None, categoria=_AUSENTE, data_inicio=None,
                     data_fim=None, confirmar_conflito=False):
    """
    Só mexe no que foi informado. Informando apenas data_inicio, a duração é
    mantida. Se o horário não mudou de fato, não checa conflito (editar só o
    título de uma tarefa já conflitante não pode ser bloqueado).
    """
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()

    campos = {}
    if titulo is not None and str(titulo).strip():
        campos["titulo"] = _titulo_valido(titulo)
    if categoria is not _AUSENTE:
        nova = categoria if categoria in CATEGORIAS_VALIDAS else None
        if nova != tarefa["categoria"]:
            campos["categoria"] = nova

    if data_inicio or data_fim:
        duracao = tarefa["data_fim"] - tarefa["data_inicio"]
        inicio = parse_datetime(data_inicio) if data_inicio else tarefa["data_inicio"]
        if data_fim:
            fim = parse_datetime(data_fim)
        elif data_inicio:
            fim = inicio + duracao
        else:
            fim = tarefa["data_fim"]
        if fim <= inicio:
            raise ValueError("o novo fim precisa ser depois do novo início.")
        if inicio != tarefa["data_inicio"] or fim != tarefa["data_fim"]:
            categoria_efetiva = campos["categoria"] if "categoria" in campos else tarefa["categoria"]
            conflitos = agenda.conflitos_para(
                id_usuario, inicio, fim, categoria=categoria_efetiva,
                ignorar_id_tarefa=tarefa["id_tarefa"],
            )
            if conflitos and not confirmar_conflito:
                return {"sucesso": False, "alterada": False, "conflitos": conflitos,
                        "acao": "Informe os conflitos ao usuário e pergunte se deve alterar mesmo assim."}
            campos["data_inicio"], campos["data_fim"] = _iso(inicio), _iso(fim)

    if not campos:
        return {"sucesso": False, "erro": "Nada para alterar foi informado.", "sem_mudanca": True}

    if db.atualizar_tarefa(tarefa["id_tarefa"], id_usuario, **campos) == 0:
        return _nao_encontrada()
    _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": campos.get("titulo", tarefa["titulo"]),
            "novo_inicio": campos.get("data_inicio"), "novo_fim": campos.get("data_fim")}


def hora_do_cronometro():
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
    return _transicao_do_cronometro(id_usuario, id_tarefa, "retomar")


def cancelar_tarefa(id_usuario, id_tarefa):
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] != "cancelada":
        db.cancelar_tarefa(tarefa["id_tarefa"], id_usuario)
        _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}


def excluir_tarefa(id_usuario, id_tarefa):
    """Apaga de vez (a tela usa; a IA só cancela, preservando o histórico)."""
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    db.deletar_tarefa(tarefa["id_tarefa"], id_usuario)
    _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}

def reativar_tarefa(id_usuario, id_tarefa):
    """Desfaz um cancelamento, voltando a tarefa para pendente."""
    tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
    if tarefa is None:
        return _nao_encontrada()
    if tarefa["status"] != "cancelada":
        return {"sucesso": False, "erro": "Essa tarefa não está cancelada."}
    db.atualizar_tarefa(tarefa["id_tarefa"], id_usuario, status="pendente")
    _atualizar_aprendizado(id_usuario)
    return {"sucesso": True, "id_tarefa": tarefa["id_tarefa"], "titulo": tarefa["titulo"]}


# ============================================================
# COMPROMISSOS
# ============================================================
def criar_compromisso(id_usuario, titulo, data_inicio, data_fim=None, tipo="outro", local=None,
                      confirmar_conflito=False):
    titulo = _titulo_valido(titulo)
    inicio = parse_datetime(data_inicio)
    fim, duracao_assumida = _resolver_fim(inicio, data_fim)
    tipo = str(tipo or "outro").strip().lower()
    if tipo not in TIPOS_COMPROMISSO:
        tipo = "outro"
    local = str(local).strip() if local else None

    conflitos = agenda.conflitos_para(id_usuario, inicio, fim)
    if conflitos and not confirmar_conflito:
        return {"sucesso": False, "criado": False, "conflitos": conflitos,
                "acao": "Informe os conflitos ao usuário e pergunte se deve criar mesmo assim."}

    id_compromisso = db.criar_compromisso(id_usuario, titulo, _iso(inicio), _iso(fim), tipo=tipo, local=local)
    saida = {"sucesso": True, "id_compromisso": id_compromisso, "titulo": titulo,
             "inicio": _iso(inicio), "fim": _iso(fim), "tipo": tipo, "local": local,
             "duracao_assumida_min": duracao_assumida}
    if conflitos:
        saida["conflitos_ignorados_com_confirmacao"] = conflitos
    return saida


# ============================================================
# ROTINA FIXA
# ============================================================
def _virou_a_noite(inicio_min, fim_min):
    """Turno que atravessa a meia-noite (ex.: 22:00–06:00). O agenda.py já sabe expandi-lo."""
    return fim_min < inicio_min and inicio_min >= 18 * 60 and fim_min <= 12 * 60


def configurar_rotina(id_usuario, descricao, hora_inicio, hora_fim, dias_semana):
    """
    Cria ou atualiza uma atividade da rotina fixa nos dias informados. Mesma
    descrição (ignorando acento, caixa e pontuação) no mesmo dia = atualiza o
    horário em vez de duplicar. 'Estudo' e 'Estudo inglês' são atividades distintas.
    Aceita turno que vira a noite (início >= 18:00 e fim <= 12:00).
    """
    descricao = str(descricao or "").strip()
    if not descricao:
        raise ValueError("descricao é obrigatória para configurar uma rotina.")
    inicio, fim = parse_hhmm(hora_inicio), parse_hhmm(hora_fim)
    inicio_min, fim_min = agenda._hhmm_para_minutos(inicio), agenda._hhmm_para_minutos(fim)
    if fim_min == inicio_min or (fim_min < inicio_min and not _virou_a_noite(inicio_min, fim_min)):
        raise ValueError("hora_fim precisa ser depois de hora_inicio na rotina fixa.")

    if isinstance(dias_semana, str):
        dias_semana = [dias_semana]
    dias = []
    for dia in dias_semana or []:
        dia_norm = agenda.normalizar_texto(dia).strip()
        if dia_norm in agenda.DIAS_SEMANA and dia_norm not in dias:
            dias.append(dia_norm)
    if not dias:
        raise ValueError("dias_semana precisa conter ao menos um dia válido.")

    chave = re.sub(r"[^a-z0-9]", "", agenda.normalizar_texto(descricao))
    atualizadas = criadas = 0
    ids = []
    for dia in dias:
        iguais = [r for r in db.listar_rotina(id_usuario, dia_semana=dia)
                  if re.sub(r"[^a-z0-9]", "", agenda.normalizar_texto(r.get("descricao"))) == chave]
        if iguais:
            for r in iguais:
                db.atualizar_rotina(r["id_rotina"], id_usuario, descricao=descricao,
                                    hora_inicio=inicio, hora_fim=fim)
                ids.append(r["id_rotina"])
                atualizadas += 1
        else:
            ids.append(db.adicionar_rotina(id_usuario, dia, descricao, inicio, fim))
            criadas += 1

    return {"sucesso": True, "descricao": descricao, "hora_inicio": inicio, "hora_fim": fim,
            "dias_semana": dias, "dias_atualizados": atualizadas, "dias_criados": criadas,
            "ids_rotina": ids}
