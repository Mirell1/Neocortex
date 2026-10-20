"""
NEOCORTEX — ml_preparacao.py

PREPARAÇÃO para Machine Learning. Nada aqui treina modelo em produção.

Estado real do projeto (honesto):
  - O Gemini é um LLM: redige respostas e chama ferramentas. NÃO é o "ML do
    projeto".
  - decisao.py / aprendizado.py usam REGRAS e ESTATÍSTICA com limiares
    (aprendizado paramétrico). Isso funciona desde o primeiro usuário.
  - Machine Learning preditivo só passa a valer a pena com volume. Este módulo
    prepara o terreno e dá o critério objetivo de quando ligar.

PRIMEIRO MODELO QUE FAZ SENTIDO:
  Probabilidade de CONCLUSÃO de uma tarefa dado como ela foi agendada
  (target = concluida). Serve a duas decisões reais do produto: escolher
  o horário a sugerir e avisar "essa tarefa tem risco de ficar para depois".

BASELINE (o modelo precisa vencê-lo):
  taxa histórica de conclusão da própria pessoa naquele período do dia
  (com suavização), e a taxa global quando a pessoa tem pouco histórico.
  É exatamente a regra que o sistema já usa hoje.

REGRA DE USO:
  O modelo só é aprovado se reduzir o log-loss em pelo menos 2% sobre o
  baseline em testes POSTERIORES no tempo (nunca embaralhados: não se prevê
  o passado com o futuro) e se esse ganho se repetir: a avaliação é feita em
  4 janelas de tempo consecutivas (janela expansível: treina com tudo o que é
  mais antigo que a janela, testa nela) e o modelo precisa ganhar em pelo
  menos 3 de cada 4. Uma única divisão treino/teste dava um resultado
  instável: com os mesmos dados simulados, a decisão mudava de um sorteio
  para outro. Caso contrário, "manter_regras".
  Em produção, o fallback é sempre a regra determinística.

HISTÓRICO DA PRÓPRIA PESSOA (variáveis taxa_pessoa_*_previa e n_tarefas_previas):
  para cada tarefa, o que se SABIA da pessoa quando ela foi agendada (só conta
  tarefa já encerrada naquele momento). Sem isso o modelo não conhecia a pessoa
  e perdia da regra; com isso ele a conhece e só precisa acrescentar o que vale
  para qualquer pessoa (categoria, dia da semana, duração, antecedência).

O BASELINE É ATUALIZADO A CADA TAREFA, como a regra do produto (que recalcula
  o aprendizado a cada uso): é uma comparação justa, e não contra uma regra
  congelada no dia do treino.

FEATURES: só o que se sabe NO MOMENTO do agendamento. 'n_adiamentos' fica
no dataset para análise, mas NÃO entra no modelo: só é conhecido depois,
seria vazamento de informação (data leakage).
"""

from datetime import datetime

import numpy as np
import pandas as pd

import db
from periodos import normalizar_periodo, periodo_da_hora

TARGET = "concluida"
FEATURES_CATEGORICAS = ["periodo_agendado", "categoria", "dia_semana", "energia_declarada"]
FEATURES_NUMERICAS = ["hora_inicio", "duracao_planejada_min", "antecedencia_min", "no_pico_declarado"]

MIN_TAREFAS_ENCERRADAS = 300
MIN_USUARIOS = 20
MIN_POR_CLASSE = 50
GANHO_MINIMO_LOGLOSS = 0.02
# [ML-JANELAS] avaliação em janelas de tempo e histórico prévio da pessoa
FRACAO_TREINO = 0.8                 # (mantida por compatibilidade; a avaliação agora é feita em janelas de tempo)
FEATURES_HISTORICO = ["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"]
N_JANELAS = 4                       # a avaliação se repete em 4 janelas de tempo consecutivas
INICIO_TESTE = 0.4                  # a 1ª janela de teste começa depois dos 40% mais antigos dos dados
FRACAO_JANELAS_POSITIVAS = 0.75     # o modelo precisa ganhar em pelo menos 3 de cada 4 janelas


