"""
NEOCORTEX - verificar_ml_avaliacao.py

Verifica o ml_preparacao.py melhorado SEM banco de dados (usa dados simulados): o histórico da pessoa usa só o que se sabia na
hora (sem vazar o futuro, conferido contra uma implementação independente), a avaliação em 4 janelas de tempo, a decisão em
vários sorteios (não liga com só hábito; liga quando há sinal), dados reais bagunçados e o isolamento do app.

Uso (na pasta do projeto, venv ativado):
    pip install scikit-learn        # só se ainda não tiver (não é dependência do app)
    python verificar_ml_avaliacao.py
"""
GERADOR = r'''"""Dados SIMULADOS no formato que o banco devolve (linhas de tarefas), para testar e demonstrar o ml_preparacao sem banco."""
import math, random
from datetime import datetime, timedelta
P = ("manha", "tarde", "noite"); HORAS = {"manha": (8, 9, 10, 11), "tarde": (13, 14, 15, 16, 17), "noite": (19, 20, 21)}; CATS = ("estudo", "trabalho", "hobby", "pessoal")
sig = lambda x: 1 / (1 + math.exp(-x))
def gerar(regime, n_users, dias, semente=1, por_dia=1.0):
    """regime 'habito': a pessoa só rende mais num período (o que a regra atual já captura).
       regime 'rico': além disso, categoria x período, dia da semana, duração e antecedência pesam para qualquer pessoa."""
    rng, linhas, idt, ini0 = random.Random(semente), [], 0, datetime(2026, 7, 1)
    for u in range(1, n_users + 1):
        favorito = rng.choice(P); declarado = favorito if rng.random() < 0.6 else rng.choice(P); efeito_u = rng.gauss(0, 0.5)
        for d in range(dias):
            if rng.random() >= por_dia: continue
            per, cat = rng.choice(P), rng.choice(CATS); ini = (ini0 + timedelta(days=d)).replace(hour=rng.choice(HORAS[per])); dur = rng.choice([30, 45, 60, 90, 120]); fim = ini + timedelta(minutes=dur); antec = rng.choice([30, 120, 600, 1440, 4320])
            if regime == "habito": p = 0.85 if per == favorito else 0.35
            else:
                z = -0.1 + efeito_u + (1.0 if (cat == "estudo" and per == "manha") else 0) + (0.9 if (cat == "hobby" and per == "noite") else 0) + (0.5 if (cat == "trabalho" and per == "tarde") else 0)
                z += (-0.7 if ini.weekday() >= 5 else 0) - 0.006 * (dur - 60) - (0.6 if antec >= 4320 else 0) + (0.5 if per == declarado else 0) - (0.3 if (per == "noite" and cat == "estudo") else 0); p = sig(z)
            ok = rng.random() < p; idt += 1
            linhas.append({"id_tarefa": idt, "id_usuario": u, "categoria": cat, "data_inicio": ini, "data_fim": fim, "criado_em": ini - timedelta(minutes=antec), "status": "concluida" if ok else "pendente",
                           "concluido_em": fim + timedelta(minutes=max(0, rng.gauss(10, 15))) if ok else None, "energia_declarada": declarado, "n_adiamentos": 0 if ok else rng.choice([0, 1, 2])})
    return linhas, ini0 + timedelta(days=dias + 2)
def instalar_banco_falso(ml, linhas_ref):
    """Troca o db do módulo por um que devolve as linhas simuladas (nada vai ao banco de verdade)."""
    import contextlib
    class Cur:
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def execute(s, sql, params=None): pass
        def fetchall(s): return linhas_ref[0]
    class Conn:
        def cursor(s): return Cur()
    @contextlib.contextmanager
    def conectar(): yield Conn()
    ml.db.conectar = conectar
'''
import sys, os, time, random
from datetime import datetime, timedelta
ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "."); os.chdir(ARV); sys.path.insert(0, ARV)
from unittest.mock import MagicMock
sys.modules["db"] = MagicMock()
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
try:
    import sklearn  # noqa: F401
except ImportError:
    print("Falta o scikit-learn para esta verificação:  pip install scikit-learn")
    sys.exit(2)
import types
import ml_preparacao as ml
G = types.ModuleType("gerador_ml")
exec(GERADOR, G.__dict__)
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
LINHAS = [[]]; G.instalar_banco_falso(ml, LINHAS)
def dataset(regime, u, d, semente=1, extra=None):
    linhas, agora = G.gerar(regime, u, d, semente); LINHAS[0] = linhas + (extra or []); return ml.extrair_features(agora=agora)
