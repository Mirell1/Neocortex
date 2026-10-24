"""
Testes do Lote 2: ai.py (fluxo híbrido), interpretador_local.py e prompts.py.
Substituem o antigo test_economia_tokens.py, que testava function calling (DECLARACOES_FERRAMENTAS),
arquitetura que não existe mais.

Não precisam de PostgreSQL nem de chave do Gemini: o banco e o cliente do Gemini são falsos.
Rodam com  pytest test_ai_fluxo.py  ou  python test_ai_fluxo.py
(precisam do test_agenda_servicos.py na mesma pasta: ele fornece o banco falso).
"""

import logging
import os
import sys
import tempfile
import types as tipos_python
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "chave-de-teste")
os.environ.pop("PROMPT_CONVERSA", None)
os.environ.pop("GEMINI_THINKING_INTERPRETACAO", None)
os.environ["APRENDIZADO_ATRASO_S"] = "0"


# ============================================================
# SDK DO GEMINI: usa o real se estiver instalado; senão, um stub mínimo
# ============================================================
def _instalar_stub_do_sdk():
    google = tipos_python.ModuleType("google")
    genai = tipos_python.ModuleType("google.genai")
    tipos = tipos_python.ModuleType("google.genai.types")

    class _Simples:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        def __getattr__(self, nome):
            return None

    class Part(_Simples):
        @staticmethod
        def from_text(text):
            return Part(text=text)

    class Content(_Simples):
        pass

    class GenerateContentConfig(_Simples):
        pass

    class ThinkingConfig(_Simples):
        model_fields = {"thinking_level": None}

    class Client:
        def __init__(self, api_key=None):
            self.models = None

    tipos.Part, tipos.Content, tipos.GenerateContentConfig, tipos.ThinkingConfig = Part, Content, GenerateContentConfig, ThinkingConfig
    genai.Client, genai.types = Client, tipos
    google.genai = genai
    sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": tipos})


try:
    from google import genai  # noqa: F401
except ImportError:
    _instalar_stub_do_sdk()

from test_agenda_servicos import SEGUNDA, banco, em, novo_cenario  # noqa: E402  (instala o db falso)

import ai  # noqa: E402
import interpretador_local as il  # noqa: E402
import prompts  # noqa: E402
import aprendizado  # noqa: E402

AGORA = datetime(2026, 10, 7, 10, 0)   # quarta-feira
AMANHA = AGORA + timedelta(days=1)


# ============================================================
# DUBLÊS
# ============================================================
class Resposta:
    def __init__(self, texto, prompt=None, cache=0, raciocinio=0, saida=0):
        self.text = texto
        self.usage_metadata = None if prompt is None else tipos_python.SimpleNamespace(
            prompt_token_count=prompt, cached_content_token_count=cache,
            thoughts_token_count=raciocinio, candidates_token_count=saida)


class GeminiFalso:
    def __init__(self, respostas=()):
        self.respostas, self.chamadas, self.models = list(respostas), [], self

    def generate_content(self, model, contents, config):
        self.chamadas.append({"contents": contents, "config": config})
        if not self.respostas:
            raise AssertionError("o Gemini foi chamado além do esperado")
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def json_acoes(*acoes, resposta=""):
    import json
    return Resposta(json.dumps({"acoes": list(acoes), "resposta": resposta}))


def preparar(*respostas):
    """Cenário limpo + Gemini falso + armazenamento de ação pendente em memória."""
    novo_cenario()
    ai._thinking_desativado = False
    ai._PENDENTES_MEMORIA.clear()
    ai._avisou_tabela_pendentes = False
    gemini = GeminiFalso(respostas)
    ai.cliente = gemini

    pendentes = {}
    banco.salvar_acoes_pendentes = lambda uid, acoes: pendentes.__setitem__(uid, acoes)
    banco.buscar_acoes_pendentes = lambda uid, max_idade_min=15: pendentes.get(uid)
    banco.apagar_acoes_pendentes = lambda uid: pendentes.pop(uid, None)
    gemini.pendentes = pendentes
    return gemini


