"""
NEOCORTEX - verificar_lote1_1.py

Verifica, SEM banco e SEM navegador, os ajustes do lote 1.1 do aprendizado:
  1. ATUALIZAÇÃO AO LER: quem lê o aprendizado para sugerir (decisao._contexto_aprendido) garante antes que há um snapshot
     válido; se não há, recalcula (com trava de frequência) e nunca derruba a leitura;
  2. UMA SÓ DEFINIÇÃO de "snapshot vigente" no db.py;
  3. CATEGORIAS: tudo o que o recálculo publica, para TODAS as categorias que ele aprende, está na lista de chaves que o
     banco aceita (senão a publicação inteira falharia com ValueError).

Uso (na pasta do projeto): python verificar_lote1_1.py
"""
import ast
import logging
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(RAIZ))
db = types.ModuleType("db")
sys.modules["db"] = db
import aprendizado as ap   # noqa: E402
import decisao             # noqa: E402

if not hasattr(ap, "garantir_vigente"):
    print("FALHA o lote 1.1 não está aplicado: o aprendizado.py não tem a função garantir_vigente. Rode: python aplicar_patches.py")
    sys.exit(1)
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)

NOW = datetime(2026, 10, 20, 12)
print("=== 1) ATUALIZAÇÃO AO LER ===")
chamadas = []
ap.recalcular_aprendizado = lambda uid, agora=None: chamadas.append((uid, agora))
vigente = {"v": True}
db.aprendizado_vigente = lambda uid, agora=None: vigente["v"]
ap._ultima_tentativa.clear()
r = ap.garantir_vigente(1, NOW); checa("com snapshot válido: não recalcula e devolve False", r is False and chamadas == [])
vigente["v"] = False
r = ap.garantir_vigente(1, NOW); checa("sem snapshot válido (vencido, legado ou nunca calculado): recalcula uma vez e devolve True", r is True and chamadas == [(1, NOW)])
r = ap.garantir_vigente(1, NOW); checa("uma segunda leitura logo em seguida NÃO recalcula de novo (trava de frequência)", r is False and len(chamadas) == 1)
r2 = ap.garantir_vigente(2, NOW); checa("a trava é por pessoa: outra pessoa recalcula normalmente", r2 is True and len(chamadas) == 2)
ap._ultima_tentativa[1] -= ap.INTERVALO_MIN_TENTATIVAS_S + 1
r = ap.garantir_vigente(1, NOW); checa("passado o intervalo da trava, volta a poder recalcular", r is True and len(chamadas) == 3)
def quebra(uid, agora=None): raise RuntimeError("banco fora")
ap.recalcular_aprendizado = quebra; ap._ultima_tentativa.clear()
logging.disable(logging.CRITICAL)   # o log da falha esperada não precisa aparecer aqui
try: r = ap.garantir_vigente(3, NOW); erro = None
except Exception as e: erro = e
finally: logging.disable(logging.NOTSET)
checa("se o recálculo falhar, a leitura NÃO quebra (devolve False e registra no log)", erro is None and r is False)
ap.recalcular_aprendizado = lambda uid, agora=None: chamadas.append((uid, agora)); n = len(chamadas)
r = ap.garantir_vigente(3, NOW); checa("e uma falha não vira uma tempestade: a tentativa seguinte também espera a trava", r is False and len(chamadas) == n)
del db.aprendizado_vigente; ap._ultima_tentativa.clear()
try: r = ap.garantir_vigente(4, NOW); erro = None
except Exception as e: erro = e
checa("se não for possível verificar a vigência (banco sem a função/tabela), não recalcula e não quebra", erro is None and r is False and len(chamadas) == n)
print("\n=== 2) A DECISÃO GARANTE A VIGÊNCIA ANTES DE LER ===")
ordem = []
ap.garantir_vigente = lambda uid, agora=None: ordem.append("garantir")
db.listar_padroes = lambda uid: (ordem.append("padroes") or [])
db.listar_metricas = lambda uid: (ordem.append("metricas") or [])
decisao._contexto_aprendido(1)
checa("_contexto_aprendido garante a vigência ANTES de ler padrões e métricas (é por onde passam 'sugerir horários' e 'o que fazer agora')", ordem[:1] == ["garantir"] and set(ordem[1:]) == {"padroes", "metricas"})
fonte_db = (RAIZ / "db.py").read_bytes().decode("utf-8").replace("\r\n", "\n")
checa("db.py tem UMA definição de 'snapshot vigente' (aprendizado_vigente) e o filtro de leitura a usa", fonte_db.count("def aprendizado_vigente(") == 1 and "if aprendizado_vigente(id_usuario, agora):" in fonte_db and fonte_db.count("estado[\"calculado_em\"] <= agora < estado[\"valido_ate\"]") == 1)
print("\n=== 3) CATEGORIAS: o que o recálculo publica cabe na lista que o banco aceita ===")
arvore = ast.parse(fonte_db); espaco = {}
for no in arvore.body:
    if isinstance(no, ast.Assign) and getattr(no.targets[0], "id", "") in ("_PADROES_APRENDIZADO", "_METRICAS_APRENDIZADO"):
        exec(compile(ast.Module([no], []), "db.py", "exec"), espaco)