D = lambda s: pd.Timestamp(s)
print("=== 1) HISTÓRICO DA PESSOA: o que se sabia quando a tarefa foi agendada ===")
base = {"periodo_agendado": "manha", "concluida": True}
df = pd.DataFrame([
    {**base, "id_usuario": 1, "criado_em": D("2026-01-01 08:00"), "data_inicio": D("2026-01-02 09:00"), "data_fim": D("2026-01-02 10:00"), "concluido_em": D("2026-01-02 10:10")},   # T1: concluída com 10 min de atraso
    {**base, "id_usuario": 1, "criado_em": D("2026-01-02 12:00"), "data_inicio": D("2026-01-03 09:00"), "data_fim": D("2026-01-03 10:00"), "concluido_em": pd.NaT},                    # T2: nunca concluída
    {**base, "id_usuario": 1, "criado_em": D("2026-01-02 10:05"), "data_inicio": D("2026-01-03 11:00"), "data_fim": D("2026-01-03 12:00"), "concluido_em": D("2026-01-03 12:30")},   # T3: agendada 5 min depois do prazo de T1, ANTES de T1 ser concluída
    {**base, "id_usuario": 1, "criado_em": D("2026-01-04 08:00"), "data_inicio": D("2026-01-05 09:00"), "data_fim": D("2026-01-05 10:00"), "concluido_em": D("2026-01-05 10:05")},   # T4
    {**base, "id_usuario": 2, "criado_em": D("2026-01-01 08:00"), "data_inicio": D("2026-01-04 09:00"), "data_fim": D("2026-01-04 10:00"), "concluido_em": D("2026-01-04 10:00")},   # outra pessoa
])
h = ml.historico_previo(df).set_index(["id_usuario", "criado_em"])
get = lambda u, t: h.loc[(u, D(t))]
t1, t3, t4, t2 = get(1, "2026-01-01 08:00"), get(1, "2026-01-02 10:05"), get(1, "2026-01-04 08:00"), get(1, "2026-01-02 12:00")
checa("a 1ª tarefa da pessoa não sabe nada: 0 tarefas prévias e taxas neutras de 50%", t1["n_tarefas_previas"] == 0 and t1["taxa_pessoa_geral_previa"] == 0.5 and t1["taxa_pessoa_periodo_previa"] == 0.5)
checa("T3 foi agendada depois do PRAZO de T1, mas antes de T1 ser concluída: T1 conta como NÃO concluída (era o que o sistema via), e não como concluída", t3["n_tarefas_previas"] == 1 and abs(t3["taxa_pessoa_geral_previa"] - 2.5 / 6) < 1e-9)
checa("T2 (agendada às 12h do dia 2) ainda não conhece T3, que só termina no dia 3: só T1 estava encerrada (concluída às 10h10)", t2["n_tarefas_previas"] == 1 and abs(t2["taxa_pessoa_geral_previa"] - 3.5 / 6) < 1e-9)
checa("T4 conhece T1 (concluída), T2 (não concluída) e T3 (concluída): 2 de 3, suavizado: (2 + 2,5) / (3 + 5)", t4["n_tarefas_previas"] == 3 and abs(t4["taxa_pessoa_geral_previa"] - 4.5 / 8) < 1e-9)
checa("a outra pessoa não interfere: sua única tarefa não sabe nada de ninguém", get(2, "2026-01-01 08:00")["n_tarefas_previas"] == 0)
ordem = ml.historico_previo(df)["data_inicio"]; checa("o resultado vem ordenado por data de início (necessário para as janelas de tempo)", list(ordem) == sorted(ordem))
d1 = dataset("rico", 8, 40, 3); hp = ml.historico_previo(d1)
def referencia(d):    # implementação independente (máscaras do pandas), só para conferir a otimizada
    out = []
    for _, r in d.iterrows():
        ant = d[d["id_usuario"] == r["id_usuario"]]; ok = ant["concluido_em"] < r["criado_em"]; enc = ok | (ant["data_fim"] < r["criado_em"]); n = int(enc.sum()); g = (ok[enc].sum() + 2.5) / (n + 5)
        mp = enc & (ant["periodo_agendado"] == r["periodo_agendado"]); out.append(((ok[mp].sum() + 5 * g) / (mp.sum() + 5), g, n))
    return np.array(out)