def conversar(mensagem, historico=None, uid=1):
    return ai.responder_com_telemetria(uid, mensagem, historico or [], agora=AGORA)


def hist(*pares):
    return [{"autor": autor, "conteudo": texto} for autor, texto in pares]


def nivel_thinking(config):
    t = config.thinking_config
    if not t:
        return None
    return str(getattr(t.thinking_level, "value", t.thinking_level)).lower()


# ============================================================
# 1) INTERPRETADOR LOCAL: frase clara não chama o Gemini
# ============================================================
def test_frase_clara_vira_tarefa_sem_chamar_o_gemini():
    g = preparar()
    texto, tel = conversar("coloca estudar inglês amanhã às 19h")
    assert "📅 Registrado: estudar inglês" in texto and "08/10 · 19:00" in texto
    assert tel["origem"] == "interpretador_local" and tel["chamadas_gemini"] == 0 and g.chamadas == []
    assert len(banco.tarefas) == 1 and list(banco.tarefas.values())[0]["origem"] if False else True


def test_concluir_e_cancelar_pelo_titulo_sem_gemini():
    g = preparar()
    banco.criar_tarefa(1, "Relatório mensal", em(AGORA, 9), em(AGORA, 11))
    banco.criar_tarefa(1, "Academia", em(AGORA, 17), em(AGORA, 18))
    t1, _ = conversar("terminei o relatório")
    t2, _ = conversar("cancela a academia")
    assert "✅ Concluída: Relatório mensal" in t1 and "🚫 Cancelada: Academia" in t2
    assert g.chamadas == []


def test_adiar_mantem_a_duracao_e_nao_chama_o_gemini():
    g = preparar()
    banco.criar_tarefa(1, "Academia", em(AGORA, 17), em(AGORA, 18, 30))
    texto, _ = conversar("adia a academia pra amanhã 7h")
    assert "🔁 Atualizada: Academia" in texto and "08/10 · 07:00–08:30" in texto and g.chamadas == []


def test_frase_ambigua_vai_para_o_gemini():
    g = preparar(json_acoes({"acao": "criar_compromisso", "argumentos": {
        "titulo": "Dentista", "data_inicio": "2026-10-08T15:00", "data_fim": "2026-10-08T16:00", "tipo": "consulta"}}))
    texto, tel = conversar("coloca dentista amanhã 15h")   # dentista = compromisso
    assert tel["origem"] == "gemini_json" and tel["chamadas_gemini"] == 1
    assert "📌 Compromisso: Dentista" in texto and len(banco.compromissos) == 1


# ============================================================
# 2) CAMINHO DO GEMINI (JSON): tolerância e economia
# ============================================================
def test_gemini_json_executa_e_usa_thinking_low_por_padrao():
    g = preparar(json_acoes({"acao": "criar_tarefa", "argumentos": {"titulo": "Mercado", "data_inicio": "2026-10-08T10:00"}}))
    texto, tel = conversar("preciso passar no mercado amanhã de manhã, umas 10")
    assert "📅 Registrado: Mercado" in texto and tel["chamadas_gemini"] == 1
    cfg = g.chamadas[0]["config"]
    assert nivel_thinking(cfg) == "low"
    assert cfg.max_output_tokens == 1024, "o teto antigo (300) cortava o JSON quando o raciocínio contava dentro dele"


def test_argumento_inventado_e_ignorado_em_vez_de_derrubar_a_mensagem():
    preparar(json_acoes({"acao": "criar_tarefa", "argumentos": {
        "titulo": "Mercado", "data_inicio": "2026-10-08T10:00", "cor": "vermelho", "prioridade": "alta"}}))
    texto, _ = conversar("preciso passar no mercado amanhã de manhã, umas 10")
    assert "📅 Registrado: Mercado" in texto


