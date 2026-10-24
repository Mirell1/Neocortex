"""
Testes do Lote 1: agenda.py, servicos.py, decisao.py e roteador.py.

Não precisam de PostgreSQL nem de Gemini: o módulo 'db' é trocado por um banco
falso em memória. Rodam com  pytest test_agenda_servicos.py  ou  python test_agenda_servicos.py
"""

import os
import sys
import time
import types
from datetime import datetime, timedelta

os.environ["APRENDIZADO_ATRASO_S"] = "0"   # recálculo imediato (cada teste muda quando precisa)


# ============================================================
# BANCO FALSO (só o que agenda/servicos/decisao usam)
# ============================================================
class BancoFalso(types.ModuleType):
    def __init__(self):
        super().__init__("db")
        self.limpar()

    def limpar(self):
        self.tarefas, self.compromissos, self.rotinas = {}, {}, {}
        self.restricoes, self.disponibilidades = [], []
        self.padroes, self.metricas, self.decisoes, self.recomendacoes = [], [], [], []
        self.consultas = 0
        self._id = 0

    def _novo_id(self):
        self._id += 1
        return self._id

    @staticmethod
    def _dt(valor):
        return valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))

    # --- leituras da agenda (cada chamada conta como uma consulta)
    def listar_tarefas_janela(self, uid, inicio, fim, status=None):
        self.consultas += 1
        return [dict(t) for t in self.tarefas.values() if t["id_usuario"] == uid
                and t["data_inicio"] < fim and t["data_fim"] > inicio
                and (t["status"] == status if status else t["status"] != "cancelada")]

    def listar_compromissos_janela(self, uid, inicio, fim):
        self.consultas += 1
        return [dict(c) for c in self.compromissos.values() if c["id_usuario"] == uid
                and c["data_inicio"] < fim and c["data_fim"] > inicio]

    def listar_rotina(self, uid, dia_semana=None):
        self.consultas += 1
        return [dict(r) for r in self.rotinas.values() if r["id_usuario"] == uid
                and (dia_semana is None or r["dia_semana"] == dia_semana)]

    def listar_restricoes(self, uid):
        self.consultas += 1
        return list(self.restricoes)

    def listar_disponibilidades(self, uid):
        self.consultas += 1
        return list(self.disponibilidades)

    # --- tarefas
    def criar_tarefa(self, uid, titulo, inicio, fim, categoria=None, descricao=None, origem="manual"):
        i = self._novo_id()
        self.tarefas[i] = {"id_tarefa": i, "id_usuario": uid, "titulo": titulo, "categoria": categoria,
                           "data_inicio": self._dt(inicio), "data_fim": self._dt(fim), "status": "pendente",
                           "concluido_em": None, "cor": None}
        return i

    def buscar_tarefa(self, id_tarefa, uid):
        t = self.tarefas.get(id_tarefa)
        return dict(t) if t and t["id_usuario"] == uid else None

    def atualizar_tarefa(self, id_tarefa, uid, **campos):
        t = self.tarefas.get(id_tarefa)
        if not t or t["id_usuario"] != uid:
            return 0
        for k, v in campos.items():
            t[k] = self._dt(v) if k in ("data_inicio", "data_fim") else v
        return 1

    def cancelar_tarefa(self, id_tarefa, uid):
        return self.atualizar_tarefa(id_tarefa, uid, status="cancelada")

    def marcar_tarefa_concluida(self, id_tarefa, uid):
        return self.atualizar_tarefa(id_tarefa, uid, status="concluida")

    def desfazer_conclusao_tarefa(self, id_tarefa, uid):
        return self.atualizar_tarefa(id_tarefa, uid, status="pendente")

    def deletar_tarefa(self, id_tarefa, uid):
        return 1 if self.tarefas.pop(id_tarefa, None) else 0

    def listar_tarefas_abertas(self, uid, data_fim_minima=None, limite=200):
        return sorted((dict(t) for t in self.tarefas.values() if t["id_usuario"] == uid
                       and t["status"] in ("pendente", "em_andamento")
                       and (data_fim_minima is None or t["data_fim"] >= data_fim_minima)),
                      key=lambda t: t["data_inicio"])

    def enriquecer_tarefas(self, uid, tarefas):
        for t in tarefas:
            t.setdefault("prioridade", None)
            t.setdefault("objetivo_prazo", None)
            t.setdefault("dependencia_pendente", False)
        return tarefas

    # --- compromissos e rotina
    def criar_compromisso(self, uid, titulo, inicio, fim, tipo="outro", local=None):
        i = self._novo_id()
        self.compromissos[i] = {"id_compromisso": i, "id_usuario": uid, "titulo": titulo, "tipo": tipo,
                                "data_inicio": self._dt(inicio), "data_fim": self._dt(fim), "local": local}
        return i

    def adicionar_rotina(self, uid, dia, descricao, inicio, fim):
        i = self._novo_id()
        self.rotinas[i] = {"id_rotina": i, "id_usuario": uid, "dia_semana": dia, "descricao": descricao,
                           "hora_inicio": inicio, "hora_fim": fim}
        return i

    def atualizar_rotina(self, id_rotina, uid, **campos):
        self.rotinas[id_rotina].update(campos)
        return 1

    # --- decisão / aprendizado
    def listar_padroes(self, uid):
        return list(self.padroes)

    def listar_metricas(self, uid):
        return list(self.metricas)

    def listar_decisoes(self, uid, limite=None):
        return list(reversed(self.decisoes))[: limite or None]

    def salvar_decisao(self, uid, contexto, criterios, decisao):
        i = self._novo_id()
        self.decisoes.append({"id_decisao": i, "decisao_tomada": decisao, "criado_em": datetime.now()})
        return i

    def buscar_recomendacao_aberta_recente(self, uid, id_tarefa, tipo, horas=2):
        return None

    def registrar_decisao_com_recomendacao(self, uid, contexto, criterios, decisao, texto, id_tarefa=None, tipo="geral"):
        return self._novo_id(), self._novo_id()

    def salvar_recomendacao(self, *a, **k):
        return self._novo_id()

    def _como_datetime(self, valor):
        return self._dt(valor)


