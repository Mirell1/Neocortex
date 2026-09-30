"""
NEOCORTEX - Analise: energia declarada x comportamento observado

Compara o periodo do dia em que cada pessoa DISSE que rende mais
(padroes_comportamentais, tipo_padrao = 'energia') com o periodo em que
ela de fato CONCLUI tarefas (tarefas.concluido_em).

Principios:
- SOMENTE LEITURA: nao escreve nada no banco.
- Saida AGREGADA: nunca imprime nome, e-mail nem texto livre.
- Honesta com amostra pequena: abaixo dos minimos, mostra so contagens.

Uso (venv ativa, dentro da pasta do projeto):
    python analise_energia.py --demo    # dados simulados, so pra validar o pipeline
    python analise_energia.py           # dados reais do banco
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------
# PARAMETROS (ajuste aqui, nao no meio do codigo)
# ------------------------------------------------------------
PERIODOS = ["manha", "tarde", "noite"]

MIN_CONCLUSOES_USUARIO = 5       # abaixo disso, o "periodo observado" da pessoa nao e confiavel
PARTICIPACAO_MIN_DOMINANTE = 0.5 # o periodo dominante precisa ter >= 50% das conclusoes
MIN_USUARIOS_RELATORIO = 5       # abaixo disso, nao reportamos percentuais (so contagens)
MIN_TAREFAS_GRUPO = 30           # minimo de tarefas em cada grupo (no pico / fora do pico)
JANELA_LOTE_MIN = 10             # conclusoes a menos de N min uma da outra = "lote"

PASTA_SAIDA = Path("analise_saida")


# ------------------------------------------------------------
# FUNCOES AUXILIARES
# ------------------------------------------------------------
def periodo_da_hora(hora):
    """manha 05-11h, tarde 12-17h, noite 18h ate 04h."""
    if 5 <= hora < 12:
        return "manha"
    if 12 <= hora < 18:
        return "tarde"
    return "noite"


def normalizar_energia(valor):
    """Aceita o formato novo ('manha') e o antigo do cadastro ('Manhã')."""
    v = str(valor).strip().lower().replace("ã", "a")
    return v if v in {"manha", "tarde", "noite", "nao_sei"} else np.nan


def intervalo_wilson(sucessos, total, z=1.96):
    """Intervalo de confianca de 95% pra uma proporcao (funciona bem com amostra pequena)."""
    if total == 0:
        return (np.nan, np.nan)
    p = sucessos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margem = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominador
    return (centro - margem, centro + margem)


def formatar_taxa(sucessos, total):
    if total == 0:
        return "sem dados"
    baixo, alto = intervalo_wilson(sucessos, total)
    return f"{sucessos / total:.0%} ({sucessos}/{total}; IC95% {baixo:.0%} a {alto:.0%})"


def titulo(texto):
    print("\n" + texto)
    print("-" * len(texto))


# ------------------------------------------------------------
# CARGA DOS DADOS
# ------------------------------------------------------------
def carregar_do_banco():
    import db  # importa aqui pra o modo --demo funcionar sem banco

    with db.conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_usuario, valor AS energia_declarada
                FROM padroes_comportamentais
                WHERE tipo_padrao = 'energia'
                """
            )
            energia = pd.DataFrame(cur.fetchall(), columns=["id_usuario", "energia_declarada"])

            cur.execute(
                """
                SELECT id_tarefa, id_usuario, status, categoria,
                       data_inicio, data_fim, concluido_em
                FROM tarefas
                WHERE status <> 'cancelada'
                """
            )
            tarefas = pd.DataFrame(
                cur.fetchall(),
                columns=["id_tarefa", "id_usuario", "status", "categoria",
                         "data_inicio", "data_fim", "concluido_em"],
            )
    return energia, tarefas