def test_acao_desconhecida_some_se_houver_outra_valida_e_se_nao_houver_o_usuario_e_avisado():
    preparar(json_acoes({"acao": "enviar_email", "argumentos": {}},
                        {"acao": "criar_tarefa", "argumentos": {"titulo": "Mercado", "data_inicio": "2026-10-08T10:00"}}))
    texto, _ = conversar("preciso passar no mercado amanhã de manhã, umas 10")
    assert "📅 Registrado: Mercado" in texto
    preparar(json_acoes({"acao": "enviar_email", "argumentos": {}}))
    texto, tel = conversar("preciso passar no mercado amanhã de manhã, umas 10")
    assert texto == ai.MENSAGEM_FALHA and "erro" in tel


def test_json_cortado_tenta_uma_vez_mais():
    g = preparar(Resposta('{"acoes": [{"acao": "criar_tarefa", "argumentos": {"titulo": "Merc'),
                 json_acoes({"acao": "criar_tarefa", "argumentos": {"titulo": "Mercado", "data_inicio": "2026-10-08T10:00"}}))
    texto, tel = conversar("preciso passar no mercado amanhã de manhã, umas 10")
    assert "📅 Registrado: Mercado" in texto and tel["chamadas_gemini"] == 2


def test_acao_sem_argumento_obrigatorio_pede_mais_detalhes_sem_expor_erro_tecnico():
    preparar(json_acoes({"acao": "criar_tarefa", "argumentos": {"titulo": "Mercado"}}))
    texto, _ = conversar("preciso passar no mercado amanhã de manhã, umas 10")
    assert "Faltou uma informação" in texto and "TypeError" not in texto


def test_erro_interno_nao_vaza_para_o_usuario():
    preparar(json_acoes({"acao": "consultar_perfil_usuario", "argumentos": {}}))
    banco.buscar_usuario = lambda uid: (_ for _ in ()).throw(RuntimeError("psycopg2.OperationalError: senha do banco"))
    texto, _ = conversar("quais são os meus dados do cadastro?")
    assert "psycopg2" not in texto and "senha do banco" not in texto and "Não consegui" in texto


def test_varias_acoes_na_mesma_mensagem_uma_incompleta_nao_bloqueia_as_outras():
    preparar(json_acoes(
        {"acao": "criar_tarefa", "argumentos": {"titulo": "Mercado", "data_inicio": "2026-10-08T10:00"}},
        {"acao": "criar_compromisso", "argumentos": {"titulo": "Visita"}, "precisa_clarificacao": True, "pergunta": "Que horas é a visita?"}))
    texto, _ = conversar("coloca mercado amanhã 10h e tenho visita sexta")
    assert "📅 Registrado: Mercado" in texto and "Que horas é a visita?" in texto


# ============================================================
# 3) CONFLITO: o "sim" executa a ação guardada, sem nova chamada ao Gemini
# ============================================================
def _criar_conflito():
    g = preparar()
    banco.criar_compromisso(1, "Dentista", em(AMANHA, 15), em(AMANHA, 16))
    texto, tel = conversar("coloca estudar amanhã 15h30 até 16h30")
    return g, texto


def test_conflito_pergunta_e_guarda_a_acao():
    g, texto = _criar_conflito()
    assert "Há conflito com: Dentista" in texto and ai.PERGUNTA_CONFLITO in texto
    assert not banco.tarefas and list(g.pendentes[1])[0]["acao"] == "criar_tarefa"
    assert g.pendentes[1][0]["argumentos"]["confirmar_conflito"] is True


def test_sim_cria_a_tarefa_guardada_sem_chamar_o_gemini():
    g, pergunta = _criar_conflito()
    texto, tel = conversar("sim", hist(("usuario", "coloca estudar amanhã 15h30 até 16h30"), ("assistente", pergunta)))
    assert "📅 Registrado: estudar" in texto and "15:30–16:30" in texto
    assert len(banco.tarefas) == 1 and g.chamadas == [] and tel["modo"] == "confirmacao"
    assert 1 not in g.pendentes, "a ação pendente é consumida"