banco = BancoFalso()
sys.modules["db"] = banco

import agenda      # noqa: E402
import aprendizado  # noqa: E402
import decisao     # noqa: E402
import roteador    # noqa: E402
import servicos    # noqa: E402

# 2026-10-05 é uma segunda-feira
SEGUNDA = datetime(2026, 10, 5)
CHAMADAS_APRENDIZADO = []
aprendizado.apos_evento = lambda uid: CHAMADAS_APRENDIZADO.append(uid)


def novo_cenario():
    banco.limpar()
    CHAMADAS_APRENDIZADO.clear()
    os.environ["APRENDIZADO_ATRASO_S"] = "0"


def em(dia, h, m=0):
    return dia.replace(hour=h, minute=m)


# ============================================================
# AGENDA
# ============================================================
def test_conflito_com_tarefa_existente():
    novo_cenario()
    banco.criar_tarefa(1, "Reunião", em(SEGUNDA, 10), em(SEGUNDA, 11))
    achados = agenda.conflitos_para(1, em(SEGUNDA, 10, 30), em(SEGUNDA, 11, 30))
    assert [(c["tipo"], c["titulo"]) for c in achados] == [("tarefa", "Reunião")]
    assert agenda.conflitos_para(1, em(SEGUNDA, 11), em(SEGUNDA, 12)) == []   # encostar não é conflito


def test_tarefa_de_trabalho_dentro_do_turno_nao_conflita_mas_outra_categoria_sim():
    novo_cenario()
    banco.adicionar_rotina(1, "segunda", "Trabalho", "09:00", "18:00")
    assert agenda.conflitos_para(1, em(SEGUNDA, 10), em(SEGUNDA, 11), categoria="trabalho") == []
    assert [c["tipo"] for c in agenda.conflitos_para(1, em(SEGUNDA, 10), em(SEGUNDA, 11), categoria="estudo")] == ["rotina"]


def test_turno_que_vira_a_noite_aparece_uma_vez_so_mesmo_em_intervalo_de_varios_dias():
    novo_cenario()
    banco.adicionar_rotina(1, "domingo", "Plantão", "22:00", "06:00")
    domingo = SEGUNDA - timedelta(days=1)
    achados = agenda.conflitos_para(1, em(domingo, 20), em(SEGUNDA, 8))
    assert len(achados) == 1 and achados[0]["titulo"] == "Plantão"
    assert len(agenda.conflitos_para(1, em(SEGUNDA, 2), em(SEGUNDA, 3))) == 1


