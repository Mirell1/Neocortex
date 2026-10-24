import sys, os, types
from datetime import datetime, timedelta
ARV = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "."); os.chdir(ARV); sys.path.insert(0, ARV)
falhas = []
def checa(d, c):
    print(("OK   " if c else "FALHA"), d)
    if not c: falhas.append(d)
class Banco(types.ModuleType):
    """Banco em memória com as MESMAS regras do real: o evento do cronômetro só é gravado se a tarefa for do usuário e estiver aberta."""
    def __init__(s):
        super().__init__("db"); s.agora = datetime(2026, 10, 19, 9, 0); s.t, s.ev, s.tempos, s.salvar_falha, s.eventos_falha, s.n = {}, [], {}, False, False, 0
    def avancar(s, min_): s.agora += timedelta(minutes=min_)
    def criar(s, i, uid=1, titulo=None, status="pendente", dur=60):
        s.t[i] = {"id_tarefa": i, "id_usuario": uid, "titulo": titulo or f"Tarefa {i}", "status": status, "data_inicio": datetime(2026, 10, 19, 9), "data_fim": datetime(2026, 10, 19, 9) + timedelta(minutes=dur), "categoria": "estudo"}
    def _ev(s, i, tipo): s.n += 1; s.ev.append({"id_evento": s.n, "id_tarefa": i, "tipo_evento": tipo, "data_hora": s.agora})
    def tipos(s, i): return [e["tipo_evento"] for e in s.ev if e["id_tarefa"] == i]
    def buscar_tarefa(s, i, uid): t = s.t.get(i); return dict(t) if t and t["id_usuario"] == uid else None
    def listar_eventos_execucao(s, i, uid):
        if s.eventos_falha: raise RuntimeError("banco fora")
        return [dict(e) for e in sorted(s.ev, key=lambda e: -e["id_evento"]) if e["id_tarefa"] == i and s.t[i]["id_usuario"] == uid]
    def listar_tarefas_abertas(s, uid, data_fim_minima=None, limite=200): return [dict(t) for t in s.t.values() if t["id_usuario"] == uid and t["status"] in ("pendente", "em_andamento")]
    def registrar_evento_cronometro(s, i, uid, tipo, novo_status=None):
        t = s.t.get(i)
        if not t or t["id_usuario"] != uid or t["status"] not in ("pendente", "em_andamento"): return None
        if novo_status and t["status"] != novo_status: t["status"] = novo_status
        s._ev(i, tipo); return True
    def marcar_tarefa_concluida(s, i, uid):
        t = s.t.get(i)
        if not t or t["id_usuario"] != uid: return 0
        if t["status"] == "concluida": return 1
        t["status"] = "concluida"; t["concluido_em"] = s.agora; s._ev(i, "concluiu"); return 1
    def desfazer_conclusao_tarefa(s, i, uid): s.t[i]["status"] = "pendente"; s._ev(i, "desfez_conclusao"); return 1
    def salvar_tempo_execucao(s, i, uid, seg):
        if s.salvar_falha: raise RuntimeError("coluna não existe")
        s.tempos[i] = seg; return 1
    def agora_do_banco(s): return s.agora