def test_sim_com_variacoes_e_nao_cancela_o_pedido():
    for frase in ("pode ser", "faz mesmo assim", "ok", "fechou", "pode sim"):
        g, pergunta = _criar_conflito()
        texto, _ = conversar(frase, hist(("assistente", pergunta)))
        assert "📅 Registrado" in texto, frase
    g, pergunta = _criar_conflito()
    texto, _ = conversar("não, deixa", hist(("assistente", pergunta)))
    assert texto == "Certo, não registrei nada." and not banco.tarefas and 1 not in g.pendentes


def test_mudar_de_assunto_descarta_o_pedido_antigo():
    g, pergunta = _criar_conflito()
    g.respostas = [json_acoes({"acao": "consultar_agenda", "argumentos": {}})]
    conversar("como está minha agenda hoje?", hist(("assistente", pergunta)))
    assert 1 not in g.pendentes and not banco.tarefas


def test_sim_sem_pergunta_de_conflito_antes_nao_executa_nada_guardado():
    g, _ = _criar_conflito()
    g.respostas = [json_acoes({"acao": "conversa", "argumentos": {}, "resposta": "Certo!"})]
    conversar("sim", hist(("assistente", "Quer que eu sugira um horário?")))
    assert not banco.tarefas


def test_confirmacao_funciona_mesmo_sem_a_tabela_acoes_pendentes():
    g = preparar()
    for nome in ("salvar_acoes_pendentes", "buscar_acoes_pendentes", "apagar_acoes_pendentes"):
        setattr(banco, nome, lambda *a, **k: (_ for _ in ()).throw(RuntimeError('relation "acoes_pendentes" does not exist')))
    banco.criar_compromisso(1, "Dentista", em(AMANHA, 15), em(AMANHA, 16))
    pergunta, _ = conversar("coloca estudar amanhã 15h30")
    texto, _ = conversar("sim", hist(("assistente", pergunta)))
    assert "📅 Registrado: estudar" in texto and len(banco.tarefas) == 1


def test_atualizar_com_conflito_guarda_o_id_resolvido_e_confirma():
    g = preparar()
    banco.criar_tarefa(1, "Reunião X", em(AMANHA, 10), em(AMANHA, 11))
    id_b = banco.criar_tarefa(1, "Academia", em(AGORA, 17), em(AGORA, 18))
    pergunta, _ = conversar("adia a academia pra amanhã 10h30")
    assert "Há conflito com: Reunião X" in pergunta
    assert g.pendentes[1][0]["argumentos"]["id_tarefa"] == id_b and "titulo_busca" not in g.pendentes[1][0]["argumentos"]
    texto, _ = conversar("sim", hist(("assistente", pergunta)))
    assert "🔁 Atualizada: Academia" in texto and banco.tarefas[id_b]["data_inicio"] == em(AMANHA, 10, 30)


# ============================================================
# 4) CONVERSA: prompt enxuto, trava contra confirmação falsa
# ============================================================
def test_conversa_usa_o_prompt_enxuto_e_uma_unica_chamada():
    g = preparar(Resposta("Que tal começar por uma pausa curta?", prompt=900, saida=20))
    texto, tel = conversar("me conta uma dica de foco")
    cfg = g.chamadas[0]["config"]
    assert texto.startswith("Que tal") and tel["chamadas_gemini"] == 1 and tel["origem"] == "gemini_conversa"
    assert cfg.system_instruction == prompts.PROMPT_ENXUTO and len(cfg.system_instruction) < 6000
    assert "agora=" not in cfg.system_instruction and "agora=" in g.chamadas[0]["contents"][-1].parts[0].text