def test_conflitos_de_varios_dias_carregam_o_intervalo_uma_vez():
    novo_cenario()
    banco.criar_tarefa(1, "X", em(SEGUNDA, 10), em(SEGUNDA, 11))
    banco.consultas = 0
    agenda.conflitos_para(1, em(SEGUNDA, 8), em(SEGUNDA + timedelta(days=4), 20))
    assert banco.consultas == 5, "antes eram ~6 consultas POR DIA"


def test_situacao_agora_ocupado_pelo_bloco_de_rotina():
    novo_cenario()
    banco.adicionar_rotina(1, "segunda", "Trabalho", "09:00", "18:00")
    s = agenda.situacao_agora(1, em(SEGUNDA, 10))
    assert s["atual"]["tipo"] == "rotina" and s["atual"]["titulo"] == "Trabalho"
    livre = agenda.situacao_agora(1, em(SEGUNDA, 7))
    assert livre["atual"] is None and livre["minutos_livres_ate_proximo"] == 120


def test_normalizar_periodo_aceita_formato_antigo_do_cadastro():
    assert agenda.normalizar_periodo("Manhã") == "manha"
    assert agenda.normalizar_periodo(" NOITE ") == "noite"
    assert agenda.normalizar_periodo("nao_sei") is None and agenda.normalizar_periodo(None) is None


def test_eventos_por_dia_distribui_item_que_atravessa_dias():
    novo_cenario()
    banco.criar_compromisso(1, "Viagem", em(SEGUNDA, 20), em(SEGUNDA + timedelta(days=1), 8))
    carregada = agenda.carregar_agenda(1, SEGUNDA, SEGUNDA + timedelta(days=7))
    por_dia = agenda.eventos_por_dia(carregada, SEGUNDA.date(), (SEGUNDA + timedelta(days=7)).date())
    assert sorted(por_dia) == [SEGUNDA.date(), (SEGUNDA + timedelta(days=1)).date()]


# ============================================================
# DECISÃO — a regra de "ocupado" é a mesma do conflito
# ============================================================
def test_tarefa_de_trabalho_e_recomendada_durante_o_turno_de_trabalho():
    novo_cenario()
    banco.adicionar_rotina(1, "segunda", "Trabalho", "09:00", "18:00")
    id_t = banco.criar_tarefa(1, "Relatório", em(SEGUNDA, 10), em(SEGUNDA, 12), categoria="trabalho")
    r = decisao.recomendar_tarefa_agora(1, agora=em(SEGUNDA, 10, 30))
    assert r["recomendada"] == id_t


def test_tarefa_de_outra_categoria_nao_e_recomendada_durante_o_turno():
    novo_cenario()
    banco.adicionar_rotina(1, "segunda", "Trabalho", "09:00", "18:00")
    banco.criar_tarefa(1, "Violão", em(SEGUNDA, 10), em(SEGUNDA, 12), categoria="hobby")
    r = decisao.recomendar_tarefa_agora(1, agora=em(SEGUNDA, 10, 30))
    assert "recomendada" not in r and r["ocupado_agora_com"]["titulo"] == "Trabalho"


def test_energia_declarada_no_formato_antigo_pontua_o_periodo():
    novo_cenario()
    banco.padroes = [{"tipo_padrao": "energia", "valor": "Manhã"}]
    sugestoes = decisao.sugerir_horarios(1, SEGUNDA.date(), 60, agora=em(SEGUNDA, 6))["sugestoes"]
    assert sugestoes and all(s["periodo"] == "manha" for s in sugestoes)
    assert "período de energia que você declarou" in sugestoes[0]["base"]


def test_compromisso_fixo_bloqueia_recomendar_tarefa_no_mesmo_horario():
    novo_cenario()
    banco.criar_compromisso(1, "Dentista", em(SEGUNDA, 10), em(SEGUNDA, 11))
    banco.criar_tarefa(1, "Violão", em(SEGUNDA, 10), em(SEGUNDA, 12), categoria="hobby")
    r = decisao.recomendar_tarefa_agora(1, agora=em(SEGUNDA, 10, 30))
    assert "recomendada" not in r and r["ocupado_agora_com"]["titulo"] == "Dentista"