LISTA_P, LISTA_M = set(espaco["_PADROES_APRENDIZADO"]), set(espaco["_METRICAS_APRENDIZADO"])
checa(f"o db.py define as duas listas de chaves aceitas ({len(LISTA_P)} padrões, {len(LISTA_M)} métricas)", len(LISTA_P) > 0 and len(LISTA_M) > 0)
PERIODOS_H = {"manha": 9, "tarde": 14, "noite": 20}
tarefas, idt = [], 0
for cat in list(ap.CATEGORIAS_APRENDIDAS) + ["outro"]:
    for per, hora in PERIODOS_H.items():
        for k in range(6):
            idt += 1; dia = NOW.replace(hour=0) - timedelta(days=3 + (idt % 40)); ini = dia.replace(hour=hora)
            conc = (dia + timedelta(days=1)).replace(hour=9, minute=idt % 50)
            tarefas.append(dict(id_tarefa=idt, id_usuario=1, categoria=cat, status="concluida", data_inicio=ini, data_fim=ini + timedelta(hours=1), concluido_em=conc, criado_em=ini - timedelta(days=1), tempo_execucao_s=None))
publicado = []
import importlib; importlib.reload(ap)       # a versão de verdade (as anteriores foram trocadas por espiões)
ap.resolver_recomendacoes = lambda *a: {}
db.listar_tarefas_aprendizado = lambda *a: tarefas; db.listar_eventos_usuario = lambda *a, **k: []; db.obter_padrao = lambda *a: None
db.contar_resultados_recomendacoes = lambda *a, **k: {}; db.proxima_expiracao_resultados = lambda *a: None
db.publicar_aprendizado = lambda *a: publicado.append(a)
ap.recalcular_aprendizado(1, NOW)
padroes, metricas = publicado[-1][1], publicado[-1][2]
esperados_p = {f"periodo_conclusao_observado:{c}" for c in ap.CATEGORIAS_APRENDIDAS}
esperados_m = {f"taxa_conclusao_{c}_{p}" for c in ap.CATEGORIAS_APRENDIDAS for p in PERIODOS_H}
checa(f"o cenário exercita TODAS as categorias que o aprendizado conhece: {len(esperados_p & set(padroes))}/{len(esperados_p)} padrões e {len(esperados_m & set(metricas))}/{len(esperados_m)} taxas por categoria e período", esperados_p <= set(padroes) and esperados_m <= set(metricas))
checa(f"tudo o que foi publicado como PADRÃO está na lista do banco (fora dela: {sorted(set(padroes) - LISTA_P) or 'nada'})", set(padroes) <= LISTA_P)
checa(f"tudo o que foi publicado como MÉTRICA está na lista do banco (fora dela: {sorted(set(metricas) - LISTA_M) or 'nada'})", set(metricas) <= LISTA_M)
checa("a categoria 'outro' não ensina nada (nenhuma chave dela é publicada)", not any("outro" in k for k in list(padroes) + list(metricas)))
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
