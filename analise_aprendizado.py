"""
NEOCORTEX - analise_aprendizado.py

Relatório de ANÁLISE DE DADOS do aprendizado do NEOCORTEX: o que o sistema observa das pessoas, se o que ela declara bate com o
que ela faz, como atrasa e se vale a pena ligar Machine Learning. Gera um relatório em Markdown, gráficos (PNG) e um JSON com os
números, tudo em  analise_saida/.

Princípios:
  - SOMENTE LEITURA: só faz SELECT no banco. Não escreve nada nele.
  - Saída AGREGADA: nunca imprime nem grava nome, e-mail, id de pessoa nem texto livre.
  - HONESTA com amostra pequena: onde os dados não bastam, diz isso (e quanto falta) em vez de desenhar um gráfico enganoso.
  - Reaproveita o que já existe: analise_energia.py (declarado x observado) e ml_preparacao.py (avaliação de ML).

Uso (na pasta do projeto, venv ativado):
    python analise_aprendizado.py            # dados reais do banco
    python analise_aprendizado.py --demo     # dados SIMULADOS (não toca no banco): só para ver o relatório completo
    python analise_aprendizado.py --saida OUTRA_PASTA

Opcional: gráficos precisam de matplotlib (pip install matplotlib); a avaliação de ML precisa de scikit-learn
(pip install scikit-learn). Sem eles o relatório sai igual, só avisa o que faltou.
"""

import argparse
import contextlib
import json
import math
import random
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PERIODOS = ("manha", "tarde", "noite")
ROTULO_PERIODO = {"manha": "Manhã", "tarde": "Tarde", "noite": "Noite"}
MIN_CELULA = 10          # célula categoria x período com menos tarefas que isso não é mostrada
MIN_CONCLUIDAS_ATRASO = 20
CORES = {"base": "#94A3B8", "modelo": "#2563EB", "destaque": "#7C3AED", "alerta": "#DC2626", "ok": "#16A34A", "texto": "#0F172A"}


# ----------------------------------------------------------------------------------------------------------------------
# DADOS SIMULADOS (só para o --demo)
# ----------------------------------------------------------------------------------------------------------------------
def _simular(n_users=60, dias=90, semente=11):
    """Linhas no formato que o banco devolve. Cada pessoa rende mais em um período e declara (com 60% de acerto) outro."""
    rng, linhas, idt, ini0 = random.Random(semente), [], 0, datetime(2026, 7, 1)
    horas = {"manha": (8, 9, 10, 11), "tarde": (13, 14, 15, 16, 17), "noite": (19, 20, 21)}
    cats = ("estudo", "trabalho", "hobby", "pessoal")
    sig = lambda x: 1 / (1 + math.exp(-x))
    for u in range(1, n_users + 1):
        favorito = rng.choice(PERIODOS)
        declarado = favorito if rng.random() < 0.6 else rng.choice(PERIODOS)
        efeito_u, atraso_u = rng.gauss(0, 0.5), max(0.0, rng.gauss(18, 12))
        for d in range(dias):
            per, cat = rng.choice(PERIODOS), rng.choice(cats)
            ini = (ini0 + timedelta(days=d)).replace(hour=rng.choice(horas[per]))
            dur = rng.choice([30, 45, 60, 90, 120])
            fim = ini + timedelta(minutes=dur)
            antec = rng.choice([30, 120, 600, 1440, 4320])
            z = -0.1 + efeito_u + (0.9 if per == favorito else 0) + (0.8 if (cat == "estudo" and per == "manha") else 0) + (0.7 if (cat == "hobby" and per == "noite") else 0)
            z += (0.4 if (cat == "trabalho" and per == "tarde") else 0) + (-0.7 if ini.weekday() >= 5 else 0) - 0.006 * (dur - 60) - (0.6 if antec >= 4320 else 0)
            ok = rng.random() < sig(z)
            idt += 1
            linhas.append({"id_tarefa": idt, "id_usuario": u, "categoria": cat, "data_inicio": ini, "data_fim": fim, "criado_em": ini - timedelta(minutes=antec),
                           "status": "concluida" if ok else "pendente",
                           "concluido_em": fim + timedelta(minutes=rng.gauss(atraso_u, 14)) if ok else None,
                           "energia_declarada": declarado, "n_adiamentos": 0 if ok else rng.choice([0, 1, 2])})
    return linhas, ini0 + timedelta(days=dias + 2)