# ============================================================
# SERVIÇOS
# ============================================================
def test_criar_tarefa_com_conflito_pede_confirmacao_e_depois_cria():
    novo_cenario()
    banco.criar_compromisso(1, "Dentista", em(SEGUNDA, 15), em(SEGUNDA, 16))
    r = servicos.criar_tarefa(1, "Estudar", "2026-10-05T15:30", "2026-10-05T16:30")
    assert r["sucesso"] is False and r["conflitos"][0]["titulo"] == "Dentista"
    assert "Dentista (05/10 15:00–16:00)" in servicos.descrever_conflitos(r["conflitos"])
    assert not banco.tarefas
    ok = servicos.criar_tarefa(1, "Estudar", "2026-10-05T15:30", "2026-10-05T16:30", confirmar_conflito=True)
    assert ok["sucesso"] and len(banco.tarefas) == 1 and ok["conflitos_ignorados_com_confirmacao"]


def test_criar_tarefa_sem_fim_assume_uma_hora_e_valida_dados():
    novo_cenario()
    r = servicos.criar_tarefa(1, "  Ler  ", "2026-10-05T09:00")
    assert r["titulo"] == "Ler" and r["duracao_assumida_min"] == 60 and r["fim"] == "2026-10-05T10:00"
    for chamada in (lambda: servicos.criar_tarefa(1, "", "2026-10-05T09:00"),
                    lambda: servicos.criar_tarefa(1, "X", "lixo"),
                    lambda: servicos.criar_tarefa(1, "X", "2026-10-05T09:00", "2026-10-05T08:00")):
        try:
            chamada()
            assert False, "deveria levantar ValueError"
        except ValueError:
            pass


def test_categoria_invalida_vira_none_em_vez_de_quebrar_o_check_do_banco():
    novo_cenario()
    servicos.criar_tarefa(1, "A", "2026-10-05T09:00", categoria="")
    assert list(banco.tarefas.values())[0]["categoria"] is None


def test_editar_so_o_titulo_de_tarefa_ja_conflitante_nao_e_bloqueado():
    novo_cenario()
    banco.criar_tarefa(1, "A", em(SEGUNDA, 10), em(SEGUNDA, 11))
    id_b = banco.criar_tarefa(1, "B", em(SEGUNDA, 10, 30), em(SEGUNDA, 11, 30))   # já conflita com A
    r = servicos.atualizar_tarefa(1, id_b, titulo="B2", data_inicio="2026-10-05T10:30", data_fim="2026-10-05T11:30")
    assert r["sucesso"] and banco.tarefas[id_b]["titulo"] == "B2"
    assert CHAMADAS_APRENDIZADO == [1]


def test_mover_tarefa_para_horario_ocupado_pede_confirmacao_e_ignora_a_propria_tarefa():
    novo_cenario()
    banco.criar_tarefa(1, "A", em(SEGUNDA, 10), em(SEGUNDA, 11))
    id_b = banco.criar_tarefa(1, "B", em(SEGUNDA, 14), em(SEGUNDA, 15))
    r = servicos.atualizar_tarefa(1, id_b, data_inicio="2026-10-05T10:30")
    assert r["sucesso"] is False and r["conflitos"][0]["titulo"] == "A"
    ok = servicos.atualizar_tarefa(1, id_b, data_inicio="2026-10-05T14:30")   # só ele mesmo no lugar: livre
    assert ok["sucesso"] and ok["novo_fim"] == "2026-10-05T15:30", "mantém a duração"


def test_nada_a_alterar_e_marcado_como_sem_mudanca():
    novo_cenario()
    id_a = banco.criar_tarefa(1, "A", em(SEGUNDA, 10), em(SEGUNDA, 11))
    r = servicos.atualizar_tarefa(1, id_a)
    assert r["sucesso"] is False and r["sem_mudanca"] is True


def test_usuario_nao_mexe_na_tarefa_de_outro():
    novo_cenario()
    id_a = banco.criar_tarefa(1, "A", em(SEGUNDA, 10), em(SEGUNDA, 11))
    for r in (servicos.concluir_tarefa(2, id_a), servicos.cancelar_tarefa(2, id_a),
              servicos.excluir_tarefa(2, id_a), servicos.atualizar_tarefa(2, id_a, titulo="hack")):
        assert r["nao_encontrada"] is True
    assert banco.tarefas[id_a]["status"] == "pendente" and banco.tarefas[id_a]["titulo"] == "A"