def extrair_features(agora=None, id_usuario=None):
    """
    Dataset de tarefas ENCERRADAS (concluídas, ou abertas com prazo vencido;
    canceladas ficam de fora) — SOMENTE LEITURA, uma linha por tarefa.
    """
    agora = agora or datetime.now()
    sql = """
        SELECT t.id_tarefa, t.id_usuario, t.categoria, t.data_inicio, t.data_fim,
               t.criado_em, t.status, t.concluido_em,
               (SELECT p.valor FROM padroes_comportamentais p
                 WHERE p.id_usuario = t.id_usuario AND p.tipo_padrao = 'energia'
                 LIMIT 1) AS energia_declarada,
               (SELECT COUNT(*) FROM eventos_execucao e
                 WHERE e.id_tarefa = t.id_tarefa AND e.tipo_evento = 'adiou') AS n_adiamentos
        FROM tarefas t
        WHERE t.status <> 'cancelada'
          AND (t.status = 'concluida'
               OR (t.status IN ('pendente', 'em_andamento') AND t.data_fim < %s))
    """
    parametros = [agora]
    if id_usuario is not None:
        sql += " AND t.id_usuario = %s"
        parametros.append(id_usuario)
    with db.conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, parametros)
            linhas = cur.fetchall()

    colunas = ["id_tarefa", "id_usuario", "categoria", "data_inicio", "data_fim", "criado_em",
               "status", "concluido_em", "energia_declarada", "n_adiamentos"]
    df = pd.DataFrame([dict(l) for l in linhas], columns=colunas)
    if df.empty:
        return df.assign(**{TARGET: pd.Series(dtype=bool)})

    df["data_inicio"] = pd.to_datetime(df["data_inicio"])
    df["data_fim"] = pd.to_datetime(df["data_fim"])
    df["criado_em"] = pd.to_datetime(df["criado_em"])
    df["concluido_em"] = pd.to_datetime(df["concluido_em"])
    df[TARGET] = df["status"] == "concluida"
    df["hora_inicio"] = df["data_inicio"].dt.hour
    df["dia_semana"] = df["data_inicio"].dt.dayofweek
    df["periodo_agendado"] = df["hora_inicio"].map(periodo_da_hora)
    df["duracao_planejada_min"] = (df["data_fim"] - df["data_inicio"]).dt.total_seconds() / 60
    df["antecedencia_min"] = (df["data_inicio"] - df["criado_em"]).dt.total_seconds() / 60
    df["categoria"] = df["categoria"].fillna("sem_categoria")
    # "Manhã" (cadastro antigo) e "manha" são a mesma coisa; "nao_sei"/ausente = desconhecida
    df["energia_declarada"] = df["energia_declarada"].map(lambda v: normalizar_periodo(v) or "desconhecida")
    df["no_pico_declarado"] = (df["periodo_agendado"] == df["energia_declarada"]).astype(int)
    df["atraso_min"] = (df["concluido_em"] - df["data_fim"]).dt.total_seconds() / 60
    return df


def prontidao_ml(df):
    """Há dados suficientes para sequer tentar treinar? Diz exatamente o que falta."""
    n = len(df)
    n_usuarios = int(df["id_usuario"].nunique()) if n else 0
    n_sim = int(df[TARGET].sum()) if n else 0
    n_nao = n - n_sim
    faltando = []
    if n < MIN_TAREFAS_ENCERRADAS:
        faltando.append(f"tarefas encerradas: {n}/{MIN_TAREFAS_ENCERRADAS}")
    if n_usuarios < MIN_USUARIOS:
        faltando.append(f"usuários com histórico: {n_usuarios}/{MIN_USUARIOS}")
    if min(n_sim, n_nao) < MIN_POR_CLASSE:
        faltando.append(f"exemplos da classe minoritária: {min(n_sim, n_nao)}/{MIN_POR_CLASSE}")
    return {"pronto": not faltando, "tarefas_encerradas": n, "usuarios": n_usuarios,
            "concluidas": n_sim, "nao_concluidas": n_nao, "faltando": faltando}