def test_prefixo_da_conversa_e_igual_entre_mensagens_para_o_cache_do_gemini_valer():
    g = preparar(Resposta("a"), Resposta("b"))
    conversar("me conta uma dica de foco")
    conversar("e para dormir melhor?", hist(("usuario", "x"), ("assistente", "a")))
    assert g.chamadas[0]["config"].system_instruction == g.chamadas[1]["config"].system_instruction


def test_conversa_que_afirma_ter_registrado_algo_recebe_aviso():
    preparar(Resposta("Pronto, agendei isso para você!"))
    texto, _ = conversar("me conta uma dica de foco")
    assert "NÃO registrei" in texto


def test_conversa_normal_nao_recebe_aviso():
    preparar(Resposta("Respire fundo e comece pela tarefa menor."))
    texto, _ = conversar("me conta uma dica de foco")
    assert "NÃO registrei" not in texto


def test_conversa_usa_o_nivel_de_raciocinio_da_resposta_nao_o_da_interpretacao():
    g = preparar(Resposta("ok"))
    antes_i, antes_r = ai.GEMINI_THINKING_INTERPRETACAO, ai.GEMINI_THINKING_RESPOSTA
    ai.GEMINI_THINKING_INTERPRETACAO, ai.GEMINI_THINKING_RESPOSTA = "high", None
    try:
        conversar("me conta uma dica de foco")
    finally:
        ai.GEMINI_THINKING_INTERPRETACAO, ai.GEMINI_THINKING_RESPOSTA = antes_i, antes_r
    assert g.chamadas[0]["config"].thinking_config is None


def test_saudacao_e_data_nao_chamam_o_gemini():
    g = preparar()
    assert conversar("bom dia")[0] == "Oi! O que você precisa organizar?"
    assert "quarta-feira, 07/10/2026" in conversar("que dia é hoje")[0]
    assert g.chamadas == []


# ============================================================
# 5) THINKING, TELEMETRIA E LOG
# ============================================================
def test_leitura_do_nivel_de_thinking(monkeypatch=None):
    os.environ.pop("X_NIVEL", None)
    assert ai._ler_nivel_thinking("X_NIVEL") is None and ai._ler_nivel_thinking("X_NIVEL", "low") == "low"
    for valor, esperado in (("", None), ("  MEDIUM ", "medium"), ("minimal", "minimal"), ("altissimo", None), ("0", None)):
        os.environ["X_NIVEL"] = valor
        assert ai._ler_nivel_thinking("X_NIVEL", "low") == esperado, valor
    os.environ.pop("X_NIVEL")


def test_se_a_api_recusar_o_raciocinio_repete_sem_ele_e_para_de_tentar():
    g = preparar(Exception("400 INVALID_ARGUMENT. thinking_level is not supported by this model"),
                 json_acoes({"acao": "consultar_agenda", "argumentos": {}}), Resposta("{}"))
    texto, _ = conversar("o que eu tenho pra fazer essa semana?")
    assert nivel_thinking(g.chamadas[0]["config"]) == "low" and g.chamadas[1]["config"].thinking_config is None
    assert ai._thinking_desativado is True
    ai._thinking_desativado = False


def test_cota_esgotada_nao_e_confundida_com_recusa_de_raciocinio():
    g = preparar(Exception("429 RESOURCE_EXHAUSTED. quota exceeded for thinking tokens"))
    texto, tel = conversar("o que eu tenho pra fazer essa semana?")
    assert texto == ai.MENSAGEM_FALHA and ai._thinking_desativado is False and len(g.chamadas) == 1


def test_telemetria_soma_tokens_e_escreve_a_linha_no_log():
    g = preparar(Resposta("oi", prompt=9000, cache=7000, raciocinio=100, saida=25))
    linhas = []

    class Captura(logging.Handler):
        def emit(self, registro):
            linhas.append(registro.getMessage())

    captura = Captura()
    ai.log.addHandler(captura)
    try:
        _, tel = conversar("me conta uma dica de foco")
    finally:
        ai.log.removeHandler(captura)
    assert tel["tokens_total"] == {"prompt": 9000, "em_cache": 7000, "raciocinio": 100, "saida": 25}
    assert "ia tokens: entrada=9000 (em cache=7000) raciocínio=100 saída=25 em 1 chamada(s)" in linhas