def test_concluir_cancelar_desfazer_respeitam_o_estado():
    novo_cenario()
    id_a = banco.criar_tarefa(1, "A", em(SEGUNDA, 10), em(SEGUNDA, 11))
    assert servicos.desfazer_conclusao(1, id_a)["sucesso"] is False          # não estava concluída
    assert servicos.concluir_tarefa(1, id_a)["sucesso"]
    assert servicos.desfazer_conclusao(1, id_a)["sucesso"]
    assert servicos.cancelar_tarefa(1, id_a)["sucesso"]
    assert servicos.concluir_tarefa(1, id_a)["erro"] == "Essa tarefa está cancelada."


def test_rotina_cria_atualiza_sem_duplicar_e_nao_funde_atividades_diferentes():
    novo_cenario()
    r1 = servicos.configurar_rotina(1, "Estudo", "19:00", "21:00", ["segunda", "terça"])
    assert r1["dias_criados"] == 2 and r1["dias_semana"] == ["segunda", "terca"]
    r2 = servicos.configurar_rotina(1, "estudo", "20:00", "22:00", "segunda")
    assert r2["dias_atualizados"] == 1 and len(banco.rotinas) == 2
    servicos.configurar_rotina(1, "Estudo inglês", "08:00", "09:00", ["segunda"])
    assert len(banco.rotinas) == 3, "'Estudo inglês' é outra atividade, não atualiza 'Estudo'"


def test_rotina_aceita_turno_da_noite_mas_recusa_horario_invertido_de_dia():
    novo_cenario()
    assert servicos.configurar_rotina(1, "Plantão", "22:00", "06:00", ["sexta"])["sucesso"]
    for ini, fim in (("17:00", "09:00"), ("20:00", "15:00"), ("10:00", "10:00"), ("14:00", "13:00")):
        try:
            servicos.configurar_rotina(1, "X", ini, fim, ["sexta"])
            assert False, (ini, fim)
        except ValueError:
            pass
    assert servicos.parse_hhmm("9:5") == "09:05"


def test_aprendizado_em_rajada_vira_um_recalculo_so():
    novo_cenario()
    os.environ["APRENDIZADO_ATRASO_S"] = "0.15"
    ids = [banco.criar_tarefa(1, f"T{i}", em(SEGUNDA, 8 + i), em(SEGUNDA, 9 + i)) for i in range(3)]
    for i in ids:
        servicos.concluir_tarefa(1, i)
    assert CHAMADAS_APRENDIZADO == [], "ainda esperando para agrupar"
    time.sleep(0.5)
    assert CHAMADAS_APRENDIZADO == [1]


# ============================================================
# ROTEADOR
# ============================================================
def test_pedidos_com_verbo_de_agenda_nao_caem_em_conversa():
    for frase in ("adia o dentista pra amanhã", "terminei a academia", "anota ligar pro João",
                  "marca dentista sexta", "bota estudar inglês 19h", "cancela a reunião",
                  "coloca natação na segunda"):
        assert roteador.classificar(frase).modo == "interpretar", frase


def test_conversa_de_verdade_continua_sendo_conversa():
    for frase in ("me conta uma piada", "estou me sentindo cansado", "o que você acha de meditação"):
        assert roteador.classificar(frase).modo == "conversa", frase


def test_so_e_saudacao_quando_ha_palavra_de_cumprimento():
    assert roteador.classificar("bom dia").modo == "deterministico"
    assert roteador.classificar("valeu, obrigado!").acao_deterministica == "saudacao"
    for frase in ("mais tarde", "de noite", "por favor"):
        assert roteador.classificar(frase).modo != "deterministico", frase


def test_consultas_exatas_continuam_deterministicas_e_rotina_diaria_tem_candidata():
    assert roteador.classificar("o que eu tenho hoje?").acao_deterministica == "agenda_hoje"
    assert roteador.classificar("qual a data de hoje").acao_deterministica == "data_atual"
    r = roteador.classificar("Alura todos os dias das 6 às 8")
    assert r.modo == "interpretar" and r.intencao_candidata == "configurar_rotina"


def test_resposta_a_pergunta_pendente_vai_para_interpretacao():
    r = roteador.classificar("sim", "Há conflito com Trabalho. Confirma que quer fazer mesmo assim?")
    assert r.modo == "interpretar"


# ============================================================
if __name__ == "__main__":
    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    falhas = 0
    for nome, funcao in testes:
        try:
            funcao()
            print(f"ok      {nome}")
        except Exception as erro:
            falhas += 1
            print(f"FALHOU  {nome}: {type(erro).__name__}: {erro}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)