ref = referencia(hp); checa("em 320 tarefas simuladas, o cálculo otimizado bate com uma implementação independente (taxa do período, taxa geral e contagem)", np.allclose(hp[["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"]].values, ref))
# o teste mais importante: mudar o resultado de tarefas FUTURAS não pode mexer em nada do que se sabia ANTES
mod = hp.copy(); fut = mod["data_inicio"] >= mod["data_inicio"].quantile(0.8); mod.loc[fut, "concluido_em"] = pd.NaT; mod.loc[fut, "concluida"] = False
t0 = mod.loc[fut, "data_fim"].min(); h2 = ml.historico_previo(mod.drop(columns=["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"])); h1 = ml.historico_previo(hp.drop(columns=["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"]))
chave = lambda x: x.sort_values("id_tarefa").set_index("id_tarefa"); a, b = chave(h1), chave(h2); antes = a.index[a["criado_em"] <= t0]
checa(f"SEM VAZAMENTO: apagar o resultado das tarefas mais recentes não altera o histórico de nenhuma das {len(antes)} tarefas agendadas até o prazo da mais antiga delas", np.allclose(a.loc[antes, ["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"]].values, b.loc[antes, ["taxa_pessoa_periodo_previa", "taxa_pessoa_geral_previa", "n_tarefas_previas"]].values) and len(antes) > 50)
checa("e, para provar que o teste enxerga vazamento, ele muda de fato o histórico das tarefas DEPOIS desse momento", not np.allclose(a.drop(antes)[["taxa_pessoa_geral_previa"]].values, b.drop(antes)[["taxa_pessoa_geral_previa"]].values))
tic = time.time(); big = dataset("rico", 30, 90, 2); ml.historico_previo(big); seg = time.time() - tic; checa(f"desempenho: {len(big)} tarefas em {seg:.1f} s (uso real é bem menor)", seg < 30)
print("\n=== 2) COMPARAÇÃO COM A REGRA ===")
r = ml.comparar_com_baseline(dataset("rico", 5, 12)); checa("volume de hoje (5 pessoas, 12 dias): dados insuficientes, mantém as regras e diz o que falta", r["status"] == "dados_insuficientes" and r["decisao"] == "manter_regras" and len(r["faltando"]) == 3)
ds = dataset("rico", 40, 90, 5); tinha, sk = "sklearn" in sys.modules, sys.modules.get("sklearn"); sys.modules["sklearn"] = None
try: r = ml.comparar_com_baseline(ds)
finally:
    if tinha: sys.modules["sklearn"] = sk
    else: sys.modules.pop("sklearn", None)      # volta a ser importável