db = Banco(); sys.modules["db"] = db
import servicos
servicos._atualizar_aprendizado = lambda uid: None
def novo(*ids, **kw): db.__init__(); [db.criar(i, **kw) for i in ids]
print("=== começar, pausar e retomar ===")
novo(1); r = servicos.iniciar_tarefa(1, 1); e = servicos.estado_do_cronometro(1, 1)
checa("começar: a tarefa passa a 'em andamento', grava o evento 'iniciou' e o cronômetro roda", r["sucesso"] and r["evento"] == "iniciou" and db.t[1]["status"] == "em_andamento" and db.tipos(1) == ["iniciou"] and e["estado"] == "rodando")
db.avancar(5); checa("passados 5 min, o cronômetro marca 5 min", servicos.estado_do_cronometro(1, 1)["acumulado_s"] == 300)
r = servicos.iniciar_tarefa(1, 1); checa("começar de novo (duplo clique) é recusado com mensagem clara e NÃO grava outro evento", not r["sucesso"] and "já está rodando" in r["erro"] and db.tipos(1) == ["iniciou"])
r = servicos.pausar_tarefa(1, 1); db.avancar(30); e = servicos.estado_do_cronometro(1, 1)
checa("pausar: o tempo PARA (5 min, mesmo depois de 30 min parado) e a tarefa continua 'em andamento'", r["sucesso"] and e["estado"] == "pausado" and e["acumulado_s"] == 300 and db.t[1]["status"] == "em_andamento")
r = servicos.pausar_tarefa(1, 1); checa("pausar o que já está pausado: recusado", not r["sucesso"] and "não está rodando" in r["erro"])
r = servicos.iniciar_tarefa(1, 1); checa("'Começar' numa tarefa pausada RETOMA (evento 'retomou'), sem reiniciar o tempo", r["sucesso"] and r["evento"] == "retomou" and servicos.estado_do_cronometro(1, 1)["acumulado_s"] == 300)
r = servicos.retomar_tarefa(1, 1); checa("retomar o que já está rodando: recusado", not r["sucesso"] and "não está pausada" in r["erro"])
servicos.pausar_tarefa(1, 1); r = servicos.retomar_tarefa(1, 1); checa("pausar e retomar de verdade: volta a rodar", r["sucesso"] and servicos.estado_do_cronometro(1, 1)["estado"] == "rodando")
print("\n=== só UM cronômetro roda por vez ===")
novo(1, 2); servicos.iniciar_tarefa(1, 1); db.avancar(10); r = servicos.iniciar_tarefa(1, 2)
checa("começar a tarefa 2 PAUSA a tarefa 1, avisa quem foi pausada e a 2 roda", r["pausadas"] == ["Tarefa 1"] and servicos.estado_do_cronometro(1, 1)["estado"] == "pausado" and servicos.estado_do_cronometro(1, 2)["estado"] == "rodando" and db.tipos(1) == ["iniciou", "pausou"])
checa("o tempo da tarefa 1 ficou congelado nos 10 min que ela rodou", servicos.estado_do_cronometro(1, 1)["acumulado_s"] == 600)
db.avancar(5); servicos.pausar_tarefa(1, 2); r = servicos.iniciar_tarefa(1, 1); checa("se a outra já estava pausada, nada é pausado de novo (sem aviso)", r["pausadas"] == [] and db.tipos(2) == ["iniciou", "pausou"])
novo(1, 2); servicos.iniciar_tarefa(1, 1); servicos.iniciar_tarefa(1, 2); servicos.retomar_tarefa(1, 1); checa("retomar também pausa a que estava rodando (nunca dois cronômetros juntos)", servicos.estado_do_cronometro(1, 2)["estado"] == "pausado" and servicos.estado_do_cronometro(1, 1)["estado"] == "rodando")
print("\n=== isolamento e estados que não permitem cronômetro ===")
novo(1); db.criar(7, uid=2); r = servicos.iniciar_tarefa(1, 7); checa("tarefa de OUTRA pessoa: 'não encontrada' e nenhum evento gravado nela", r.get("nao_encontrada") and db.tipos(7) == [])
r = servicos.iniciar_tarefa(1, 99); checa("tarefa que não existe: 'não encontrada'", r.get("nao_encontrada"))
db.criar(3, status="concluida"); db.criar(4, status="cancelada")
r3, r4 = servicos.iniciar_tarefa(1, 3), servicos.iniciar_tarefa(1, 4); checa("tarefa concluída ou cancelada não pode ser cronometrada (mensagens claras)", "já está concluída" in r3["erro"] and "cancelada" in r4["erro"] and db.tipos(3) == [] and db.tipos(4) == [])
print("\n=== concluir: tempo real, pontos e o que NÃO acontece sem o cronômetro ===")
novo(1, dur=60); servicos.iniciar_tarefa(1, 1); db.avancar(25); r = servicos.concluir_tarefa(1, 1); c = r["cronometro"]
checa("concluir depois de 25 min: devolve o tempo real (1500 s), o previsto (60 min), o bônus e os 5 pontos", r["sucesso"] and c["real_s"] == 1500 and c["previsto_min"] == 60 and c["bonus"] and c["pontos"] == 5)
checa("o tempo executado fica GUARDADO na tarefa (é a base dos pontos, que não podem sumir quando os eventos antigos forem apagados)", db.tempos[1] == 1500)
novo(1); servicos.iniciar_tarefa(1, 1); db.avancar(2); r = servicos.concluir_tarefa(1, 1); checa("concluir com só 2 min: tempo real é informado, mas SEM bônus (evita clicar Começar e Concluir em seguida) e nada fica guardado", r["cronometro"]["real_s"] == 120 and not r["cronometro"]["bonus"] and r["cronometro"]["pontos"] == 0 and db.tempos[1] is None)
novo(1); r = servicos.concluir_tarefa(1, 1); checa("concluir SEM ter usado o cronômetro: funciona como sempre, sem aviso de tempo e sem guardar nada (nada é cobrado de quem não usa)", r["sucesso"] and "cronometro" not in r and 1 not in db.tempos)
novo(1); servicos.iniciar_tarefa(1, 1); db.avancar(10); servicos.pausar_tarefa(1, 1); db.avancar(120); servicos.retomar_tarefa(1, 1); db.avancar(15); r = servicos.concluir_tarefa(1, 1)
checa("com pausa de 2 h no meio: conta só 25 min (10 + 15)", r["cronometro"]["real_s"] == 1500)
novo(1); servicos.iniciar_tarefa(1, 1); db.avancar(20); servicos.concluir_tarefa(1, 1); r = servicos.concluir_tarefa(1, 1); checa("duplo clique em concluir: mesmo resultado, sem duplicar nada", r["sucesso"] and r["cronometro"]["real_s"] == 1200 and db.tipos(1).count("concluiu") == 1 and db.tempos[1] == 1200)
novo(1); servicos.iniciar_tarefa(1, 1); db.avancar(30); servicos.concluir_tarefa(1, 1); r = servicos.desfazer_conclusao(1, 1)
checa("desfazer a conclusão limpa o tempo guardado e a tarefa volta a 'pendente'", r["sucesso"] and db.tempos[1] is None and db.t[1]["status"] == "pendente" and servicos.estado_do_cronometro(1, 1)["estado"] == "parado")
r = servicos.concluir_tarefa(1, 1); checa("concluir de novo sem cronômetro depois de desfazer: sem tempo (o ciclo antigo foi apagado)", "cronometro" not in r)
print("\n=== o cronômetro nunca derruba a conclusão ===")
novo(1); servicos.iniciar_tarefa(1, 1); db.avancar(20); db.salvar_falha = True; r = servicos.concluir_tarefa(1, 1); checa("coluna do banco ausente (migração não rodada): a tarefa É concluída, sem erro para a pessoa", r["sucesso"] and db.t[1]["status"] == "concluida")
novo(1); servicos.iniciar_tarefa(1, 1); db.avancar(20); db.eventos_falha = True; r = servicos.concluir_tarefa(1, 1); checa("banco de eventos fora do ar na hora de fechar: a tarefa É concluída, só sem o aviso de tempo", r["sucesso"] and db.t[1]["status"] == "concluida" and "cronometro" not in r)
print("\n=== o relógio ===")
db.agora_do_banco = lambda: (_ for _ in ()).throw(RuntimeError("sem relógio")); h = servicos.hora_do_cronometro(); checa("se não der para ler a hora do banco, usa a do servidor (não quebra)", isinstance(h, datetime))
print("\nRESULTADO:", "TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {falhas}")
sys.exit(1 if falhas else 0)
