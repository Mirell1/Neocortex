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
  baseline num conjunto de TESTE POSTERIOR no tempo (nunca embaralhado:
  não se prevê o passado com o futuro). Caso contrário, "manter_regras".
  Em produção, o fallback é sempre a regra determinística.

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
FRACAO_TREINO = 0.8


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


def comparar_com_baseline(df):
    """
    Treina um modelo (regressão logística) SOMENTE se houver dados suficientes
    e o compara com o baseline em um teste posterior no tempo. Não persiste e
    não coloca nada em produção: devolve o relatório e a decisão.
    """
    prontidao = prontidao_ml(df)
    if not prontidao["pronto"]:
        return {"status": "dados_insuficientes", "decisao": "manter_regras", **prontidao}

    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        return {"status": "sklearn_indisponivel", "decisao": "manter_regras",
                "detalhe": "Instale scikit-learn para avaliar o modelo (não é dependência do app).", **prontidao}

    df = df.sort_values("data_inicio").reset_index(drop=True)
    corte = int(len(df) * FRACAO_TREINO)
    treino, teste = df.iloc[:corte], df.iloc[corte:]
    if teste[TARGET].nunique() < 2 or treino[TARGET].nunique() < 2:
        return {"status": "dados_insuficientes", "decisao": "manter_regras",
                "detalhe": "treino/teste sem as duas classes", **prontidao}

    colunas = FEATURES_CATEGORICAS + FEATURES_NUMERICAS
    todos = pd.get_dummies(df[colunas], columns=FEATURES_CATEGORICAS, dtype=float)
    X_treino, X_teste = todos.iloc[:corte], todos.iloc[corte:]
    media, desvio = X_treino.mean(), X_treino.std().replace(0, 1)
    modelo = LogisticRegression(max_iter=1000)
    modelo.fit((X_treino - media) / desvio, treino[TARGET])
    p_modelo = modelo.predict_proba((X_teste - media) / desvio)[:, 1]
    p_base = previsao_baseline(treino, teste)

    ll_base, ll_modelo = _log_loss(teste[TARGET], p_base), _log_loss(teste[TARGET], p_modelo)
    ganho = (ll_base - ll_modelo) / ll_base if ll_base else 0.0
    aprovado = ganho >= GANHO_MINIMO_LOGLOSS
    return {
        "status": "avaliado",
        "versao": f"logreg-{datetime.now():%Y%m%d%H%M}",
        "periodo_treino": [str(treino["data_inicio"].min()), str(treino["data_inicio"].max())],
        "n_treino": len(treino), "n_teste": len(teste),
        "features": colunas,
        "metricas": {
            "baseline": {"log_loss": round(ll_base, 4), "brier": round(_brier(teste[TARGET], p_base), 4)},
            "modelo": {"log_loss": round(ll_modelo, 4), "brier": round(_brier(teste[TARGET], p_modelo), 4)},
        },
        "ganho_relativo_log_loss": round(ganho, 4),
        "aprovado": aprovado,
        "decisao": "usar_modelo" if aprovado else "manter_regras",
        "fallback": "regra determinística (baseline)",
        **prontidao,
    }


if __name__ == "__main__":
    # Relatório de prontidão (somente leitura): python ml_preparacao.py
    dados = extrair_features()
    print("Prontidão para ML:", prontidao_ml(dados))
    print("Comparação com o baseline:", comparar_com_baseline(dados))