def gerar_dados_simulados(n_usuarios=40, concordancia=0.6, seed=42):
    """Dados FICTICIOS, so pra validar o pipeline antes de existir uso real."""
    rng = np.random.default_rng(seed)
    faixa = {"manha": (6, 12), "tarde": (12, 18), "noite": (18, 23)}
    hoje = pd.Timestamp.now().normalize()

    energia, tarefas, id_tarefa = [], [], 1
    for uid in range(1, n_usuarios + 1):
        declarado = str(rng.choice(PERIODOS))
        # com probabilidade 'concordancia', a pessoa realmente rende no periodo declarado
        real = declarado if rng.random() < concordancia else str(rng.choice(PERIODOS))
        energia.append({"id_usuario": uid, "energia_declarada": declarado})

        for _ in range(int(rng.integers(15, 40))):
            dia = hoje - pd.Timedelta(days=int(rng.integers(1, 61)))
            periodo = str(rng.choice(PERIODOS))
            inicio = dia + pd.Timedelta(hours=int(rng.integers(*faixa[periodo])))
            fim = inicio + pd.Timedelta(hours=1)
            # mais chance de concluir tarefas agendadas no periodo em que a pessoa realmente rende
            concluiu = rng.random() < (0.8 if periodo == real else 0.5)
            tarefas.append({
                "id_tarefa": id_tarefa,
                "id_usuario": uid,
                "status": "concluida" if concluiu else "pendente",
                "categoria": "outro",
                "data_inicio": inicio,
                "data_fim": fim,
                "concluido_em": inicio + pd.Timedelta(minutes=int(rng.integers(5, 55))) if concluiu else pd.NaT,
            })
            id_tarefa += 1
    return pd.DataFrame(energia), pd.DataFrame(tarefas)


# ------------------------------------------------------------
# TRATAMENTO
# ------------------------------------------------------------
def preparar(energia, tarefas):
    energia = energia.copy()
    energia["energia_declarada"] = energia["energia_declarada"].map(normalizar_energia)
    energia = energia.dropna(subset=["energia_declarada"]).drop_duplicates("id_usuario")

    tarefas = tarefas.copy()
    for coluna in ("data_inicio", "data_fim", "concluido_em"):
        tarefas[coluna] = pd.to_datetime(tarefas[coluna])
    return energia, tarefas


def conclusoes_sem_lote(tarefas):
    """
    concluido_em registra quando a pessoa CLICOU em concluir, nao quando fez.
    Quem marca varias tarefas de uma vez parece 'noturno' so por causa do
    horario do clique. Por isso, conclusoes muito proximas (mesmo lote)
    contam como UM evento.
    """
    c = tarefas.dropna(subset=["concluido_em"]).sort_values(["id_usuario", "concluido_em"]).copy()
    if c.empty:
        c["periodo"] = pd.Series(dtype="object")
        return c, 0, 0

    intervalo = c.groupby("id_usuario")["concluido_em"].diff()
    c["novo_lote"] = intervalo.isna() | (intervalo > pd.Timedelta(minutes=JANELA_LOTE_MIN))
    eventos = c[c["novo_lote"]].copy()
    eventos["periodo"] = eventos["concluido_em"].dt.hour.map(periodo_da_hora)
    return eventos, len(c), len(eventos)


def observado_por_usuario(eventos):
    """Periodo em que cada pessoa mais conclui, so pra quem tem conclusoes suficientes."""
    if eventos.empty:
        return pd.DataFrame()
    cont = (
        eventos.groupby(["id_usuario", "periodo"]).size()
        .unstack(fill_value=0)
        .reindex(columns=PERIODOS, fill_value=0)
    )
    cont["total"] = cont[PERIODOS].sum(axis=1)
    cont["observado"] = cont[PERIODOS].idxmax(axis=1)
    cont["participacao_top"] = cont[PERIODOS].max(axis=1) / cont["total"]
    return cont[cont["total"] >= MIN_CONCLUSOES_USUARIO]


