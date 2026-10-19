import sys, types, importlib.util, contextlib, os, logging, datetime as dt
from pathlib import Path
from unittest.mock import MagicMock
PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve(); sys.path.insert(0, str(PASTA))
for nome in ("psycopg2", "psycopg2.extras", "psycopg2.pool", "dotenv", "bcrypt"): sys.modules[nome] = MagicMock()
sys.modules["psycopg2.extras"].Json = lambda x: ("JSON", x); sys.modules["dotenv"].load_dotenv = lambda *a, **k: None
spec = importlib.util.spec_from_file_location("db", PASTA / "db.py"); db = importlib.util.module_from_spec(spec); sys.modules["db"] = db; spec.loader.exec_module(db)
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
def banco(status="pendente", existe=True, n_tarefas=3, n_obj=1, n_cron=4, falha_cron=False, falha_update=False):
    e = types.SimpleNamespace(sql=[], params=[])
    class Cur:
        rowcount = -1
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def execute(s, sql, params=None):
            q = " ".join(str(sql).split()); e.sql.append(q); e.params.append(params)
            if q.startswith("SELECT status FROM tarefas") and "FOR UPDATE" in q: s._f = {"status": status} if existe else None
            elif q.startswith("UPDATE tarefas SET status ="): s.rowcount = 1
            elif q.startswith("INSERT INTO eventos_execucao"): s.rowcount = 1
            elif q.startswith("SELECT LOCALTIMESTAMP"): s._f = {"agora": dt.datetime(2026, 10, 19, 9, 30)}
            elif q.startswith("UPDATE tarefas SET tempo_execucao_s"):
                if falha_update: raise RuntimeError('column "tempo_execucao_s" does not exist')
                s.rowcount = 1
            elif q.startswith("SELECT COUNT(*) AS n FROM tarefas WHERE id_usuario = %s AND status = 'concluida' AND tempo_execucao_s"):
                if falha_cron: raise RuntimeError('column "tempo_execucao_s" does not exist')
                s._f = {"n": n_cron}
            elif q.startswith("SELECT COUNT(*) AS n FROM tarefas WHERE id_usuario = %s AND status = 'concluida'"): s._f = {"n": n_tarefas}
            elif q.startswith("SELECT COUNT(*) AS n FROM objetivos"): s._f = {"n": n_obj}
            else: raise AssertionError("comando inesperado: " + q[:90])
        def fetchone(s): return s._f
    class Conn:
        def cursor(s): return Cur()
    @contextlib.contextmanager
    def conectar(): yield Conn()
    db.conectar = conectar; return e
print("=== registrar_evento_cronometro (a transação do cronômetro) ===")
e = banco("pendente"); r = db.registrar_evento_cronometro(5, 1, "iniciou", "em_andamento")
checa("começar uma tarefa PENDENTE: trava a linha (FOR UPDATE), muda o status para em_andamento e grava o evento 'iniciou', tudo junto", r is True and "FOR UPDATE" in e.sql[0] and e.params[0] == (5, 1) and e.sql[1].startswith("UPDATE tarefas SET status =") and e.params[1] == ("em_andamento", 5, 1) and e.sql[2].startswith("INSERT INTO eventos_execucao") and e.params[2][:2] == (5, "iniciou") and len(e.sql) == 3)
e = banco("em_andamento"); r = db.registrar_evento_cronometro(5, 1, "retomou", "em_andamento"); checa("retomar uma tarefa que JÁ está em andamento: só grava o evento, sem UPDATE desnecessário", r is True and [q.split()[0] for q in e.sql] == ["SELECT", "INSERT"])
e = banco("em_andamento"); r = db.registrar_evento_cronometro(5, 1, "pausou"); checa("pausar (sem novo status): só o evento 'pausou'", r is True and [q.split()[0] for q in e.sql] == ["SELECT", "INSERT"] and e.params[1][1] == "pausou")
for st in ("concluida", "cancelada"):
    e = banco(st); r = db.registrar_evento_cronometro(5, 1, "iniciou", "em_andamento"); checa(f"tarefa {st}: devolve None e NÃO grava nada (nem status, nem evento)", r is None and len(e.sql) == 1)
e = banco(existe=False); r = db.registrar_evento_cronometro(5, 2, "iniciou", "em_andamento"); checa("tarefa que não existe OU é de outra pessoa (a consulta é filtrada pelo usuário): None, sem gravar", r is None and len(e.sql) == 1 and e.params[0] == (5, 2) and "id_usuario = %s" in e.sql[0])
print("\n=== a hora do banco e o tempo guardado ===")
e = banco(); r = db.agora_do_banco(); checa("agora_do_banco devolve a hora que o BANCO informa (a mesma dos eventos)", r == dt.datetime(2026, 10, 19, 9, 30))
e = banco(); r = db.salvar_tempo_execucao(5, 1, 1499.7); checa("guardar o tempo: número inteiro de segundos, filtrado pelo usuário", r == 1 and e.params[0] == (1499, 5, 1) and "id_usuario = %s" in e.sql[0])
e = banco(); db.salvar_tempo_execucao(5, 1, None); checa("limpar o tempo (None) grava NULL", e.params[0] == (None, 5, 1))
logs = []; h = logging.Handler(); h.emit = lambda rec: logs.append(rec.getMessage()); logging.getLogger("neocortex.db").addHandler(h)
db._AVISOU_MIGRACAO_CRONOMETRO = False; banco(falha_update=True)
r = [db.salvar_tempo_execucao(5, 1, 600) for _ in range(3)]; checa("coluna ausente (migração não rodada): devolve 0 sem erro e AVISA UMA VEZ no log, citando o arquivo da migração (sem encher o log)", r == [0, 0, 0] and len(logs) == 1 and "neocortex_cronometro_migracao.sql" in logs[0])
print("\n=== pontos: o incentivo não pode depender de eventos ===")
banco(n_tarefas=3, n_obj=1, n_cron=0); base = db.calcular_pontos_mascote(1); checa(f"sem nenhuma tarefa cronometrada, os pontos são os de sempre: 3 tarefas x 10 + 1 objetivo x 50 = {base}", base == 80)
e = banco(n_tarefas=3, n_obj=1, n_cron=4); p = db.calcular_pontos_mascote(1); checa(f"com 4 tarefas cronometradas: +5 cada = {p}", p == 100)
q = next(s for s in e.sql if "tempo_execucao_s" in s); i = e.sql.index(q)
checa("a consulta dos pontos usa SÓ a tabela de tarefas (tempo guardado na conclusão): NÃO lê eventos_execucao, que a retenção apaga com 75 dias", "eventos_execucao" not in q and "FROM tarefas" in q)
checa("e só conta tarefas CONCLUÍDAS, DA PESSOA, com pelo menos 180 s guardados", "status = 'concluida'" in q and "id_usuario = %s" in q and e.params[i] == (1, 180))
db._AVISOU_MIGRACAO_CRONOMETRO = False; banco(n_tarefas=3, n_obj=1, falha_cron=True); p = db.calcular_pontos_mascote(1); checa("sem a coluna nova, os pontos continuam funcionando como antes (80) e a página NÃO quebra", p == 80)
src = Path(PASTA / "db.py").read_text(encoding="utf-8"); checa("o evento 'iniciou' não aparece em nenhuma regra de pontos do db.py (nada de pontos dependendo do que é apagado)", "tipo_evento = 'iniciou'" not in src[src.index("def calcular_pontos_mascote"):])
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