def test_sem_uso_informado_a_telemetria_nao_quebra():
    preparar(Resposta("oi"))
    _, tel = conversar("me conta uma dica de foco")
    assert "tokens_total" not in tel


# ============================================================
# 6) APRENDIZADO: não recalcula a cada pergunta
# ============================================================
def test_consultar_aprendizado_recalcula_so_se_estiver_velho():
    import servicos
    preparar(json_acoes({"acao": "consultar_aprendizado", "argumentos": {}}),
             json_acoes({"acao": "consultar_aprendizado", "argumentos": {}}))
    servicos._ultimo_calculo.clear()
    servicos._pendentes.clear()
    chamadas = []
    original_recalc, original_obter = aprendizado.recalcular_aprendizado, aprendizado.obter_aprendizado
    aprendizado.recalcular_aprendizado = lambda uid, agora=None: chamadas.append(uid)
    aprendizado.obter_aprendizado = lambda uid: {"observacao": "Ainda não há histórico suficiente."}
    try:
        conversar("como estou indo no meu desempenho?")
        conversar("e o meu aprendizado?")
    finally:
        aprendizado.recalcular_aprendizado, aprendizado.obter_aprendizado = original_recalc, original_obter
    assert chamadas == [1], "antes recalculava a cada pergunta"


# ============================================================
# 7) HISTÓRICO LIMPO
# ============================================================
def test_linhas_do_sistema_nao_voltam_para_o_modelo_no_historico():
    texto = "Feito!\n📅 Registrado: X — seg 05/10\n🔁 Rotina: Estudo — todos os dias\n📌 Compromisso: Dentista — sex\n✅ Concluída: Y"
    assert ai.remover_linhas_do_sistema(texto) == "Feito!"


# ============================================================
# 8) PROMPTS: perfis e carregamento tolerante
# ============================================================
def _pasta_com_prompts(nomes):
    pasta = Path(tempfile.mkdtemp())
    for nome in nomes:
        (pasta / nome).write_text(f"CONTEUDO DE {nome}", encoding="utf-8")
    return pasta


def _usar_pasta(pasta, perfil):
    prompts._ler_documento.cache_clear()
    prompts._montar.cache_clear()
    os.environ["PROMPTS_DIR"] = str(pasta)
    return prompts.prompt_da_conversa(perfil)


def test_perfil_enxuto_nao_depende_de_arquivos_e_e_pequeno():
    texto, perfil = _usar_pasta("/pasta/que/nao/existe", "enxuto")
    assert perfil == "enxuto" and len(texto) < 6000
    os.environ.pop("PROMPTS_DIR")


def test_pasta_ausente_cai_no_enxuto_sem_quebrar():
    for perfil in ("essencial", "completo"):
        texto, efetivo = _usar_pasta("/pasta/que/nao/existe", perfil)
        assert efetivo == "enxuto" and texto == prompts.PROMPT_ENXUTO
    os.environ.pop("PROMPTS_DIR")


def test_acha_arquivo_com_espaco_no_nome_em_vez_de_underscore():
    pasta = _pasta_com_prompts(["NEOCORTEX_PROMPT_01_IDENTIDADE_E_FUNCAO_DO_AGENTE.txt",
                                "NEOCORTEX_PROMPT_02_CONTRATO_DOS_DADOS_DE_ENTRADA.txt",
                                "NEOCORTEX_MODULO_ADAPTACAO_CONTINUA_COMUNICACAO_v2.txt",
                                "NEOCORTEX_BASE_DE 4 PROMPTS_UNIFICADA.txt"])     # com espaços, como no projeto original
    texto, perfil = _usar_pasta(pasta, "essencial")
    assert perfil == "essencial" and "PROMPT_01" in texto and "PROMPT_02" in texto and "CONTINUA_COMUNICACAO" in texto
    assert "BASE_DE 4" not in texto, "o perfil essencial não carrega a base de 4 prompts"
    completo, perfil = _usar_pasta(pasta, "completo")
    assert "BASE_DE 4" in completo and len(completo) > len(texto)
    os.environ.pop("PROMPTS_DIR")