def _banco_falso(linhas):
    """Módulo 'db' de mentira (o --demo nunca toca no banco de verdade)."""
    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None): pass
        def fetchall(self): return linhas
    class Conn:
        def cursor(self): return Cur()
    @contextlib.contextmanager
    def conectar():
        yield Conn()
    modulo = types.ModuleType("db")
    modulo.conectar = conectar
    return modulo


# ----------------------------------------------------------------------------------------------------------------------
# GRÁFICOS
# ----------------------------------------------------------------------------------------------------------------------
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 12})
        return plt
    except Exception:
        return None


def _salvar(plt, fig, pasta, nome, demo, rodape=None):
    if demo:
        fig.text(0.5, 0.5, "DADOS SIMULADOS", fontsize=34, color="#DC2626", alpha=0.10, ha="center", va="center", rotation=22, fontweight="bold")
    margem = 0.03
    if rodape:
        import textwrap
        linhas = textwrap.wrap(rodape, width=max(40, int(fig.get_figwidth() * 15)))      # a nota nunca passa da largura da figura
        fig.text(0.01, 0.01, "\n".join(linhas), fontsize=8, color="#64748B", ha="left", va="bottom")
        margem = 0.03 + 0.035 * (len(linhas) - 1)
    fig.tight_layout(rect=(0, margem, 1, 1))
    fig.savefig(pasta / nome, dpi=140)
    plt.close(fig)
    return nome


def _grafico_taxa_por_periodo(plt, tabela, ae, pasta, demo):
    fig, eixo = plt.subplots(figsize=(6.4, 4))
    x = np.arange(len(PERIODOS))
    taxas = [t["sucessos"] / t["total"] for t in tabela]
    erros = [[taxas[i] - t["ic"][0] for i, t in enumerate(tabela)], [t["ic"][1] - taxas[i] for i, t in enumerate(tabela)]]
    eixo.bar(x, taxas, color=[CORES["modelo"], CORES["destaque"], CORES["base"]], width=0.55, yerr=erros, capsize=6, ecolor=CORES["texto"])
    for i, t in enumerate(tabela):
        eixo.text(i, 0.03, f"{taxas[i]:.0%}\nn={t['total']}", ha="center", va="bottom", color="white", fontweight="bold", fontsize=10)
    eixo.set_xticks(x, [ROTULO_PERIODO[p] for p in PERIODOS]); eixo.set_ylim(0, 1); eixo.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    eixo.set_ylabel("tarefas concluídas"); eixo.set_title("Taxa de conclusão por período em que a tarefa foi agendada")
    return _salvar(plt, fig, pasta, "taxa_por_periodo.png", demo, "Barras de erro: intervalo de confiança de 95% (Wilson). Tarefas encerradas: concluídas ou com prazo vencido.")


