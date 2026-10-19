"""
NEOCORTEX - cronometro.py

Cronômetro OPCIONAL de execução de tarefas. São funções PURAS (sem banco): o estado e o tempo líquido saem só dos eventos que
o banco já registra para cada tarefa (iniciou, pausou, retomou, concluiu, desfez_conclusao, cancelou).

Ideia: usar o cronômetro é uma escolha. Quem usa ganha pontos e ajuda o NEOCORTEX a aprender o ritmo real (quando a pessoa
COMEÇA e quanto tempo LEVA de verdade), que o horário do clique em "concluir" não mostra. Quem não usa não perde nada.

Um "ciclo" começa em 'iniciou' e termina em 'concluiu'. Pausar e retomar só abrem e fecham trechos dentro do ciclo.
'desfez_conclusao' e 'cancelou' apagam o ciclo (a tarefa volta ao começo).
"""

from datetime import datetime

TIPOS_QUE_IMPORTAM = ("iniciou", "pausou", "retomou", "concluiu", "desfez_conclusao", "cancelou")
PONTOS_POR_TAREFA_CRONOMETRADA = 5     # incentivo: pontos a mais por tarefa concluída com o cronômetro
MIN_SEGUNDOS_BONUS = 180               # só vale se houve pelo menos 3 min de execução (evita clicar Começar e Concluir em seguida)
MIN_SEGUNDOS_APRENDER = 60             # abaixo de 1 min o tempo não diz nada sobre o ritmo da pessoa
MAX_HORAS_CICLO = 12                   # acima disso o cronômetro foi esquecido ligado: não entra no aprendizado


def _como_datetime(valor):
    if isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(str(valor))


def resumir(eventos, agora=None):
    """
    Estado do cronômetro de UMA tarefa, a partir dos seus eventos (em qualquer ordem).

    Devolve um dict:
      estado        'parado' (nunca iniciado, ou ciclo apagado) | 'rodando' | 'pausado' | 'concluido' (ciclo fechado)
      acumulado_s   segundos de execução LÍQUIDA (descontadas as pausas); se estiver rodando, inclui o trecho até 'agora'
      iniciou_em    quando o ciclo começou (None se parado)
      concluiu_em   quando o ciclo terminou (só em 'concluido')
      esquecido     True se está rodando há mais de MAX_HORAS_CICLO horas
    """
    agora = agora or datetime.now()
    validos = [e for e in eventos if e.get("tipo_evento") in TIPOS_QUE_IMPORTAM and e.get("data_hora") is not None]
    validos.sort(key=lambda e: (_como_datetime(e["data_hora"]), e.get("id_evento") or 0))

    aberto, rodando, acumulado, iniciou_em, concluiu_em = False, None, 0.0, None, None
    for e in validos:
        t, tipo = _como_datetime(e["data_hora"]), e["tipo_evento"]
        if tipo == "iniciou":
            if not aberto:                                   # começa um ciclo novo
                aberto, acumulado, iniciou_em, concluiu_em = True, 0.0, t, None
            if rodando is None:
                rodando = t
        elif tipo == "retomou":
            if aberto and rodando is None:
                rodando = t
        elif tipo == "pausou":
            if aberto and rodando is not None:
                acumulado += max(0.0, (t - rodando).total_seconds())
                rodando = None
        elif tipo == "concluiu":
            if aberto:
                if rodando is not None:
                    acumulado += max(0.0, (t - rodando).total_seconds())
                    rodando = None
                aberto, concluiu_em = False, t
        else:                                                # 'desfez_conclusao' e 'cancelou': a tarefa volta ao começo
            aberto, rodando, acumulado, iniciou_em, concluiu_em = False, None, 0.0, None, None

    if aberto:
        trecho = max(0.0, (agora - rodando).total_seconds()) if rodando is not None else 0.0
        return {"estado": "rodando" if rodando is not None else "pausado", "acumulado_s": acumulado + trecho,
                "iniciou_em": iniciou_em, "concluiu_em": None, "esquecido": trecho > MAX_HORAS_CICLO * 3600}
    if iniciou_em is not None and concluiu_em is not None:
        return {"estado": "concluido", "acumulado_s": acumulado, "iniciou_em": iniciou_em, "concluiu_em": concluiu_em, "esquecido": False}
    return {"estado": "parado", "acumulado_s": 0.0, "iniciou_em": None, "concluiu_em": None, "esquecido": False}


def ganha_bonus(resumo):
    """A tarefa foi concluída com o cronômetro e houve execução de verdade (pelo menos MIN_SEGUNDOS_BONUS)?"""
    return resumo["estado"] == "concluido" and resumo["acumulado_s"] >= MIN_SEGUNDOS_BONUS


def serve_para_aprender(resumo):
    """O ciclo fechado tem uma duração plausível (entre 1 min e MAX_HORAS_CICLO horas)?"""
    return resumo["estado"] == "concluido" and MIN_SEGUNDOS_APRENDER <= resumo["acumulado_s"] <= MAX_HORAS_CICLO * 3600


def rotulo_tempo(segundos):
    """'05:09' ou '1:02:09'."""
    s = int(max(0, segundos))
    h, resto = divmod(s, 3600)
    m, seg = divmod(resto, 60)
    return f"{h}:{m:02d}:{seg:02d}" if h else f"{m:02d}:{seg:02d}"