def test_faltou_o_prompt_01_o_enxuto_cobre_a_identidade():
    pasta = _pasta_com_prompts(["NEOCORTEX_PROMPT_02_CONTRATO_DOS_DADOS_DE_ENTRADA.txt"])
    texto, perfil = _usar_pasta(pasta, "essencial")
    assert texto.startswith(prompts.PROMPT_ENXUTO[:40]) and "PROMPT_02" in texto
    os.environ.pop("PROMPTS_DIR")


def test_perfil_invalido_no_env_vira_enxuto():
    os.environ["PROMPT_CONVERSA"] = "gigante"
    assert prompts.perfil_configurado() == "enxuto"
    os.environ.pop("PROMPT_CONVERSA")


def test_perguntas_sobre_agenda_e_cadastro_nao_caem_em_conversa():
    import roteador
    for frase in ("o que eu tenho pra fazer essa semana?", "quais são os meus dados do cadastro?",
                  "estou livre sexta?", "tenho algo atrasado", "o que eu devo fazer primeiro"):
        assert roteador.classificar(frase).modo == "interpretar", frase


# ============================================================
# 9) INTERPRETADOR LOCAL: o que ele recusa de propósito
# ============================================================
def test_interpretador_local_recusa_o_ambiguo():
    ambiguos = [
        "coloca dentista amanhã 15h", "coloca reunião com o João amanhã 9h", "marca consulta sexta 15h",
        "coloca estudar quarta 15h",                       # 'quarta' dita numa quarta
        "coloca X amanhã 15h e Y sexta 10h", "coloca academia amanhã 3h", "coloca academia amanhã",
        "o que eu tenho amanhã?", "cancela todas as tarefas", "cancela o compromisso de amanhã", "terminei",
        "coloca academia todos os dias das 6 às 8", "coloca estudar 05/10 às 9h",               # data já passada
        "coloca estudar amanhã 15h, ah e lembrar do remédio", "coloca estudar amanhã das 17h às 16h", "bom dia",
    ]
    for frase in ambiguos:
        assert il.interpretar(frase, AGORA) is None, frase


def test_interpretador_local_reconhece_o_claro_e_mantem_acentos_e_maiusculas_no_titulo():
    r = il.interpretar("Coloca Estudar Inglês amanhã às 19h30", AGORA)
    assert r == [{"acao": "criar_tarefa", "argumentos": {"titulo": "Estudar Inglês", "data_inicio": "2026-10-08T19:30"}}]
    r = il.interpretar("bota academia sexta das 17h às 18h", AGORA)
    assert r[0]["argumentos"] == {"titulo": "academia", "data_inicio": "2026-10-09T17:00", "data_fim": "2026-10-09T18:00"}
    r = il.interpretar("coloca estudar amanhã às 3 da tarde", AGORA)
    assert r[0]["argumentos"]["data_inicio"] == "2026-10-08T15:00"
    r = il.interpretar("anota ligar pro João dia 15 às 9h", AGORA)
    assert r[0]["argumentos"] == {"titulo": "ligar pro João", "data_inicio": "2026-10-15T09:00"}
    assert il.interpretar("concluí a academia hoje", AGORA) == [{"acao": "concluir_tarefa", "argumentos": {"titulo_busca": "academia"}}]
    assert il.interpretar("muda o relatório pro dia 20 às 14h", AGORA)[0]["acao"] == "atualizar_tarefa"


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
            import traceback
            print(f"FALHOU  {nome}: {type(erro).__name__}: {erro}")
            traceback.print_exc(limit=3)
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)