def comparar_declarado_observado(energia, obs):
    vazio = pd.DataFrame()
    if obs.empty:
        return vazio, vazio, vazio
    df = obs.reset_index().merge(energia, on="id_usuario", how="inner")
    # sem periodo dominante claro (conclusoes espalhadas) nao ha "pico observado"
    claros = df[df["participacao_top"] >= PARTICIPACAO_MIN_DOMINANTE]
    comparaveis = claros[claros["energia_declarada"] != "nao_sei"].copy()
    comparaveis["concorda"] = comparaveis["energia_declarada"] == comparaveis["observado"]
    return df, claros, comparaveis


def taxa_conclusao_no_pico(tarefas, energia, agora):
    """
    Entre as tarefas ENCERRADAS (concluidas, ou pendentes com prazo vencido),
    compara a taxa de conclusao das agendadas no periodo de pico declarado
    com as agendadas fora dele.
    """
    base = tarefas.merge(
        energia[energia["energia_declarada"].isin(PERIODOS)], on="id_usuario", how="inner"
    )
    aberta_vencida = base["status"].isin(["pendente", "em_andamento"]) & (base["data_fim"] < agora)
    encerradas = base[(base["status"] == "concluida") | aberta_vencida].copy()
    if encerradas.empty:
        return pd.DataFrame(), 0

    encerradas["concluida"] = encerradas["status"] == "concluida"
    encerradas["periodo_agendado"] = encerradas["data_inicio"].dt.hour.map(periodo_da_hora)
    encerradas["no_pico"] = encerradas["periodo_agendado"] == encerradas["energia_declarada"]
    resumo = encerradas.groupby("no_pico")["concluida"].agg(sucessos="sum", total="count")
    return resumo, encerradas["id_usuario"].nunique()


