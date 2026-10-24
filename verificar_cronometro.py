"""
NEOCORTEX - verificar_cronometro.py

Roda as verificações do cronômetro opcional SEM banco de dados e SEM Gemini (bancos de mentira e o banco falso do próprio projeto):
estado e tempo líquido (pausas, desfazer, esquecimento), começar/pausar/retomar/concluir, a transação no db.py, os pontos (que não
dependem de eventos), o aprendizado do ritmo real e a folga e a margem de preparo nas sugestões.

Uso (na pasta do projeto, venv ativado):
    python verificar_cronometro.py
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
PASTA = Path(__file__).resolve().parent / "verificacoes_cronometro"
SUITES = [('teste_cronometro.py', 'estado e tempo líquido'), ('teste_cron_servicos.py', 'serviços: começar, pausar, retomar, concluir'), ('teste_cron_db.py', 'banco: transação, hora e pontos'), ('teste_cron_aprendizado.py', 'aprendizado: o ritmo real'), ('teste_cron_decisao.py', 'decisão: folga e margem de preparo')]
falhou = False
for arquivo, nome in SUITES:
    r = subprocess.run([sys.executable, str(PASTA / arquivo), str(RAIZ)], capture_output=True, text=True, cwd=RAIZ)
    linhas = r.stdout.splitlines()
    ok, ruins = sum(1 for l in linhas if l.startswith("OK")), [l for l in linhas if l.startswith("FALHA")]
    status = "OK  " if r.returncode == 0 and not ruins else "ERRO"
    print(f"{status} {nome}: {ok} verificações" + (f", {len(ruins)} FALHA(S)" if ruins else ""))
    for l in ruins:
        print("       " + l[:200])
    if r.returncode != 0 and not ruins:
        print("       " + (r.stderr.strip().splitlines() or ["(sem detalhes)"])[-1][:200])
    falhou = falhou or r.returncode != 0 or bool(ruins)
print()
print("RESULTADO:", "TUDO CERTO" if not falhou else "HÁ FALHAS (veja acima)")
sys.exit(1 if falhou else 0)