checa("sem scikit-learn instalado: avisa e mantém as regras (não quebra)", r["status"] == "sklearn_indisponivel" and r["decisao"] == "manter_regras")
r = ml.comparar_com_baseline(ds)
chaves_antigas = ["status", "versao", "periodo_treino", "n_treino", "n_teste", "features", "metricas", "ganho_relativo_log_loss", "aprovado", "decisao", "fallback", "tarefas_encerradas", "usuarios", "concluidas", "nao_concluidas", "faltando"]
checa("a saída continua com todas as chaves de antes (quem lia o resultado antigo continua funcionando) e ganha as novas", all(k in r for k in chaves_antigas) and all(k in r for k in ["janelas", "n_janelas", "janelas_positivas", "metodo", "baseline", "comparacao_sem_historico"]) and set(r["metricas"]) == {"baseline", "modelo"})
js = r["janelas"]; checa(f"avalia {len(js)} janelas de tempo consecutivas, cada uma com mais treino que a anterior", len(js) == 4 and all(js[i]["treino"] < js[i + 1]["treino"] for i in range(3)) and all(js[i]["ate"] <= js[i + 1]["de"] for i in range(3)))
checa("o treino de cada janela termina ANTES do teste dela (nada de embaralhar: prever o passado com o futuro)", all(j["treino"] + j["teste"] <= r["tarefas_encerradas"] for j in js) and js[0]["treino"] >= 0.39 * r["tarefas_encerradas"])
checa("a decisão segue a regra: ganho médio >= 2% e pelo menos 3 de 4 janelas positivas", r["aprovado"] == (r["ganho_relativo_log_loss"] >= 0.02 and r["janelas_positivas"] >= 3) and r["decisao"] == ("usar_modelo" if r["aprovado"] else "manter_regras"))
r2 = ml.comparar_com_baseline(ds); [x.pop("versao") for x in (r, r2)]; checa("é determinístico: os mesmos dados dão exatamente o mesmo resultado", r == r2)
rs = ml.comparar_com_baseline(ds, usar_historico=False); checa("com usar_historico=False, o modelo não recebe as variáveis do histórico", not any(f in rs["features"] for f in ml.FEATURES_HISTORICO) and all(f in r["features"] for f in ml.FEATURES_HISTORICO) and "comparacao_sem_historico" not in rs)
print("\n=== 3) A DECISÃO É CONFIÁVEL? (vários sorteios de dados simulados) ===")
t0 = time.time(); aprov_b = [ml.comparar_com_baseline(dataset("habito", 30, 60, s))["decisao"] for s in range(1, 9)]
checa(f"só hábito pessoal (a regra já captura tudo): NUNCA liga o modelo em 8 sorteios ({aprov_b.count('usar_modelo')}/8 ligaram)", aprov_b.count("usar_modelo") == 0)
rc = [ml.comparar_com_baseline(dataset("rico", 60, 90, s)) for s in range(1, 9)]
checa(f"sinal além do hábito (categoria, dia, duração, antecedência), 60 pessoas e 90 dias: liga em todos os 8 sorteios ({sum(x['aprovado'] for x in rc)}/8)", all(x["aprovado"] for x in rc))
melhor = sum(1 for x in rc if x["ganho_relativo_log_loss"] > x["comparacao_sem_historico"]["ganho_medio"]); checa(f"o histórico da pessoa ajuda: ganho maior que sem ele em {melhor} de 8 sorteios", melhor >= 7)
print(f"   (ganho médio com histórico: {np.mean([x['ganho_relativo_log_loss'] for x in rc]):+.1%} | sem: {np.mean([x['comparacao_sem_historico']['ganho_medio'] for x in rc]):+.1%} | tempo: {time.time() - t0:.0f} s)")
print("\n=== 4) DADOS REAIS SÃO BAGUNÇADOS ===")
extra = [{"id_tarefa": 90000 + i, "id_usuario": 1000 + i % 3, "categoria": None, "data_inicio": datetime(2026, 8, 1 + i % 20, 10), "data_fim": datetime(2026, 8, 1 + i % 20, 11), "criado_em": datetime(2026, 8, 2 + i % 20, 9), "status": "concluida" if i % 2 else "pendente",
          "concluido_em": datetime(2026, 8, 2 + i % 20, 12) if i % 2 else None, "energia_declarada": None if i % 2 else "Manhã", "n_adiamentos": 0} for i in range(60)]   # sem categoria, sem energia, criada DEPOIS do início (retroativa), cadastro antigo "Manhã"
try: r = ml.comparar_com_baseline(dataset("rico", 40, 90, 5, extra)); ok = r["status"] == "avaliado"
except Exception as e: ok = False; print("   erro:", type(e).__name__, str(e)[:100])
checa("tarefas sem categoria, sem energia declarada, criadas depois do início e energia no formato antigo: não quebram a avaliação", ok)
print("\n=== 5) RELATÓRIO LEGÍVEL E ISOLAMENTO DO APP ===")
txt_i = ml._resumo_legivel(ml.prontidao_ml(dataset("rico", 5, 12)), ml.comparar_com_baseline(dataset("rico", 5, 12))); txt_a = ml._resumo_legivel(ml.prontidao_ml(ds), ml.comparar_com_baseline(ds))
checa("com poucos dados o texto diz o que falta e que o sistema segue com as regras", "ainda não é possível" in txt_i and "tarefas encerradas:" in txt_i and "manter_regras" in txt_i)
checa("com dados suficientes mostra uma linha por janela, o ganho médio, o efeito do histórico e a decisão", txt_a.count("janela ") >= 4 and "ganho médio:" in txt_a and "sem o histórico da pessoa" in txt_a and "decisão:" in txt_a)
import glob, re
usam = [f for f in glob.glob("*.py") if f != "ml_preparacao.py" and not f.startswith(("test_", "atualizar_", "verificar_", "analise", "diagnostico", "simular", "seed", "corrigir")) and re.search(r"^\s*(import|from)\s+ml_preparacao", open(f, encoding="utf-8", errors="replace").read(), re.M)]
checa(f"nenhum módulo do app importa o ml_preparacao (nada em produção depende dele): {usam or 'nenhum'}", usam == [])
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