# ------------------------------------------------------------
# RELATORIO
# ------------------------------------------------------------
def relatorio(energia, tarefas):
    agora = pd.Timestamp(datetime.now())

    eventos, n_conclusoes, n_eventos = conclusoes_sem_lote(tarefas)
    obs = observado_por_usuario(eventos)
    df_obs, claros, comparaveis = comparar_declarado_observado(energia, obs)
    resumo_pico, n_usuarios_pico = taxa_conclusao_no_pico(tarefas, energia, agora)

    # 1. Qualidade dos dados
    titulo("1. QUALIDADE DOS DADOS")
    print(f"Pessoas com energia declarada ............ {len(energia)}")
    if len(energia):
        print("  distribuicao:", energia["energia_declarada"].value_counts().to_dict())
    print(f"Conclusoes registradas ................... {n_conclusoes}")
    if n_conclusoes:
        pct_lote = 1 - n_eventos / n_conclusoes
        print(f"  feitas em lote (< {JANELA_LOTE_MIN} min entre si) ....... {pct_lote:.0%} (cada lote conta 1 vez)")
    print(f"Pessoas com >= {MIN_CONCLUSOES_USUARIO} conclusoes ........... {len(obs)}")
    print(f"  dessas, com energia declarada .......... {len(df_obs)}")
    distribuicao = None
    if not eventos.empty:
        distribuicao = eventos["periodo"].value_counts().reindex(PERIODOS, fill_value=0)
        print("Conclusoes por periodo:", distribuicao.to_dict())

    # 2. Declarado x observado
    titulo("2. ENERGIA DECLARADA x PERIODO OBSERVADO (por pessoa)")
    print(f"Com periodo dominante claro (>= {PARTICIPACAO_MIN_DOMINANTE:.0%} das conclusoes): {len(claros)}")
    print(f"Comparaveis (sem 'nao_sei') .............. {len(comparaveis)}")
    tabela_cruzada = None
    if len(comparaveis) < MIN_USUARIOS_RELATORIO:
        print(f"Dados insuficientes: minimo de {MIN_USUARIOS_RELATORIO} pessoas para reportar percentuais.")
    else:
        concordam = int(comparaveis["concorda"].sum())
        print("Concordancia declarado = observado:", formatar_taxa(concordam, len(comparaveis)))
        print("  (referencia aproximada: ~33% seria o esperado por acaso, com 3 periodos)")
        tabela_cruzada = pd.crosstab(
            comparaveis["energia_declarada"], comparaveis["observado"]
        ).reindex(index=PERIODOS, columns=PERIODOS, fill_value=0)
        print("\nlinhas = declarado, colunas = observado")
        print(tabela_cruzada.to_string())

    # 3. Taxa de conclusao no pico x fora do pico
    titulo("3. TAXA DE CONCLUSAO: TAREFAS NO PICO DECLARADO x FORA DELE")
    total_encerradas = int(resumo_pico["total"].sum()) if not resumo_pico.empty else 0
    print(f"Tarefas encerradas consideradas .......... {total_encerradas} (de {n_usuarios_pico} pessoas)")
    print("  encerrada = concluida, ou pendente/em andamento com prazo vencido; canceladas ficam de fora")
    grupos = resumo_pico.to_dict("index") if not resumo_pico.empty else {}
    if set(grupos) != {True, False} or min(g["total"] for g in grupos.values()) < MIN_TAREFAS_GRUPO:
        print(f"Dados insuficientes: minimo de {MIN_TAREFAS_GRUPO} tarefas em cada grupo.")
    else:
        no, fora = grupos[True], grupos[False]
        print("No pico declarado :", formatar_taxa(int(no["sucessos"]), int(no["total"])))
        print("Fora do pico      :", formatar_taxa(int(fora["sucessos"]), int(fora["total"])))
        baixo1, alto1 = intervalo_wilson(no["sucessos"], no["total"])
        baixo2, alto2 = intervalo_wilson(fora["sucessos"], fora["total"])
        diferenca = no["sucessos"] / no["total"] - fora["sucessos"] / fora["total"]
        print(f"Diferenca: {diferenca * 100:+.1f} pontos percentuais")
        if max(baixo1, baixo2) <= min(alto1, alto2):
            print("Os intervalos se sobrepoem: nao ha evidencia clara de diferenca com esses dados.")
        else:
            print("Os intervalos nao se sobrepoem: ha indicio de diferenca (ainda sem controlar categoria/turno).")

    # 4. Limitacoes
    titulo("4. COMO LER ESTE RELATORIO")
    print("- 'Observado' vem do horario do CLIQUE em concluir, nao de quando a tarefa foi feita.")
    print("- O periodo em que a pessoa mais conclui depende tambem de quando ela AGENDA: quem")
    print("  agenda tudo a noite conclui a noite mesmo sem render mais. A secao 3 (taxa de")
    print("  conclusao por periodo agendado) e a medida mais robusta; a secao 2 e complementar.")
    print("- Nao controla categoria da tarefa, turno de trabalho/estudo nem dia da semana.")
    print("- Os percentuais misturam todas as pessoas: quem tem mais tarefas pesa mais.")
    print("- Horarios em hora local do servidor do banco.")
    print("- Correlacao nao e causa: rende mais no pico declarado nao prova que o pico esta certo.")

    # Exporta SO tabelas agregadas (nada por pessoa)
    PASTA_SAIDA.mkdir(exist_ok=True)
    if tabela_cruzada is not None:
        tabela_cruzada.to_csv(PASTA_SAIDA / "declarado_vs_observado.csv")
    if not resumo_pico.empty:
        resumo_pico.to_csv(PASTA_SAIDA / "conclusao_no_pico.csv")
    if distribuicao is not None:
        distribuicao.to_csv(PASTA_SAIDA / "conclusoes_por_periodo.csv", header=["conclusoes"])
    print(f"\nTabelas agregadas salvas em: {PASTA_SAIDA}/")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="usa dados simulados (nao toca no banco)")
    args = parser.parse_args()

    if args.demo:
        print("=" * 62)
        print("ATENCAO: DADOS SIMULADOS. Servem so pra validar o pipeline.")
        print("Nenhum resultado abaixo e real nem deve ser apresentado como tal.")
        print("=" * 62)
        energia, tarefas = gerar_dados_simulados()
    else:
        energia, tarefas = carregar_do_banco()

    energia, tarefas = preparar(energia, tarefas)
    relatorio(energia, tarefas)


if __name__ == "__main__":
    main()