def _grafico_categoria_periodo(plt, celulas, categorias, pasta, demo):
    fig, eixo = plt.subplots(figsize=(6.8, 0.9 + 0.75 * len(categorias)))
    matriz = np.full((len(categorias), len(PERIODOS)), np.nan)
    for i, c in enumerate(categorias):
        for j, p in enumerate(PERIODOS):
            cel = celulas.get((c, p))
            if cel and cel["total"] >= MIN_CELULA:
                matriz[i, j] = cel["sucessos"] / cel["total"]
    imagem = eixo.imshow(matriz, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for i, c in enumerate(categorias):
        for j, p in enumerate(PERIODOS):
            cel = celulas.get((c, p), {"total": 0})
            texto = f"{matriz[i, j]:.0%}\n(n={cel['total']})" if not np.isnan(matriz[i, j]) else f"n<{MIN_CELULA}"
            eixo.text(j, i, texto, ha="center", va="center", fontsize=9, color="white" if (not np.isnan(matriz[i, j]) and matriz[i, j] > 0.6) else CORES["texto"])
    eixo.set_xticks(range(len(PERIODOS)), [ROTULO_PERIODO[p] for p in PERIODOS]); eixo.set_yticks(range(len(categorias)), [c.capitalize() for c in categorias])
    eixo.set_title("Taxa de conclusão por categoria e período"); eixo.spines[:].set_visible(False)
    from matplotlib.ticker import FuncFormatter
    fig.colorbar(imagem, ax=eixo, format=FuncFormatter(lambda v, _: f"{v:.0%}"), shrink=0.8)
    return _salvar(plt, fig, pasta, "taxa_categoria_periodo.png", demo, f"Células com menos de {MIN_CELULA} tarefas não são mostradas (amostra pequena demais).")


def _grafico_declarado_observado(plt, cruzada, concordancia, pasta, demo):
    fig, eixo = plt.subplots(figsize=(5.6, 4.4))
    imagem = eixo.imshow(cruzada.values, cmap="Purples", aspect="equal")
    for i in range(3):
        for j in range(3):
            v = int(cruzada.values[i, j]); eixo.text(j, i, str(v), ha="center", va="center", fontsize=13, fontweight="bold" if i == j else "normal", color="white" if v > cruzada.values.max() * 0.55 else CORES["texto"])
    rotulos = [ROTULO_PERIODO[p] for p in PERIODOS]
    eixo.set_xticks(range(3), rotulos); eixo.set_yticks(range(3), rotulos); eixo.set_xlabel("período em que mais conclui (observado)"); eixo.set_ylabel("período declarado")
    eixo.set_title(f"Declarado x observado: concordam em {concordancia:.0%}"); eixo.spines[:].set_visible(False)
    return _salvar(plt, fig, pasta, "declarado_vs_observado.png", demo, "Diagonal = declarou e faz o mesmo. Por acaso, com 3 períodos, esperaríamos cerca de 33%. Cada pessoa conta uma vez.")


def _grafico_atraso(plt, atrasos, mediana, pasta, demo):
    fig, eixo = plt.subplots(figsize=(6.6, 4))
    cortados = np.clip(atrasos, -60, 240)
    eixo.hist(cortados, bins=np.arange(-60, 255, 15), color=CORES["modelo"], edgecolor="white")
    eixo.axvline(0, color=CORES["texto"], linewidth=1.2, linestyle=":", label="fim previsto (0)")
    eixo.axvline(mediana, color=CORES["alerta"], linewidth=2, label=f"mediana: {mediana:+.0f} min")
    eixo.legend(frameon=False, loc="upper right")
    eixo.set_xlabel("minutos depois do fim previsto (negativo = antes)"); eixo.set_ylabel("tarefas")
    eixo.set_title("Quando a pessoa conclui, em relação ao fim previsto")
    return _salvar(plt, fig, pasta, "atraso_conclusao.png", demo, "É o horário do CLIQUE em concluir, não o de quando a tarefa foi feita. Atrasos acima de 240 min aparecem agrupados na última barra.")


def _grafico_ml(plt, comp, pasta, demo):
    janelas = comp["janelas"]
    fig, (e1, e2) = plt.subplots(1, 2, figsize=(9.6, 4), gridspec_kw={"width_ratios": [1.25, 1]})
    x = np.arange(len(janelas)); larg = 0.38
    e1.bar(x - larg / 2, [j["log_loss_baseline"] for j in janelas], larg, label="regra atual", color=CORES["base"])
    e1.bar(x + larg / 2, [j["log_loss_modelo"] for j in janelas], larg, label="modelo", color=CORES["modelo"])
    e1.set_xticks(x, [f"janela {i + 1}\n(teste n={j['teste']})" for i, j in enumerate(janelas)]); e1.set_ylabel("log-loss (menor = melhor)")
    low = min(min(j["log_loss_baseline"], j["log_loss_modelo"]) for j in janelas); e1.set_ylim(max(0, low - 0.08), None)
    e1.set_title("Erro da previsão, por janela de tempo"); e1.legend(frameon=False)
    ganhos = [j["ganho"] * 100 for j in janelas]
    e2.bar(x, ganhos, 0.55, color=[CORES["ok"] if g >= 2 else (CORES["modelo"] if g > 0 else CORES["alerta"]) for g in ganhos])
    e2.axhline(2, color=CORES["alerta"], linestyle="--", linewidth=1.4, label="mínimo exigido: +2%"); e2.axhline(0, color=CORES["texto"], linewidth=0.8)
    e2.set_ylim(min(0, min(ganhos) * 1.4 - 0.4), max(max(ganhos), 2) * 1.45); e2.legend(loc="upper left", frameon=False, fontsize=9)
    for i, g in enumerate(ganhos): e2.text(i, g + (0.15 if g >= 0 else -0.15), f"{g:+.1f}%", ha="center", va="bottom" if g >= 0 else "top", fontsize=9, fontweight="bold")
    e2.set_xticks(x, [f"{i + 1}" for i in range(len(janelas))]); e2.set_xlabel("janela"); e2.set_ylabel("ganho do modelo sobre a regra")
    e2.set_title(f"Ganho médio {comp['ganho_relativo_log_loss']:+.1%}: {comp['decisao'].replace('_', ' ')}")
    return _salvar(plt, fig, pasta, "ml_janelas.png", demo, "Em cada janela o modelo treina só com o que é mais antigo e é testado na janela seguinte. Atenção: o eixo do gráfico da esquerda NÃO começa em zero (para a diferença aparecer); o da direita mostra o ganho real em %.")


# ----------------------------------------------------------------------------------------------------------------------
# ANÁLISE
# ----------------------------------------------------------------------------------------------------------------------
def _taxas(df, colunas, ae):
    saida = {}
    for chave, g in df.groupby(colunas):
        saida[chave] = {"sucessos": int(g["concluida"].sum()), "total": int(len(g)), "ic": ae.intervalo_wilson(int(g["concluida"].sum()), int(len(g)))}
    return saida


def analisar(df, ml, ae, energia, tarefas, demo, pasta, plt):
    """Devolve (resultados, linhas do relatório). Cada seção diz quando os dados não bastam."""
    pasta.mkdir(exist_ok=True)
    R, md, graficos = {}, [], []
    pront = ml.prontidao_ml(df)
    n = len(df)
    # ---------------------------------------------------------------- 1. dados
    md += ["## 1. Os dados", ""]
    if n == 0:
        md += ["Ainda não há tarefas encerradas (concluídas ou com prazo vencido) para analisar.", ""]
        R["dados"] = {"tarefas_encerradas": 0}
        return R, md, graficos
    por_pessoa = df.groupby("id_usuario").size()
    R["dados"] = {"tarefas_encerradas": n, "pessoas": int(df["id_usuario"].nunique()), "concluidas": int(df["concluida"].sum()),
                  "taxa_conclusao": round(float(df["concluida"].mean()), 4), "primeira_tarefa": str(df["data_inicio"].min())[:10], "ultima_tarefa": str(df["data_inicio"].max())[:10],
                  "tarefas_por_pessoa": {"minimo": int(por_pessoa.min()), "mediana": float(por_pessoa.median()), "maximo": int(por_pessoa.max())}}
    d = R["dados"]
    md += [f"- **{n}** tarefas encerradas de **{d['pessoas']}** pessoas, entre {d['primeira_tarefa']} e {d['ultima_tarefa']}.",
           f"- **{d['concluidas']}** foram concluídas (**{d['taxa_conclusao']:.0%}**) e {n - d['concluidas']} ficaram com o prazo vencido sem concluir.",
           f"- Tarefas por pessoa: mínimo {d['tarefas_por_pessoa']['minimo']}, mediana {d['tarefas_por_pessoa']['mediana']:.0f}, máximo {d['tarefas_por_pessoa']['maximo']}.", "",
           "**Já dá para avaliar Machine Learning?** (critério definido no `ml_preparacao.py`)", "",
           "| Critério | Atual | Mínimo | |", "|---|---:|---:|:---:|",
           f"| Tarefas encerradas | {pront['tarefas_encerradas']} | {ml.MIN_TAREFAS_ENCERRADAS} | {'✅' if pront['tarefas_encerradas'] >= ml.MIN_TAREFAS_ENCERRADAS else '❌'} |",
           f"| Pessoas com histórico | {pront['usuarios']} | {ml.MIN_USUARIOS} | {'✅' if pront['usuarios'] >= ml.MIN_USUARIOS else '❌'} |",
           f"| Exemplos da classe minoritária | {min(pront['concluidas'], pront['nao_concluidas'])} | {ml.MIN_POR_CLASSE} | {'✅' if min(pront['concluidas'], pront['nao_concluidas']) >= ml.MIN_POR_CLASSE else '❌'} |", ""]
    R["prontidao"] = {k: pront[k] for k in ("pronto", "tarefas_encerradas", "usuarios", "concluidas", "nao_concluidas")}
    # ---------------------------------------------------------------- 2. observações
    md += ["## 2. O que o sistema observa", "", "### 2.1 Conclusão por período do dia", ""]
    por_periodo = _taxas(df, "periodo_agendado", ae)
    tabela = [por_periodo.get(p) for p in PERIODOS]
    if any(t is None or t["total"] < 10 for t in tabela):
        md += ["Dados insuficientes: é preciso pelo menos 10 tarefas agendadas em cada período para comparar.", ""]
    else:
        R["taxa_por_periodo"] = {p: {"taxa": round(t["sucessos"] / t["total"], 4), "n": t["total"], "ic95": [round(t["ic"][0], 4), round(t["ic"][1], 4)]} for p, t in zip(PERIODOS, tabela)}
        md += ["| Período | Concluídas | Tarefas | Taxa | IC 95% |", "|---|---:|---:|---:|---|"]
        md += [f"| {ROTULO_PERIODO[p]} | {t['sucessos']} | {t['total']} | {t['sucessos'] / t['total']:.0%} | {t['ic'][0]:.0%} a {t['ic'][1]:.0%} |" for p, t in zip(PERIODOS, tabela)]
        melhor, pior = max(range(3), key=lambda i: tabela[i]["sucessos"] / tabela[i]["total"]), min(range(3), key=lambda i: tabela[i]["sucessos"] / tabela[i]["total"])
        se_sobrepoe = max(tabela[melhor]["ic"][0], tabela[pior]["ic"][0]) <= min(tabela[melhor]["ic"][1], tabela[pior]["ic"][1])
        md += ["", (f"**Leitura:** a diferença entre {ROTULO_PERIODO[PERIODOS[melhor]].lower()} e {ROTULO_PERIODO[PERIODOS[pior]].lower()} está dentro da margem de erro: não há evidência clara de que um período seja melhor que o outro para todas as pessoas juntas."
                    if se_sobrepoe else f"**Leitura:** {ROTULO_PERIODO[PERIODOS[melhor]].lower()} tem taxa maior que {ROTULO_PERIODO[PERIODOS[pior]].lower()}, com intervalos que não se sobrepõem. Isso mistura todas as pessoas: o melhor período é diferente para cada uma, e é por isso que o sistema aprende POR PESSOA."), ""]
        if plt:
            graficos.append(_grafico_taxa_por_periodo(plt, tabela, ae, pasta, demo)); md += [f"![Taxa de conclusão por período]({graficos[-1]})", ""]
    md += ["### 2.2 Conclusão por categoria e período", ""]
    celulas = _taxas(df, ["categoria", "periodo_agendado"], ae)
    categorias = [c for c in ("estudo", "trabalho", "hobby", "pessoal", "saude", "outro", "sem_categoria") if any(celulas.get((c, p), {"total": 0})["total"] >= MIN_CELULA for p in PERIODOS)]
    if not categorias:
        md += [f"Dados insuficientes: nenhuma combinação de categoria e período tem {MIN_CELULA} tarefas ou mais.", ""]
    else:
        R["taxa_categoria_periodo"] = {f"{c}/{p}": {"taxa": round(v["sucessos"] / v["total"], 4), "n": v["total"]} for (c, p), v in celulas.items() if v["total"] >= MIN_CELULA}
        md += ["Isso é o que sustenta o aprendizado **por categoria** (estudo de manhã, trabalho à tarde...): só aparecem combinações com amostra mínima.", ""]
        for c in categorias:
            validos = [(p, celulas[(c, p)]) for p in PERIODOS if celulas.get((c, p), {"total": 0})["total"] >= MIN_CELULA]
            if len(validos) < 2:
                continue
            (pm, m), (pp, w) = max(validos, key=lambda x: x[1]["sucessos"] / x[1]["total"]), min(validos, key=lambda x: x[1]["sucessos"] / x[1]["total"])
            claro = max(m["ic"][0], w["ic"][0]) > min(m["ic"][1], w["ic"][1])
            md += [f"- **{c.capitalize()}**: melhor em {ROTULO_PERIODO[pm].lower()} ({m['sucessos'] / m['total']:.0%}) e pior em {ROTULO_PERIODO[pp].lower()} ({w['sucessos'] / w['total']:.0%}): " + ("diferença clara (intervalos não se sobrepõem)." if claro else "dentro da margem de erro (não dá para afirmar).")]
        md += [""]
        if plt:
            graficos.append(_grafico_categoria_periodo(plt, celulas, categorias, pasta, demo)); md += [f"![Categoria e período]({graficos[-1]})", ""]
    md += ["### 2.3 O que a pessoa declara x o que ela faz", ""]
    if ae is None or energia is None or tarefas is None:
        md += ["Não encontrei o `analise_energia.py` na pasta do projeto; esta seção foi pulada.", ""]
    else:
        energia_p, tarefas_p = ae.preparar(energia, tarefas)
        eventos, n_concl, n_eventos = ae.conclusoes_sem_lote(tarefas_p)
        obs = ae.observado_por_usuario(eventos)
        df_obs, claros, comparaveis = ae.comparar_declarado_observado(energia_p, obs)
        pct_lote = (1 - n_eventos / n_concl) if n_concl else 0
        md += [f"- Pessoas com energia declarada: {len(energia_p)}. Com {ae.MIN_CONCLUSOES_USUARIO} conclusões ou mais: {len(obs)}. Com um período dominante claro (≥ {ae.PARTICIPACAO_MIN_DOMINANTE:.0%} das conclusões): {len(claros)}. Comparáveis (declararam um período): {len(comparaveis)}.",
               f"- {pct_lote:.0%} das conclusões foram marcadas em lote (menos de {ae.JANELA_LOTE_MIN} min entre si); cada lote conta uma vez, porque o horário é o do clique."]
        R["declarado_vs_observado"] = {"pessoas_comparaveis": int(len(comparaveis))}
        if len(comparaveis) < ae.MIN_USUARIOS_RELATORIO:
            md += ["", f"Dados insuficientes: são necessárias pelo menos {ae.MIN_USUARIOS_RELATORIO} pessoas comparáveis para reportar percentuais."]
        else:
            concordam = int(comparaveis["concorda"].sum()); total = len(comparaveis); baixo, alto = ae.intervalo_wilson(concordam, total)
            cruzada = pd.crosstab(comparaveis["energia_declarada"], comparaveis["observado"]).reindex(index=PERIODOS, columns=PERIODOS, fill_value=0)
            R["declarado_vs_observado"].update({"concordam": concordam, "total": total, "taxa": round(concordam / total, 4), "ic95": [round(baixo, 4), round(alto, 4)]})
            md += ["", f"**Concordância entre declarado e observado: {concordam / total:.0%}** ({concordam} de {total} pessoas; IC 95% {baixo:.0%} a {alto:.0%}). Por acaso, com 3 períodos, esperaríamos cerca de 33%."]
            md += ["", (("**Leitura:** há indício de que a concordância é maior que o acaso, mas a amostra é pequena (o intervalo é largo e mal passa de 33%): precisa de mais pessoas para afirmar." if total < 30 else "**Leitura:** a concordância é claramente maior que o acaso: o que a pessoa declara costuma refletir o que ela faz.") if baixo > 1 / 3 else
                        "**Leitura:** a concordância NÃO se distingue do acaso: o que a pessoa declara pouco prevê o que ela faz. É a razão de existir o aprendizado observado, e não só o declarado." if alto >= 1 / 3 else
                        "**Leitura:** a concordância é MENOR que o acaso: quem declara um período tende a render em outro."), ""]
            if plt:
                graficos.append(_grafico_declarado_observado(plt, cruzada, concordam / total, pasta, demo)); md += [f"![Declarado x observado]({graficos[-1]})", ""]
        resumo, n_pessoas_pico = ae.taxa_conclusao_no_pico(tarefas_p, energia_p, pd.Timestamp(datetime.now()))
        grupos = resumo.to_dict("index") if not resumo.empty else {}
        if set(grupos) == {True, False} and min(g["total"] for g in grupos.values()) >= ae.MIN_TAREFAS_GRUPO:
            no, fora = grupos[True], grupos[False]; b1, a1 = ae.intervalo_wilson(no["sucessos"], no["total"]); b2, a2 = ae.intervalo_wilson(fora["sucessos"], fora["total"])
            R["pico_declarado"] = {"no_pico": round(no["sucessos"] / no["total"], 4), "fora_do_pico": round(fora["sucessos"] / fora["total"], 4), "n_no_pico": int(no["total"]), "n_fora": int(fora["total"])}
            md += [f"**Taxa de conclusão das tarefas agendadas no pico declarado: {no['sucessos'] / no['total']:.0%}** (n={int(no['total'])}; IC 95% {b1:.0%} a {a1:.0%}) **contra {fora['sucessos'] / fora['total']:.0%} fora dele** (n={int(fora['total'])}; IC 95% {b2:.0%} a {a2:.0%}).",
                   "", ("Os intervalos se sobrepõem: sem evidência clara de que agendar no pico declarado ajude." if max(b1, b2) <= min(a1, a2) else "Os intervalos não se sobrepõem: há indício de que agendar no pico declarado ajuda (ainda sem controlar categoria nem turno)."), ""]
        else:
            md += ["", f"Comparação 'no pico declarado x fora dele': dados insuficientes (precisa de {ae.MIN_TAREFAS_GRUPO} tarefas ou mais em cada grupo).", ""]
    md += ["### 2.4 Atraso na conclusão", ""]
    atrasos = df.loc[df["concluida"], "atraso_min"].dropna().values
    if len(atrasos) < MIN_CONCLUIDAS_ATRASO:
        md += [f"Dados insuficientes: {len(atrasos)} conclusões com horário registrado (mínimo {MIN_CONCLUIDAS_ATRASO}).", ""]
    else:
        med, p75 = float(np.median(atrasos)), float(np.percentile(atrasos, 75)); depois = float((atrasos > 0).mean())
        R["atraso"] = {"mediana_min": round(med, 1), "p75_min": round(p75, 1), "fracao_apos_o_fim_previsto": round(depois, 4), "n": int(len(atrasos))}
        md += [f"- Mediana: **{med:+.0f} min** em relação ao fim previsto (percentil 75: {p75:+.0f} min). **{depois:.0%}** das conclusões foram marcadas depois do fim previsto.",
               "- É a base da **folga** que o sistema reserva ao sugerir horários quando a pessoa costuma terminar depois do previsto.", ""]
        if plt:
            graficos.append(_grafico_atraso(plt, atrasos, med, pasta, demo)); md += [f"![Atraso na conclusão]({graficos[-1]})", ""]
    # ---------------------------------------------------------------- 3. ML
    md += ["## 3. Machine Learning: vale a pena ligar?", ""]
    comp = ml.comparar_com_baseline(df)
    R["ml"] = {k: comp[k] for k in ("status", "decisao") if k in comp}
    if comp["status"] == "dados_insuficientes":
        md += ["**Ainda não.** " + ("; ".join(comp.get("faltando") or []) or comp.get("detalhe", "")) + ".", "", "O sistema segue com as regras (aprendizado estatístico por pessoa e por categoria), que funcionam desde o primeiro uso. O modelo só é avaliado quando o volume atinge o critério acima.", ""]
    elif comp["status"] == "sklearn_indisponivel":
        md += ["Há dados suficientes, mas falta o scikit-learn para avaliar o modelo (`pip install scikit-learn`; não é dependência do app).", ""]
    else:
        R["ml"].update({"ganho_medio": comp["ganho_relativo_log_loss"], "janelas_positivas": comp["janelas_positivas"], "n_janelas": comp["n_janelas"], "aprovado": comp["aprovado"],
                        "log_loss_regra": comp["metricas"]["baseline"]["log_loss"], "log_loss_modelo": comp["metricas"]["modelo"]["log_loss"], "janelas": [{k: j[k] for k in ("treino", "teste", "log_loss_baseline", "log_loss_modelo", "ganho")} for j in comp["janelas"]]})
        if "comparacao_sem_historico" in comp: R["ml"]["ganho_medio_sem_historico"] = comp["comparacao_sem_historico"]["ganho_medio"]
        md += ["O modelo (regressão logística) prevê se uma tarefa será concluída a partir de como foi agendada. Ele é comparado com a **regra que o sistema usa hoje** (taxa da pessoa naquele período, atualizada a cada tarefa), em janelas de tempo: treina só com o passado e é testado na janela seguinte.", "",
               "| Janela | Treino | Teste | Log-loss da regra | Log-loss do modelo | Ganho |", "|---:|---:|---:|---:|---:|---:|"]
        md += [f"| {i} | {j['treino']} | {j['teste']} | {j['log_loss_baseline']:.4f} | {j['log_loss_modelo']:.4f} | {j['ganho']:+.1%} |" for i, j in enumerate(comp["janelas"], 1)]
        md += ["", f"**Ganho médio: {comp['ganho_relativo_log_loss']:+.1%}** (exigido: +{ml.GANHO_MINIMO_LOGLOSS:.0%}), positivo em **{comp['janelas_positivas']} de {comp['n_janelas']}** janelas (exigido: 3 de 4). **Decisão: {comp['decisao'].replace('_', ' ').upper()}.**"]
        if "comparacao_sem_historico" in comp:
            s = comp["comparacao_sem_historico"]
            efeito = ("conhecer a pessoa (o histórico dela) é o que faz o modelo valer a pena." if s["ganho_medio"] < comp["ganho_relativo_log_loss"] - 0.005 else "nestes dados o histórico da pessoa não fez diferença.")
            md += ["", f"Sem o histórico da própria pessoa como variável, o ganho médio seria {s['ganho_medio']:+.1%} ({s['janelas_positivas']} de {s['n_janelas']} janelas): {efeito}"]
        md += ["", ("**O que isso significa:** o modelo previu melhor que a regra nestes dados, de forma repetida. Isso NÃO o coloca em produção: ligar exige integrá-lo ao sistema, mantendo a regra como plano B."
                    if comp["aprovado"] else "**O que isso significa:** nestes dados o modelo não superou a regra de forma consistente; o sistema segue com as regras, que já aprendem por pessoa e por categoria."), ""]
        if plt:
            graficos.append(_grafico_ml(plt, comp, pasta, demo)); md += [f"![Modelo x regra por janela]({graficos[-1]})", ""]
    return R, md, graficos


LIMITES = [
    "## 4. Como ler este relatório (limitações)", "",
    "- O horário de conclusão é o do **clique** em concluir, não o de quando a tarefa foi feita. Quem marca várias de uma vez parece 'noturno' pelo horário do clique; por isso cada lote conta uma vez.",
    "- Onde a pessoa mais conclui depende também de **quando ela agenda**: quem agenda tudo à noite conclui à noite sem render mais. A taxa de conclusão por período agendado é a medida mais robusta.",
    "- Os percentuais misturam todas as pessoas: quem tem mais tarefas pesa mais.",
    "- Não se controla turno de trabalho/estudo nem a dificuldade de cada tarefa.",
    "- Horários em hora local do servidor do banco.",
    "- Correlação não é causa: render mais no pico declarado não prova que o pico está certo.",
    "- Resultados de ML valem para os dados disponíveis; com poucos dados, a decisão de manter as regras é a honesta.",
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Relatório de análise de dados do aprendizado do NEOCORTEX (somente leitura).")
    ap.add_argument("--demo", action="store_true", help="usa dados SIMULADOS (não toca no banco)")
    ap.add_argument("--saida", default="analise_saida", help="pasta de saída (padrão: analise_saida)")
    args = ap.parse_args(argv)
    raiz = Path(__file__).resolve().parent
    sys.path.insert(0, str(raiz))
    linhas = None
    if args.demo:
        linhas, agora = _simular()
        sys.modules["db"] = _banco_falso(linhas)
    import ml_preparacao as ml
    try:
        import analise_energia as ae
    except ImportError:
        print("Aviso: analise_energia.py não encontrado; a seção 'declarado x observado' será pulada.")
        ae = None
    if ae is None:
        class _Min:      # só o intervalo de Wilson, para o resto do relatório não depender do arquivo ausente
            @staticmethod
            def intervalo_wilson(s, t, z=1.96):
                if t == 0: return (float("nan"), float("nan"))
                p = s / t; den = 1 + z ** 2 / t; c = (p + z ** 2 / (2 * t)) / den; m = z * math.sqrt(p * (1 - p) / t + z ** 2 / (4 * t ** 2)) / den
                return (c - m, c + m)
        analisador = _Min
    else:
        analisador = ae
    if args.demo:
        df = ml.extrair_features(agora=agora)
        energia = pd.DataFrame([{"id_usuario": u, "energia_declarada": e} for u, e in sorted({(l["id_usuario"], l["energia_declarada"]) for l in linhas})])
        tarefas = pd.DataFrame([{k: l[k] for k in ("id_tarefa", "id_usuario", "status", "categoria", "data_inicio", "data_fim", "concluido_em")} for l in linhas])
    else:
        df = ml.extrair_features()
        energia, tarefas = ae.carregar_do_banco() if ae else (None, None)
    pasta = Path(args.saida)
    plt = _plt()
    resultados, corpo, graficos = analisar(df, ml, ae if ae else analisador, energia if ae else None, tarefas if ae else None, args.demo, pasta, plt)
    cabecalho = ["# NEOCORTEX — análise de dados do aprendizado", "", f"_Gerado em {datetime.now():%d/%m/%Y %H:%M}._", ""]
    if args.demo:
        cabecalho += ["> **ATENÇÃO: DADOS SIMULADOS.** Servem só para mostrar o relatório completo e validar o pipeline. Nenhum número abaixo é resultado real de uso e não deve ser apresentado como tal.", ""]
    else:
        cabecalho += ["> Dados reais do banco, em leitura (nada é alterado). Números agregados: nenhuma pessoa é identificada.", ""]
    if plt is None:
        cabecalho += ["> Os gráficos não foram gerados porque o matplotlib não está instalado (`pip install matplotlib`).", ""]
    pasta.mkdir(exist_ok=True)
    (pasta / "relatorio_analise.md").write_text("\n".join(cabecalho + corpo + LIMITES) + "\n", encoding="utf-8")
    resultados["simulado"] = bool(args.demo)
    (pasta / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Relatório: {pasta / 'relatorio_analise.md'}")
    print(f"Gráficos ({len(graficos)}): " + (", ".join(graficos) if graficos else "nenhum"))
    print(f"Números: {pasta / 'resultados.json'}")
    if args.demo:
        print("LEMBRETE: DADOS SIMULADOS. Nada disso é resultado real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
