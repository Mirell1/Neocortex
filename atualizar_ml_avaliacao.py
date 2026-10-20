"""
NEOCORTEX - atualizar_ml_avaliacao.py

Melhora a AVALIAÇÃO de Machine Learning do ml_preparacao.py (offline: o app não importa esse módulo; nada muda em produção):

  1. HISTÓRICO DA PRÓPRIA PESSOA como variável do modelo (taxa de conclusão dela naquele período, taxa geral e quantas tarefas
     já encerradas), calculado só com o que se SABIA quando a tarefa foi agendada (sem usar o futuro). Sem isso, o modelo não
     conhecia a pessoa e perdia da regra; com isso ele só precisa acrescentar o que vale para qualquer pessoa.
  2. VALIDAÇÃO EM 4 JANELAS DE TEMPO em vez de uma única divisão treino/teste. Com uma divisão só, a decisão mudava de um
     sorteio de dados para outro. Agora o modelo precisa ganhar em média 2% ou mais E em pelo menos 3 das 4 janelas.
  3. BASELINE ATUALIZADO A CADA TAREFA, como a regra do produto (comparação justa, não contra uma regra congelada).
  4. Ao rodar  python ml_preparacao.py  o relatório sai legível, com a tabela por janela e o que falta quando os dados ainda
     não bastam.

Mexe só no ml_preparacao.py (as funções antigas extrair_features e prontidao_ml continuam iguais). TUDO OU NADA.
Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_ml_avaliacao.py            # só mostra
    python atualizar_ml_avaliacao.py --aplicar  # grava (cópia .bak; confere a sintaxe antes)

Rodar de novo é seguro.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ALVOS = (
    ('ml_preparacao.py', '[ML-JANELAS]', (
        ('regra de uso, histórico e baseline na documentação',
         r'''REGRA DE USO:
  O modelo só é aprovado se reduzir o log-loss em pelo menos 2% sobre o
  baseline num conjunto de TESTE POSTERIOR no tempo (nunca embaralhado:
  não se prevê o passado com o futuro). Caso contrário, "manter_regras".
  Em produção, o fallback é sempre a regra determinística.

FEATURES: só o que se sabe NO MOMENTO do agendamento. 'n_adiamentos' fica
no dataset para análise, mas NÃO entra no modelo: só é conhecido depois,
seria vazamento de informação (data leakage).
''',
         r'''REGRA DE USO:
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
'''),
        ('constantes das janelas e do histórico',
         r'''FRACAO_TREINO = 0.8
''',
         r'''# [ML-JANELAS] avaliação em janelas de tempo e histórico prévio da pessoa
FRACAO_TREINO = 0.8                 # (mantida por compatibilidade; a avaliação agora é feita em janelas de tempo)
FEATURES_HISTORICO = ["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"]
N_JANELAS = 4                       # a avaliação se repete em 4 janelas de tempo consecutivas
INICIO_TESTE = 0.4                  # a 1ª janela de teste começa depois dos 40% mais antigos dos dados
FRACAO_JANELAS_POSITIVAS = 0.75     # o modelo precisa ganhar em pelo menos 3 de cada 4 janelas
'''),
        ('histórico prévio, janelas de tempo e avaliação',
         r'''def comparar_com_baseline(df):
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
    }''',
         r'''def historico_previo(df, suavizacao=5):
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
    return resultado'''),
        ('relatório legível ao rodar o módulo',
         r'''if __name__ == "__main__":
    # Relatório de prontidão (somente leitura): python ml_preparacao.py
    dados = extrair_features()
    print("Prontidão para ML:", prontidao_ml(dados))
    print("Comparação com o baseline:", comparar_com_baseline(dados))
''',
         r'''def _resumo_legivel(prontidao, comparacao):
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
'''),
    )),
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
    ap = argparse.ArgumentParser(description="Melhora a avaliação de ML do ml_preparacao.py.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
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
        print("\nNada foi alterado. Para aplicar:  python atualizar_ml_avaliacao.py --aplicar")
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
