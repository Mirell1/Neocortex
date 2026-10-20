"""
NEOCORTEX - verificar_analise_aprendizado.py

Verifica a ferramenta analise_aprendizado.py SEM banco de dados: modo demonstração (relatório, JSON e 5 gráficos), privacidade
(nada que identifique pessoas), SOMENTE LEITURA (toda consulta é SELECT), poucos dados (diz que não dá em vez de inventar gráfico),
banco vazio e dependências opcionais ausentes.

Uso (na pasta do projeto, venv ativado):
    pip install matplotlib scikit-learn     # só se ainda não tiver (não são dependências do app)
    python verificar_analise_aprendizado.py
"""
import sys, os, io, re, json, shutil, tempfile, subprocess, contextlib, types
from pathlib import Path
ARV = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve(); falhas = []
for _m in ("matplotlib", "sklearn"):
    try:
        __import__(_m)
    except ImportError:
        print(f"Falta o {_m} para esta verificação:  pip install {'scikit-learn' if _m == 'sklearn' else _m}")
        sys.exit(2)
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
def roda(args, cwd=ARV, env_extra=None, codigo=None):
    env = {**os.environ, **(env_extra or {})}
    cmd = [sys.executable] + (["-c", codigo] if codigo else ["analise_aprendizado.py"] + args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
print("=== 1) MODO DEMONSTRAÇÃO ===")
saida = Path(tempfile.mkdtemp(prefix="an_")) / "saida"; r = roda(["--demo", "--saida", str(saida)])
checa("roda sem erro e avisa, ao final, que os dados são simulados", r.returncode == 0 and "DADOS SIMULADOS" in r.stdout and "Gráficos (5)" in r.stdout)
arqs = sorted(p.name for p in saida.iterdir()); esperados = ["atraso_conclusao.png", "declarado_vs_observado.png", "ml_janelas.png", "relatorio_analise.md", "resultados.json", "taxa_categoria_periodo.png", "taxa_por_periodo.png"]
checa(f"gera exatamente o relatório, o JSON e os 5 gráficos: {arqs == esperados}", arqs == esperados)
import struct
pngs = [saida / n for n in arqs if n.endswith(".png")]
def dim(p): b = p.read_bytes(); return (b[:8] == b"\x89PNG\r\n\x1a\n", *struct.unpack(">II", b[16:24]), len(b))
checa("os gráficos são PNG válidos, grandes o bastante para ler e não vazios", all(dim(p)[0] and dim(p)[1] >= 700 and dim(p)[2] >= 400 and dim(p)[3] > 15000 for p in pngs))
md = (saida / "relatorio_analise.md").read_text(encoding="utf-8")
checa("o relatório tem as 4 seções e o aviso de DADOS SIMULADOS no topo", all(t in md for t in ("## 1. Os dados", "## 2. O que o sistema observa", "## 3. Machine Learning", "## 4. Como ler")) and md.index("DADOS SIMULADOS") < md.index("## 1."))
checa("cada gráfico mencionado no relatório existe como arquivo (nenhum link quebrado)", all((saida / m).exists() for m in re.findall(r"\]\(([^)]+\.png)\)", md)) and len(re.findall(r"\]\(([^)]+\.png)\)", md)) == 5)
js = json.loads((saida / "resultados.json").read_text(encoding="utf-8")); checa("o JSON marca simulado=true e traz os números das seções (dados, período, atraso, ML)", js["simulado"] is True and all(k in js for k in ("dados", "taxa_por_periodo", "atraso", "ml", "prontidao")) and js["ml"]["decisao"] in ("usar_modelo", "manter_regras"))
checa("os números do relatório batem com os do JSON (mesma fonte)", f"**{js['dados']['tarefas_encerradas']}** tarefas" in md and f"{js['ml']['ganho_medio']:+.1%}" in md)
checa("uma frase afirma menos do que os dados mostram? Não: amostra pequena de pessoas comparáveis gera 'amostra é pequena', não 'claramente'", ("claramente maior" not in md) or js["declarado_vs_observado"]["total"] >= 30)
print("\n=== 2) PRIVACIDADE E SOMENTE LEITURA ===")
checa("o relatório não traz e-mails, ids de pessoa nem nomes de coluna internos", "@" not in md and "id_usuario" not in md and "id_tarefa" not in md and not re.search(r"\busuario_\d|\bpessoa \d+\b", md))
checa("o JSON também é só agregado (nenhuma lista de ids)", "id_usuario" not in json.dumps(js) and "@" not in json.dumps(js))
sql_visto = []
codigo_banco = r'''
import sys, types, contextlib, json
from datetime import datetime, timedelta
vistos = []
class Cur:
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def execute(s, sql, p=None): vistos.append(" ".join(sql.split()))
    def fetchall(s): return []
class Conn:
    def cursor(s): return Cur()
    def commit(s): vistos.append("COMMIT!")
@contextlib.contextmanager
def conectar(): yield Conn()
m = types.ModuleType("db"); m.conectar = conectar; sys.modules["db"] = m
import analise_aprendizado as A
import tempfile, os
A.main(["--saida", tempfile.mkdtemp()])
print("SQL:" + json.dumps(vistos))
'''
r = roda([], codigo=codigo_banco); linhas = [l for l in r.stdout.splitlines() if l.startswith("SQL:")]; sqls = json.loads(linhas[0][4:]) if linhas else []
checa(f"no modo real, TODA consulta ao banco é um SELECT (nenhum INSERT/UPDATE/DELETE/COMMIT): {len(sqls)} consulta(s)", len(sqls) >= 1 and all(re.match(r"^\s*SELECT\b", q, re.I) for q in sqls) and not any(re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b|COMMIT", q, re.I) for q in sqls))
d_vazio = Path(tempfile.mkdtemp(prefix="an_")); r = roda([], codigo=codigo_banco.replace("A.main([\"--saida\", tempfile.mkdtemp()])", f'A.main(["--saida", {str(d_vazio)!r}])'))
mdv = (d_vazio / "relatorio_analise.md").read_text(encoding="utf-8") if (d_vazio / "relatorio_analise.md").exists() else ""
checa("banco totalmente vazio: não quebra e diz que ainda não há tarefas para analisar", r.returncode == 0 and "Ainda não há tarefas encerradas" in mdv)
print("\n=== 3) BANCO REAL COM POUCOS DADOS: o relatório diz que não dá, e não inventa gráfico ===")
banco_pouco = codigo_banco.replace("def fetchall(s): return []", '''def fetchall(s):
        q = vistos[-1] if vistos else ""
        if "FROM tarefas" in q and "padroes" in q:
            base = datetime(2026, 10, 1, 9)
            return [dict(id_tarefa=i, id_usuario=1 + i % 2, categoria="estudo", data_inicio=base + timedelta(days=i), data_fim=base + timedelta(days=i, hours=1), criado_em=base + timedelta(days=i - 1), status="concluida" if i % 2 else "pendente", concluido_em=base + timedelta(days=i, hours=1, minutes=10) if i % 2 else None, energia_declarada="manha", n_adiamentos=0) for i in range(14)]
        return []''').replace('print("SQL:" + json.dumps(vistos))', 'print("SQL:" + json.dumps(vistos)); print("PASTA:" + sys.argv[1] if len(sys.argv) > 1 else "")')
d_pouco = Path(tempfile.mkdtemp(prefix="an_")); r = roda([], codigo=banco_pouco.replace("A.main([\"--saida\", tempfile.mkdtemp()])", f'A.main(["--saida", {str(d_pouco)!r}])'))
md2 = (d_pouco / "relatorio_analise.md").read_text(encoding="utf-8") if (d_pouco / "relatorio_analise.md").exists() else ""
checa("com 14 tarefas de 2 pessoas: gera o relatório, SEM aviso de simulado e sem erro", r.returncode == 0 and "DADOS SIMULADOS" not in md2 and "Dados reais do banco" in md2)
checa("diz que ML ainda não dá, com o que falta (tarefas e pessoas), e mantém as regras", "**Ainda não.**" in md2 and "tarefas encerradas: 14/300" in md2 and "usuários com histórico: 2/20" in md2)
checa("seções sem amostra dizem 'Dados insuficientes' em vez de desenhar gráfico", md2.count("Dados insuficientes") >= 3 and not list(d_pouco.glob("ml_janelas.png")) and not list(d_pouco.glob("declarado_vs_observado.png")))
print("\n=== 4) DEPENDÊNCIAS OPCIONAIS AUSENTES ===")
sem_mpl = Path(tempfile.mkdtemp(prefix="an_"))
bloqueio = "import sys; sys.modules['matplotlib'] = None; sys.modules['matplotlib.pyplot'] = None\nimport analise_aprendizado as A; A.main(['--demo', '--saida', %r])" % str(sem_mpl)
r = roda([], codigo=bloqueio); mdm = (sem_mpl / "relatorio_analise.md").read_text(encoding="utf-8")
checa("sem matplotlib: o relatório sai completo, sem imagens, avisando como instalar", r.returncode == 0 and "matplotlib não está instalado" in mdm and not list(sem_mpl.glob("*.png")) and "## 3. Machine Learning" in mdm and "![" not in mdm)
sem_sk = Path(tempfile.mkdtemp(prefix="an_")); bloqueio = "import sys; sys.modules['sklearn'] = None\nimport analise_aprendizado as A; A.main(['--demo', '--saida', %r])" % str(sem_sk)
r = roda([], codigo=bloqueio); mds = (sem_sk / "relatorio_analise.md").read_text(encoding="utf-8")
checa("sem scikit-learn: o relatório sai, a seção de ML explica o que instalar e os outros 4 gráficos existem", r.returncode == 0 and "pip install scikit-learn" in mds and len(list(sem_sk.glob("*.png"))) == 4)
print("\n=== 5) SEM O analise_energia.py ===")
tmp = Path(tempfile.mkdtemp(prefix="an_proj_")) / "p"; tmp.mkdir()
for f in ("analise_aprendizado.py", "ml_preparacao.py", "periodos.py"): shutil.copy(ARV / f, tmp / f)
sd = tmp / "saida"; r = subprocess.run([sys.executable, "analise_aprendizado.py", "--demo", "--saida", str(sd)], cwd=tmp, capture_output=True, text=True); mde = (sd / "relatorio_analise.md").read_text(encoding="utf-8") if (sd / "relatorio_analise.md").exists() else ""
checa("se o analise_energia.py não estiver na pasta: avisa, pula só a seção 2.3 e segue", r.returncode == 0 and "analise_energia.py não encontrado" in r.stdout and "foi pulada" in mde and "## 3. Machine Learning" in mde)
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