def _log_loss(y, p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _brier(y, p):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def previsao_baseline(treino, teste, suavizacao=5):
    """
    Baseline = a regra que o sistema já usa: taxa de conclusão da pessoa
    naquele período, suavizada em direção à taxa global.
    """
    global_taxa = float(treino[TARGET].mean())
    grupos = treino.groupby(["id_usuario", "periodo_agendado"])[TARGET].agg(["sum", "count"])
    probs = []
    for _, linha in teste.iterrows():
        chave = (linha["id_usuario"], linha["periodo_agendado"])
        if chave in grupos.index:
            s, c = grupos.loc[chave]
            probs.append((s + suavizacao * global_taxa) / (c + suavizacao))
        else:
            probs.append(global_taxa)
    return np.array(probs)


def historico_previo(df, suavizacao=5):
    """
    Para cada tarefa: o que se SABIA da própria pessoa quando ela foi agendada (criado_em), sem usar o futuro.
    Uma tarefa anterior só conta se já estava encerrada naquele momento: concluída antes dele, ou com o prazo já vencido
    (uma tarefa concluída DEPOIS do momento conta como não concluída: era o que o sistema via então).
    Devolve o dataset ordenado por data de início, com as colunas de FEATURES_HISTORICO. A taxa 'pessoa x período' é a
    regra do produto: taxa da pessoa naquele período, suavizada em direção à taxa geral dela (que parte de 50%).
    """
    df = df.sort_values("data_inicio").reset_index(drop=True)
    taxa_periodo, taxa_geral, n_previas = np.zeros(len(df)), np.zeros(len(df)), np.zeros(len(df))
    for _, indices in df.groupby("id_usuario").groups.items():
        sub = df.loc[indices]
        fim, concluido, periodo, criado = (sub["data_fim"].values, sub["concluido_em"].values,
                                           sub["periodo_agendado"].values, sub["criado_em"].values)
        for k, i in enumerate(indices):
            momento = criado[k]
            deu_certo = concluido < momento                  # NaT < momento é falso: quem nunca concluiu não conta como concluída
            encerrada = deu_certo | (fim < momento)
            n = int(encerrada.sum())
            geral = (deu_certo[encerrada].sum() + suavizacao * 0.5) / (n + suavizacao)
            mesmo_periodo = encerrada & (periodo == periodo[k])
            taxa_geral[i], n_previas[i] = geral, n
            taxa_periodo[i] = (deu_certo[mesmo_periodo].sum() + suavizacao * geral) / (mesmo_periodo.sum() + suavizacao)
    return df.assign(taxa_pessoa_periodo_previa=taxa_periodo, taxa_pessoa_geral_previa=taxa_geral, n_tarefas_previas=n_previas)


def _bordas_das_janelas(n, n_janelas=N_JANELAS):
    """Posições (por ordem de data) onde cada janela de teste começa e termina."""
    return np.linspace(int(n * INICIO_TESTE), n, n_janelas + 1).astype(int)


def _avaliar_em_janelas(df, numericas, n_janelas):
    """Treina e prevê em cada janela de tempo (janela expansível). df precisa vir de historico_previo()."""
    from sklearn.linear_model import LogisticRegression
    X = pd.get_dummies(df[FEATURES_CATEGORICAS + numericas], columns=FEATURES_CATEGORICAS, dtype=float)
    y = df[TARGET].astype(int).values
    baseline = df["taxa_pessoa_periodo_previa"].values            # a regra do produto, atualizada a cada tarefa
    bordas, janelas = _bordas_das_janelas(len(df), n_janelas), []
    for a, b in zip(bordas[:-1], bordas[1:]):
        if len(set(y[:a])) < 2 or len(set(y[a:b])) < 2:
            continue                                               # janela sem as duas classes não mede nada
        X_treino, X_teste = X.iloc[:a], X.iloc[a:b]
        media, desvio = X_treino.mean(), X_treino.std().replace(0, 1)
        modelo = LogisticRegression(max_iter=1000).fit((X_treino - media) / desvio, y[:a])
        janelas.append({"treino": int(a), "teste": int(b - a), "y": y[a:b], "p_baseline": baseline[a:b],
                        "p_modelo": modelo.predict_proba((X_teste - media) / desvio)[:, 1],
                        "inicio_teste": str(df["data_inicio"].iloc[a]), "fim_teste": str(df["data_inicio"].iloc[b - 1])})
    return janelas


def _ganho_da_janela(j):
    ll_base, ll_modelo = _log_loss(j["y"], j["p_baseline"]), _log_loss(j["y"], j["p_modelo"])
    return (ll_base - ll_modelo) / ll_base if ll_base else 0.0


def comparar_com_baseline(df, usar_historico=True, n_janelas=N_JANELAS):
    """
    Treina um modelo (regressão logística) SOMENTE se houver dados suficientes e o compara com o baseline (a regra do
    produto, atualizada a cada tarefa) em janelas de tempo consecutivas. Não persiste e não coloca nada em produção:
    devolve o relatório e a decisão.
    """
    prontidao = prontidao_ml(df)
    if not prontidao["pronto"]:
        return {"status": "dados_insuficientes", "decisao": "manter_regras", **prontidao}

    try:
        import sklearn  # noqa: F401
    except ImportError:
        return {"status": "sklearn_indisponivel", "decisao": "manter_regras",
                "detalhe": "Instale scikit-learn para avaliar o modelo (não é dependência do app).", **prontidao}

    df = historico_previo(df)
    numericas = FEATURES_NUMERICAS + (FEATURES_HISTORICO if usar_historico else [])
    janelas = _avaliar_em_janelas(df, numericas, n_janelas)
    if not janelas:
        return {"status": "dados_insuficientes", "decisao": "manter_regras",
                "detalhe": "nenhuma janela de teste com as duas classes", **prontidao}

    ganhos = [_ganho_da_janela(j) for j in janelas]
    ganho_medio = float(np.mean(ganhos))
    positivas = int(sum(g > 0 for g in ganhos))
    aprovado = ganho_medio >= GANHO_MINIMO_LOGLOSS and positivas >= int(np.ceil(FRACAO_JANELAS_POSITIVAS * len(janelas)))
    y = np.concatenate([j["y"] for j in janelas])
    p_base, p_modelo = np.concatenate([j["p_baseline"] for j in janelas]), np.concatenate([j["p_modelo"] for j in janelas])
    ultima = janelas[-1]
    resultado = {
        "status": "avaliado",
        "versao": f"logreg-{datetime.now():%Y%m%d%H%M}",
        "metodo": "janelas de tempo (treina no passado, testa na janela seguinte)",
        "baseline": "taxa da pessoa no período, atualizada a cada tarefa (a regra do produto)",
        "periodo_treino": [str(df["data_inicio"].min()), str(df["data_inicio"].iloc[ultima["treino"] - 1])],
        "n_treino": ultima["treino"], "n_teste": int(sum(j["teste"] for j in janelas)),
        "n_janelas": len(janelas), "janelas_positivas": positivas,
        "janelas": [{"treino": j["treino"], "teste": j["teste"], "de": j["inicio_teste"], "ate": j["fim_teste"],
                     "log_loss_baseline": round(_log_loss(j["y"], j["p_baseline"]), 4),
                     "log_loss_modelo": round(_log_loss(j["y"], j["p_modelo"]), 4), "ganho": round(g, 4)}
                    for j, g in zip(janelas, ganhos)],
        "features": FEATURES_CATEGORICAS + numericas,
        "metricas": {
            "baseline": {"log_loss": round(_log_loss(y, p_base), 4), "brier": round(_brier(y, p_base), 4)},
            "modelo": {"log_loss": round(_log_loss(y, p_modelo), 4), "brier": round(_brier(y, p_modelo), 4)},
        },
        "ganho_relativo_log_loss": round(ganho_medio, 4),
        "aprovado": aprovado,
        "decisao": "usar_modelo" if aprovado else "manter_regras",
        "fallback": "regra determinística (baseline)",
        **prontidao,
    }
    if usar_historico:                                  # só para mostrar quanto o histórico da pessoa contribui
        sem = _avaliar_em_janelas(df, FEATURES_NUMERICAS, n_janelas)
        if sem:
            g_sem = [_ganho_da_janela(j) for j in sem]
            resultado["comparacao_sem_historico"] = {"ganho_medio": round(float(np.mean(g_sem)), 4),
                                                     "janelas_positivas": int(sum(g > 0 for g in g_sem)), "n_janelas": len(sem)}
    return resultado


def _resumo_legivel(prontidao, comparacao):
    linhas = ["PRONTIDÃO PARA ML (somente leitura)",
              f"  tarefas encerradas ........ {prontidao['tarefas_encerradas']} (mínimo {MIN_TAREFAS_ENCERRADAS})",
              f"  usuários com histórico .... {prontidao['usuarios']} (mínimo {MIN_USUARIOS})",
              f"  concluídas / não .......... {prontidao['concluidas']} / {prontidao['nao_concluidas']} (mínimo {MIN_POR_CLASSE} da classe minoritária)"]
    if comparacao["status"] != "avaliado":
        motivo = "; ".join(comparacao.get("faltando") or []) or comparacao.get("detalhe", comparacao["status"])
        linhas += ["", "AVALIAÇÃO DO MODELO: ainda não é possível.", f"  falta: {motivo}", f"  decisão: {comparacao['decisao']} (o sistema segue com as regras)"]
        return "\n".join(linhas)
    linhas += ["", f"AVALIAÇÃO DO MODELO em {comparacao['n_janelas']} janelas de tempo (treina no passado, testa na janela seguinte)"]
    for k, j in enumerate(comparacao["janelas"], 1):
        linhas.append(f"  janela {k}: treino {j['treino']:>5} | teste {j['teste']:>4} | log-loss regra {j['log_loss_baseline']:.4f} x modelo {j['log_loss_modelo']:.4f} | ganho {j['ganho']:+.1%}")
    linhas.append(f"  ganho médio: {comparacao['ganho_relativo_log_loss']:+.1%} (exigido: +{GANHO_MINIMO_LOGLOSS:.0%}) | janelas com ganho: {comparacao['janelas_positivas']}/{comparacao['n_janelas']}")
    if "comparacao_sem_historico" in comparacao:
        s = comparacao["comparacao_sem_historico"]
        linhas.append(f"  sem o histórico da pessoa o ganho médio seria {s['ganho_medio']:+.1%} ({s['janelas_positivas']}/{s['n_janelas']} janelas)")
    linhas.append(f"  decisão: {comparacao['decisao'].upper()}")
    return "\n".join(linhas)


if __name__ == "__main__":
    # Relatório de prontidão e avaliação (somente leitura): python ml_preparacao.py
    dados = extrair_features()
    print(_resumo_legivel(prontidao_ml(dados), comparar_com_baseline(dados)))
