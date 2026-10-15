"""
NEOCORTEX — ai.py

Camada de linguagem do agente.

Fluxo híbrido (cada degrau só é usado se o anterior não resolveu):

  MENSAGEM
    0. ação pendente        "sim"/"não" para um "confirma mesmo assim?" -> código executa a ação guardada
    1. roteador.py          saudação, data, "agenda de hoje"            -> código responde
    2. interpretador_local  "coloca dentista amanhã 15h", "terminei X"  -> código interpreta
    3. Gemini (JSON)        o que o código não entendeu                 -> interpreta, SEM tools
    4. Gemini (conversa)    papo sem pedido operacional                 -> prompt enxuto (prompts.py)
  EXECUÇÃO: sempre pelo código (servicos.py = as mesmas regras da tela), que valida,
  executa e monta a resposta factual.

O Gemini nunca recebe acesso ao banco nem ferramentas. O id_usuario vem da sessão
Flask e fica preso nos executores; o modelo não pode escolhê-lo.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

import agenda
import aprendizado
import db
import decisao
import interpretador_local
import prompts
import roteador
import servicos

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

log = logging.getLogger("neocortex.ia")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

cliente = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# TELEMETRIA VISÍVEL
# O Python só mostra WARNING ou mais por padrão, então a linha de telemetria
# (INFO) nunca aparecia no terminal. Aqui ela passa a aparecer, sem duplicar
# se o app já tiver configurado o log por conta própria.
# ============================================================
def _garantir_log_visivel():
    log.setLevel(logging.INFO)
    if not log.handlers and not logging.getLogger().handlers:
        saida = logging.StreamHandler()
        saida.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", "%H:%M:%S"))
        log.addHandler(saida)


_garantir_log_visivel()


# ============================================================
# RACIOCÍNIO DO GEMINI (thinking)
#
# Os modelos Gemini "pensam" antes de responder e esse raciocínio é cobrado como
# saída. Níveis: minimal | low | medium | high. Variável vazia no .env = desligado
# (padrão do modelo); variável ausente = padrão abaixo. Se a API recusar a
# configuração, ela é desativada sozinha (uma vez) e a conversa continua.
#
#   GEMINI_THINKING_INTERPRETACAO  (padrão: low)  extrair um JSON de uma frase não pede raciocínio longo
#   GEMINI_THINKING_RESPOSTA       (padrão: modelo) conversa livre
# ============================================================
_NIVEIS_THINKING = ("minimal", "low", "medium", "high")
_thinking_desativado = False
MENSAGEM_FALHA = (
    "Não consegui concluir essa solicitação agora. "
    "Tenta de novo em um instante."
)


def _ler_nivel_thinking(nome_variavel, padrao=None):
    bruto = os.getenv(nome_variavel)
    valor = (padrao or "") if bruto is None else bruto.strip().lower()
    if not valor:
        return None
    if valor not in _NIVEIS_THINKING:
        log.warning("%s=%r ignorado (use: %s). O Gemini segue no padrão do modelo.",
                    nome_variavel, valor, " | ".join(_NIVEIS_THINKING))
        return None
    if "thinking_level" not in types.ThinkingConfig.model_fields:
        log.warning("%s ignorado: esta versão do google-genai não tem thinking_level.", nome_variavel)
        return None
    return valor


def _ler_inteiro(nome_variavel, padrao):
    try:
        return max(1, int(os.getenv(nome_variavel, padrao)))
    except ValueError:
        return padrao


GEMINI_THINKING_INTERPRETACAO = _ler_nivel_thinking("GEMINI_THINKING_INTERPRETACAO", "low")
GEMINI_THINKING_RESPOSTA = _ler_nivel_thinking("GEMINI_THINKING_RESPOSTA")

# O raciocínio conta dentro de max_output_tokens: um teto baixo (era 300) corta o JSON no meio.
# Teto não é gasto: só se paga o que o modelo realmente gera.
GEMINI_MAX_SAIDA_INTERPRETACAO = _ler_inteiro("GEMINI_MAX_SAIDA_INTERPRETACAO", 1024)


# ============================================================
# PROMPTS
# ============================================================
BASE_OPERACIONAL = """
# REGRAS DA CAMADA DE INTERPRETAÇÃO

- Você NÃO recebe ferramentas e NÃO executa banco, agenda ou ações.
- Sua única responsabilidade nesta etapa é interpretar linguagem natural e
  transformar a intenção do usuário em um comando JSON curto e estruturado.
- Datas e horários relativos devem ser resolvidos com base no CONTEXTO DO
  SISTEMA fornecido pelo código. Nunca invente data ou hora.
- Se faltar uma informação realmente necessária, não invente: marque
  precisa_clarificacao=true e faça uma única pergunta curta.
- Nunca diga que uma tarefa foi criada, alterada, concluída ou cancelada nesta
  etapa. A execução ainda será feita pelo código.
- Não invente id_tarefa, horários, status, conflitos ou dados do usuário.
"""

_prompt_conversa_registrado = False


def prompt_da_conversa():
    """Prompt do modo conversa (perfil escolhido por PROMPT_CONVERSA). Registra o tamanho uma vez."""
    global _prompt_conversa_registrado
    texto, perfil = prompts.prompt_da_conversa()
    if not _prompt_conversa_registrado:
        _prompt_conversa_registrado = True
        log.info("ia prompt da conversa: perfil=%s, %d caracteres", perfil, len(texto))
    return texto


# ============================================================
# CONTRATO DE DADOS E EXECUTORES
#
# As ações são descritas apenas como contrato JSON para a interpretação.
# O Gemini nunca recebe function declarations.
# ============================================================
CATEGORIAS_VALIDAS = servicos.CATEGORIAS_VALIDAS
LIMITE_TAREFAS_NA_RESPOSTA = 30
_DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MAX_ACOES_POR_MENSAGEM = 10


# ============================================================
# AUXILIARES
# ============================================================
def _json_seguro(valor):
    """Converte datas/horas em texto para poder virar JSON."""
    if isinstance(valor, dict):
        return {chave: _json_seguro(v) for chave, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v) for v in valor]
    if hasattr(valor, "isoformat"):
        return valor.isoformat(timespec="minutes") if isinstance(valor, datetime) else valor.isoformat()
    return valor


def _parse_dia(texto):
    try:
        return datetime.strptime(str(texto).strip()[:10], "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"data inválida: {texto!r}. Use o formato AAAA-MM-DD.")


def _tarefa_compacta(t, agora):
    item = {
        "id_tarefa": t["id_tarefa"], "titulo": t["titulo"],
        "inicio": t["data_inicio"].isoformat(timespec="minutes"),
        "fim": t["data_fim"].isoformat(timespec="minutes"),
        "status": t["status"],
    }
    if t.get("categoria"):
        item["categoria"] = t["categoria"]
    if t["status"] in ("pendente", "em_andamento") and t["data_fim"] < agora:
        item["atrasada"] = True
    return item


def _bloco_json(b):
    return None if not b else {
        "tipo": b["tipo"], "titulo": b["titulo"],
        "inicio": b["inicio"].isoformat(timespec="minutes"),
        "fim": b["fim"].isoformat(timespec="minutes"),
    }


def _normalizar(texto):
    return roteador.normalizar(texto)


def _resolver_tarefa(id_usuario, id_tarefa, titulo_busca, agora):
    """
    Acha a tarefa-alvo SEM chamada extra ao modelo. Retorna (tarefa, None)
    ou (None, resposta_de_erro). Só considera tarefas do próprio usuário.
    """
    if id_tarefa is not None:
        tarefa = db.buscar_tarefa(int(id_tarefa), id_usuario)
        if tarefa is None:
            return None, {"sucesso": False, "erro": "Tarefa não encontrada."}
        return tarefa, None

    palavras = [p for p in re.findall(r"\w+", _normalizar(titulo_busca)) if len(p) >= 3]
    if not palavras:
        return None, {"sucesso": False, "erro": "Informe id_tarefa ou titulo_busca."}

    abertas = db.listar_tarefas_abertas(id_usuario, data_fim_minima=agora - timedelta(days=7))
    achadas = [t for t in abertas if all(p in _normalizar(t["titulo"]) for p in palavras)]
    if len(achadas) == 1:
        return achadas[0], None
    if not achadas:
        return None, {"sucesso": False, "erro": "Nenhuma tarefa aberta encontrada com esse título."}
    return None, {
        "sucesso": False, "erro": "Mais de uma tarefa corresponde. Pergunte ao usuário qual.",
        "candidatas": [_tarefa_compacta(t, agora) for t in achadas[:5]],
    }


def _sem_vazios(dicionario):
    return {k: v for k, v in dicionario.items() if v not in (None, "")}


def _com_pendente(acao, argumentos, resultado):
    """
    Se a ação parou num conflito, anexa o que precisa ser executado quando o
    usuário disser "sim" (o código guarda; o modelo não é chamado de novo).
    """
    if resultado.get("conflitos") and not resultado.get("sucesso"):
        resultado["_pendente"] = {"acao": acao, "argumentos": {**_sem_vazios(argumentos), "confirmar_conflito": True}}
    return resultado


# ============================================================
# EXECUTORES (o que realmente roda; sempre presos ao id_usuario da sessão)
# Consultas leem a agenda/decisão; alterações passam por servicos.py, as
# MESMAS regras da tela.
# ============================================================
def _construir_executores(id_usuario, agora=None):
    agora = agora or datetime.now()

    def _janela(data_inicio, data_fim, padrao_inicio, padrao_dias):
        if data_inicio:
            inicio = _parse_dia(data_inicio)
            fim = (_parse_dia(data_fim) if data_fim else inicio) + timedelta(days=1)
        elif data_fim:
            inicio, fim = padrao_inicio, _parse_dia(data_fim) + timedelta(days=1)
        else:
            inicio, fim = padrao_inicio, padrao_inicio + timedelta(days=padrao_dias)
        if fim <= inicio:
            raise ValueError("data_fim precisa ser igual ou depois de data_inicio.")
        return inicio, fim

    # ---------------- consultas
    def consultar_tarefas(status=None, data_inicio=None, data_fim=None):
        if status and not (data_inicio or data_fim):
            tarefas = db.listar_tarefas(id_usuario, status=status)
            periodo = None
        else:
            inicio, fim = _janela(data_inicio, data_fim, agora.replace(hour=0, minute=0, second=0, microsecond=0), 7)
            tarefas = db.listar_tarefas_janela(id_usuario, inicio, fim, status=status)
            periodo = {"inicio": inicio.date().isoformat(), "fim_exclusivo": fim.date().isoformat()}
        total = len(tarefas)
        saida = {"total": total, "tarefas": [_tarefa_compacta(t, agora) for t in tarefas[:LIMITE_TAREFAS_NA_RESPOSTA]]}
        if periodo:
            saida["periodo"] = periodo
        if total > LIMITE_TAREFAS_NA_RESPOSTA:
            saida["truncado"] = True
        return saida

    def consultar_agenda(data_inicio=None, data_fim=None):
        inicio, fim = _janela(data_inicio, data_fim, agora, 0) if (data_inicio or data_fim) else (
            agora, agora.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        dados = agenda.carregar_agenda(id_usuario, inicio, fim)
        saida = {
            "agora": agora.isoformat(timespec="minutes"),
            "periodo": {"inicio": inicio.isoformat(timespec="minutes"), "fim": fim.isoformat(timespec="minutes")},
            "tarefas": [_tarefa_compacta(t, agora) for t in dados["tarefas"][:LIMITE_TAREFAS_NA_RESPOSTA]],
            "compromissos": [
                {"titulo": c["titulo"], "tipo": c.get("tipo"), "local": c.get("local"),
                 "inicio": c["data_inicio"].isoformat(timespec="minutes"),
                 "fim": c["data_fim"].isoformat(timespec="minutes")}
                for c in dados["compromissos"]
            ],
            "rotina": [
                {"descricao": r["descricao"], "inicio": r["inicio"].isoformat(timespec="minutes"),
                 "fim": r["fim"].isoformat(timespec="minutes")}
                for r in dados["rotina"]
            ],
        }
        if inicio <= agora < fim:
            s = agenda.situacao_agora(id_usuario, agora)
            saida["situacao_agora"] = {
                "ocupado_com": _bloco_json(s["atual"]),
                "proximo_bloco": _bloco_json(s["proximo"]),
                "minutos_livres_ate_proximo": s["minutos_livres_ate_proximo"],
            }
        return saida

    def consultar_perfil_usuario():
        usuario = db.buscar_usuario(id_usuario)
        perfil = None
        if usuario:
            perfil = {
                "nome": usuario["nome"], "faixa_etaria": usuario["faixa_etaria"],
                "trabalha": usuario["trabalha"], "estuda": usuario["estuda"], "turno": usuario["turno"],
            }
        return {
            "perfil": perfil,
            "hobbies": [h["nome"] for h in db.listar_hobbies_usuario(id_usuario)],
            "preferencias": {p["chave"]: p["valor"] for p in db.listar_preferencias(id_usuario)},
        }

    def consultar_aprendizado():
        servicos.garantir_aprendizado_atualizado(id_usuario, agora)   # só recalcula se estiver desatualizado
        return aprendizado.obter_aprendizado(id_usuario)

    def sugerir_horarios(data, duracao_minutos=60):
        dia = _parse_dia(data).date()
        duracao = int(duracao_minutos or 60)
        if not 5 <= duracao <= 600:
            raise ValueError("duracao_minutos precisa estar entre 5 e 600.")
        return decisao.sugerir_horarios(id_usuario, dia, duracao, agora)

    def recomendar_tarefa_agora():
        return decisao.recomendar_tarefa_agora(id_usuario, agora)

    # ---------------- alterações (servicos.py)
    def configurar_rotina(descricao, hora_inicio, hora_fim, dias_semana):
        return servicos.configurar_rotina(id_usuario, descricao, hora_inicio, hora_fim, dias_semana)

    def criar_tarefa(titulo, data_inicio, data_fim=None, categoria=None, descricao=None, confirmar_conflito=False):
        resultado = servicos.criar_tarefa(
            id_usuario, titulo, data_inicio, data_fim, categoria=categoria, descricao=descricao,
            origem="ia_sugestao", confirmar_conflito=bool(confirmar_conflito), agora=agora,
        )
        return _com_pendente("criar_tarefa", dict(titulo=titulo, data_inicio=data_inicio, data_fim=data_fim,
                                                  categoria=categoria, descricao=descricao), resultado)

    def criar_compromisso(titulo, data_inicio, data_fim=None, tipo="outro", local=None, confirmar_conflito=False):
        resultado = servicos.criar_compromisso(
            id_usuario, titulo, data_inicio, data_fim, tipo=tipo, local=local,
            confirmar_conflito=bool(confirmar_conflito),
        )
        return _com_pendente("criar_compromisso", dict(titulo=titulo, data_inicio=data_inicio, data_fim=data_fim,
                                                       tipo=tipo, local=local), resultado)

    def atualizar_tarefa(id_tarefa=None, titulo_busca=None, novo_titulo=None, nova_data_inicio=None,
                         nova_data_fim=None, nova_categoria=None, confirmar_conflito=False):
        tarefa, erro = _resolver_tarefa(id_usuario, id_tarefa, titulo_busca, agora)
        if erro:
            return erro
        extras = {"categoria": nova_categoria} if nova_categoria in CATEGORIAS_VALIDAS else {}
        resultado = servicos.atualizar_tarefa(
            id_usuario, tarefa["id_tarefa"], titulo=novo_titulo, data_inicio=nova_data_inicio,
            data_fim=nova_data_fim, confirmar_conflito=bool(confirmar_conflito), **extras,
        )
        return _com_pendente("atualizar_tarefa", dict(
            id_tarefa=tarefa["id_tarefa"], novo_titulo=novo_titulo, nova_data_inicio=nova_data_inicio,
            nova_data_fim=nova_data_fim, nova_categoria=extras.get("categoria"),
        ), resultado)

    def concluir_tarefa(id_tarefa=None, titulo_busca=None):
        tarefa, erro = _resolver_tarefa(id_usuario, id_tarefa, titulo_busca, agora)
        return erro or servicos.concluir_tarefa(id_usuario, tarefa["id_tarefa"])

    def cancelar_tarefa(id_tarefa=None, titulo_busca=None):
        tarefa, erro = _resolver_tarefa(id_usuario, id_tarefa, titulo_busca, agora)
        return erro or servicos.cancelar_tarefa(id_usuario, tarefa["id_tarefa"])

    return {
        "consultar_tarefas": consultar_tarefas,
        "consultar_agenda": consultar_agenda,
        "consultar_perfil_usuario": consultar_perfil_usuario,
        "consultar_aprendizado": consultar_aprendizado,
        "sugerir_horarios": sugerir_horarios,
        "recomendar_tarefa_agora": recomendar_tarefa_agora,
        "criar_tarefa": criar_tarefa,
        "configurar_rotina": configurar_rotina,
        "criar_compromisso": criar_compromisso,
        "atualizar_tarefa": atualizar_tarefa,
        "concluir_tarefa": concluir_tarefa,
        "cancelar_tarefa": cancelar_tarefa,
    }


# ============================================================
# LINHA DE CONFIRMAÇÃO (o que o sistema REALMENTE registrou)
# O texto da IA pode ser informal e curto. Logo abaixo, o CÓDIGO acrescenta uma
# linha factual, montada a partir do resultado da execução. Regra simples para
# o usuário: se a linha 📅 apareceu, foi registrado de verdade; se não, não foi.
# ============================================================
_DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _quando(inicio_iso, fim_iso=None):
    ini = datetime.fromisoformat(inicio_iso)
    texto = f"{_DIAS_CURTOS[ini.weekday()]} {ini:%d/%m} · {ini:%H:%M}"
    if fim_iso:
        fim = datetime.fromisoformat(fim_iso)
        texto += f"–{fim:%H:%M}" if fim.date() == ini.date() else f" → {fim:%d/%m %H:%M}"
    return texto


def linha_de_confirmacao(nome, resultado):
    """Linha factual para uma alteração que deu certo (ou None)."""
    if resultado.get("sucesso") is not True:
        return None
    titulo = resultado.get("titulo", "")
    if nome == "criar_tarefa":
        extra = " (duração assumida: 1h)" if resultado.get("duracao_assumida_min") else ""
        return f"📅 Registrado: {titulo} — {_quando(resultado['inicio'], resultado['fim'])}{extra}"
    if nome == "configurar_rotina":
        dias = resultado.get("dias_semana") or []
        frequencia = "todos os dias" if len(dias) == 7 else ", ".join(dias)
        return (f"🔁 Rotina: {resultado.get('descricao', 'Rotina')} — {frequencia}, "
                f"{resultado.get('hora_inicio')}–{resultado.get('hora_fim')}.")
    if nome == "criar_compromisso":
        extra = " (duração assumida: 1h)" if resultado.get("duracao_assumida_min") else ""
        local = f" · {resultado['local']}" if resultado.get("local") else ""
        return f"📌 Compromisso: {titulo} — {_quando(resultado['inicio'], resultado['fim'])}{local}{extra}"
    if nome == "atualizar_tarefa":
        quando = f" — {_quando(resultado['novo_inicio'], resultado.get('novo_fim'))}" if resultado.get("novo_inicio") else ""
        return f"🔁 Atualizada: {titulo}{quando}"
    if nome == "concluir_tarefa":
        return f"✅ Concluída: {titulo}"
    if nome == "cancelar_tarefa":
        return f"🚫 Cancelada: {titulo}"
    return None


# ============================================================
# TRAVA CONTRA CONFIRMAÇÃO FALSA
# Se um texto escrito pelo modelo afirma que algo foi feito, mas nenhuma
# execução confirmou, o usuário é avisado em vez de acreditar num registro que
# não existe. Vale para tudo que o modelo escreve livremente (conversa).
# ============================================================
FERRAMENTAS_DE_ALTERACAO = {"criar_tarefa", "configurar_rotina", "criar_compromisso", "atualizar_tarefa", "concluir_tarefa", "cancelar_tarefa"}
AVISO_SEM_REGISTRO = (
    "\n\n⚠️ Atenção: eu ainda NÃO registrei isso na sua agenda. Para registrar, me diga o título, "
    "a data e o início e o fim (ex.: “Coloca academia amanhã das 17h às 18h”)."
)
_RE_ACAO_FEITA = re.compile(
    r"\b(agendei|criei|adicionei|registrei|coloquei|anotei|inclu[ií]|cancelei|conclu[ií]|marquei|remarquei|movi|alterei|atualizei)\b",
    re.IGNORECASE,
)
_RE_ESTADO_AFIRMADO = re.compile(
    r"\b(foi|foram|ficou|ficaram|est[aá]|est[aã]o)\s+(agendad|criad|adicionad|registrad|marcad|salv|cancelad|remarcad)\w*",
    re.IGNORECASE,
)


def afirma_sem_prova(texto, mutacoes_ok, consultas_feitas, mensagem_usuario=""):
    """
    True se o texto afirma uma ação feita sem que a execução tenha confirmado.
      - verbo de AÇÃO ("criei", "agendei"): exige uma alteração com sucesso nesta resposta;
      - afirmação de ESTADO ("foi agendado", "está no calendário"): exige alguma consulta ou alteração.
    """
    if _RE_ACAO_FEITA.search(texto or "") and mutacoes_ok == 0:
        return True
    if _RE_ESTADO_AFIRMADO.search(texto or "") and mutacoes_ok == 0 and consultas_feitas == 0:
        return True
    # o usuário pediu para registrar algo, o modelo respondeu sem fazer nada e sem perguntar nada
    if (mutacoes_ok == 0 and consultas_feitas == 0 and "?" not in (texto or "")
            and roteador.parece_pedido_de_registro(mensagem_usuario)):
        return True
    return False


def _proteger_texto_do_modelo(texto, mensagem_usuario):
    """Texto livre do modelo (conversa): acrescenta o aviso se ele afirma ter registrado algo."""
    if texto and afirma_sem_prova(texto, 0, 0, mensagem_usuario):
        return texto.rstrip() + AVISO_SEM_REGISTRO
    return texto


# ============================================================
# FILTRO DE ANÁLISE INTERNA
# Alguns modelos escrevem a análise em camadas junto com a resposta. Aqui ela
# é removida: o usuário só vê o texto final, e o histórico enviado de volta ao
# modelo fica limpo.
# ============================================================
MENSAGEM_ANALISE_VAZADA = "Tive um problema ao formular a resposta. Pode repetir, por favor?"
_RE_NIVEL_CONFIANCA = re.compile(r"^\s*N[ÍI]VEL DE CONFIAN[ÇC]A", re.IGNORECASE)
_RE_VALOR_CONFIANCA = re.compile(r"^\s*[A-Za-zÀ-ú ]{3,25}\s*[—–-]\s*(alta|m[ée]dia|baixa)\s*\.?\s*$", re.IGNORECASE)


def limpar_resposta(texto):
    """Remove o bloco 'ANÁLISE INTERNA ... NÍVEL DE CONFIANÇA ...' do início da resposta, se houver."""
    if not texto:
        return texto
    linhas = texto.strip().split("\n")
    if not re.match(r"\s*AN[ÁA]LISE INTERNA", linhas[0], re.IGNORECASE):
        return texto

    fim = None
    for i, linha in enumerate(linhas):
        if _RE_NIVEL_CONFIANCA.match(linha):
            fim = i
    if fim is None:
        return MENSAGEM_ANALISE_VAZADA   # análise sem fim identificável: melhor pedir de novo do que vazar
    resto = fim + 1
    while resto < len(linhas) and not linhas[resto].strip():
        resto += 1
    if resto < len(linhas) and _RE_VALOR_CONFIANCA.match(linhas[resto]):
        resto += 1
    limpo = "\n".join(linhas[resto:]).strip()
    return limpo or MENSAGEM_ANALISE_VAZADA


_PREFIXOS_DE_LINHA_DO_SISTEMA = (
    "📅 Registrado:", "🔁 Atualizada:", "🔁 Rotina:", "📌 Compromisso:", "✅ Concluída:", "🚫 Cancelada:",
    "⚠️ Atenção: eu ainda NÃO registrei",
)


def remover_linhas_do_sistema(texto):
    """
    Tira da resposta antiga as linhas que o CÓDIGO acrescentou (confirmações e
    avisos). Se o modelo as visse no histórico, poderia aprender a escrevê-las
    sozinho SEM ter feito nada — e a linha 📅 deixaria de ser prova de registro.
    """
    mantidas = [l for l in (texto or "").split("\n") if not l.strip().startswith(_PREFIXOS_DE_LINHA_DO_SISTEMA)]
    return "\n".join(mantidas).strip()


# ============================================================
# HISTÓRICO E CONTEXTO
# ============================================================
MAX_CARACTERES_POR_MENSAGEM = 600


def _historico_para_conteudo(historico, limite=roteador.MAX_MENSAGENS_HISTORICO):
    """
    Converte as linhas de interacoes_chat (mais antiga -> mais nova, SEM a
    mensagem nova) no 'contents' do Gemini.

    - só as últimas 'limite' mensagens, cada uma truncada;
    - mensagens seguidas do mesmo autor viram uma só;
    - a conversa precisa começar com o usuário.
    """
    contents = []
    for mensagem in (historico or [])[-limite:]:
        texto = (mensagem.get("conteudo") or "").strip()
        if mensagem.get("autor") == "assistente":
            texto = remover_linhas_do_sistema(limpar_resposta(texto))
        if not texto:
            continue
        if len(texto) > MAX_CARACTERES_POR_MENSAGEM:
            texto = texto[:MAX_CARACTERES_POR_MENSAGEM] + "…"
        papel = "model" if mensagem.get("autor") == "assistente" else "user"
        if contents and contents[-1].role == papel:
            contents[-1].parts.append(types.Part.from_text(text="\n" + texto))
        else:
            contents.append(types.Content(role=papel, parts=[types.Part.from_text(text=texto)]))
    while contents and contents[0].role != "user":
        contents.pop(0)
    return contents


def _linha_de_contexto(agora):
    """Data/hora atuais para a IA resolver 'hoje', 'amanhã', 'agora'. Vai na mensagem, não no prompt fixo."""
    return f"[CONTEXTO DO SISTEMA] agora={agora:%Y-%m-%d %H:%M} ({_DIAS_PT[agora.weekday()]}), horário local"


def _montar_config(parametros, nivel=None):
    """Monta a configuração do Gemini e aplica thinking somente quando pedido."""
    extras = {}
    if nivel and not _thinking_desativado:
        extras["thinking_config"] = types.ThinkingConfig(thinking_level=nivel.upper())
    return types.GenerateContentConfig(**parametros, **extras)


def _gerar(contents, parametros, nivel=None):
    """Faz uma chamada ao Gemini; se thinking for recusado, repete sem ele."""
    global _thinking_desativado
    try:
        return cliente.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=_montar_config(parametros, nivel),
        )
    except Exception as erro:
        mensagem = str(erro).lower()
        transitorio = any(termo in mensagem for termo in ("unavailable", "503", "429", "resource_exhausted"))
        if nivel and not _thinking_desativado and "thinking" in mensagem and not transitorio:
            _thinking_desativado = True
            log.warning(
                "A API recusou a configuração de raciocínio (%s). "
                "Desativada nesta execução; seguindo sem thinking.",
                erro,
            )
            return cliente.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=_montar_config(parametros, None),
            )
        raise


def _registrar_uso(telemetria, resposta, nivel=None):
    """Registra o uso retornado pela API sem interferir na execução."""
    registro = {"thinking": nivel if (nivel and not _thinking_desativado) else "padrao"}
    uso = getattr(resposta, "usage_metadata", None)
    if uso is not None:
        for chave, campo in (
            ("prompt", "prompt_token_count"),
            ("em_cache", "cached_content_token_count"),
            ("raciocinio", "thoughts_token_count"),
            ("saida", "candidates_token_count"),
        ):
            valor = getattr(uso, campo, None)
            if valor is not None:
                registro[chave] = valor
        prompt_tokens = getattr(uso, "prompt_token_count", None)
        if prompt_tokens is not None:
            telemetria["tokens_prompt_por_chamada"].append(prompt_tokens)
    telemetria["tokens_por_chamada"].append(registro)


def _finalizar(texto, telemetria):
    """Soma os tokens da resposta, escreve a linha de telemetria no log e devolve (texto, telemetria)."""
    total = {}
    for registro in telemetria["tokens_por_chamada"]:
        for chave in ("prompt", "em_cache", "raciocinio", "saida"):
            if chave in registro:
                total[chave] = total.get(chave, 0) + registro[chave]
    if total:
        telemetria["tokens_total"] = total
        log.info("ia tokens: entrada=%s (em cache=%s) raciocínio=%s saída=%s em %s chamada(s)",
                 total.get("prompt", 0), total.get("em_cache", 0), total.get("raciocinio", 0),
                 total.get("saida", 0), telemetria["chamadas_gemini"])
    return texto, telemetria


def _chamar_com_retentativas(func, max_tentativas=3, espera_inicial=2):
    """
    Tenta de novo quando o Gemini está sobrecarregado (503 UNAVAILABLE) — problema
    momentâneo do lado do Google. Espera crescente (2s, depois 4s). Qualquer outro
    erro (cota, chave inválida etc.) sobe na hora.
    """
    for tentativa in range(max_tentativas):
        try:
            return func()
        except Exception as erro:
            ultima_tentativa = tentativa == max_tentativas - 1
            if "UNAVAILABLE" in str(erro) or "503" in str(erro):
                if ultima_tentativa:
                    raise
                time.sleep(espera_inicial * (2 ** tentativa))
                continue
            raise


# ============================================================
# CAMADA HÍBRIDA — INTERPRETAÇÃO SEM TOOLS
# ============================================================
ACOES_VALIDAS = set(roteador.INTENCOES_ACAO)
MODO_DETERMINISTICO = "deterministico"
MODO_INTERPRETACAO = "interpretar"
MODO_CONVERSA = "conversa"

CONTRATO_ARGUMENTOS = {
    "consultar_tarefas": "status, data_inicio, data_fim",
    "consultar_agenda": "data_inicio, data_fim",
    "consultar_perfil_usuario": "sem argumentos",
    "consultar_aprendizado": "sem argumentos",
    "sugerir_horarios": "data, duracao_minutos",
    "recomendar_tarefa_agora": "sem argumentos",
    "criar_tarefa": "titulo, data_inicio, data_fim, categoria, descricao, confirmar_conflito",
    "configurar_rotina": "descricao, hora_inicio, hora_fim, dias_semana",
    "criar_compromisso": "titulo, data_inicio, data_fim, tipo, local, confirmar_conflito",
    "atualizar_tarefa": "id_tarefa, titulo_busca, novo_titulo, nova_data_inicio, nova_data_fim, nova_categoria, confirmar_conflito",
    "concluir_tarefa": "id_tarefa, titulo_busca",
    "cancelar_tarefa": "id_tarefa, titulo_busca",
    "conversa": "sem argumentos",
}

INSTRUCAO_INTERPRETACAO = """
Você é a camada de interpretação do NEOCORTEX.

Seu trabalho é SOMENTE transformar a mensagem do usuário em UMA OU MAIS ações
e argumentos estruturados. Você não executa nada e não possui ferramentas.

Retorne SOMENTE JSON válido, neste formato:
{
  "acoes": [
    {
      "acao": "consultar_tarefas | consultar_agenda | consultar_perfil_usuario | consultar_aprendizado | sugerir_horarios | recomendar_tarefa_agora | criar_tarefa | configurar_rotina | criar_compromisso | atualizar_tarefa | concluir_tarefa | cancelar_tarefa | conversa",
      "argumentos": {},
      "precisa_clarificacao": false,
      "pergunta": ""
    }
  ],
  "resposta": ""
}

REGRAS IMPORTANTES:
1. Uma mensagem pode conter várias ações independentes. NUNCA descarte uma ação
   clara só porque outra ação da mesma mensagem precisa de esclarecimento.
2. Se houver duas ou mais ações, coloque TODAS em "acoes", na ordem em que o
   usuário apresentou. Cada ação será executada separadamente pelo código.
3. Use a intenção candidata do código quando ela existir, salvo quando o próprio
   contexto demonstrar claramente outra intenção.
4. Extraia apenas informações realmente ditas ou determináveis pelo contexto
   atual fornecido pelo sistema.
4.1. Quando o usuário disser que "tem que ir" a um lugar, tem um compromisso
   ou evento futuro, prefira criar_compromisso em vez de criar_tarefa, se isso
   representar claramente um compromisso de agenda.
5. Para datas relativas (hoje, amanhã, quinta etc.), converta para AAAA-MM-DD
   usando a data/hora atual recebida no CONTEXTO DO SISTEMA.
6. Para horários, use HH:MM. Para duração, use duracao_minutos como inteiro.
7. Para "todos os dias", "todo dia" ou "diariamente" em uma atividade repetida
   com horário, use "configurar_rotina" e preencha dias_semana com:
   ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"].
   Não transforme uma rotina diária em uma única tarefa.
8. Para "configurar_rotina", use descricao, hora_inicio, hora_fim e dias_semana.
8.1. Para "criar_compromisso", use titulo, data_inicio, data_fim, tipo e local.
   Se a data for clara mas o horário não existir, marque precisa_clarificacao=true
   e pergunte apenas o horário necessário.
9. Para tarefas, use somente os campos aceitos pela ação. Não crie campos inventados.
10. Se uma ação estiver incompleta para execução, marque precisa_clarificacao=true
    apenas nessa ação e faça uma pergunta curta sobre o dado que falta.
11. Uma ação incompleta NÃO impede que outras ações completas sejam executadas.
12. Se for apenas conversa/pergunta geral, use acao="conversa".
13. Não afirme que algo foi registrado. A execução acontece depois, no código.
14. Em acao="conversa", coloque a resposta natural em "resposta".
15. Em ações operacionais, não escreva texto em "resposta".
"""

# Tudo que é fixo fica no prompt de sistema (estável entre mensagens = cache do Gemini).
# Só a data/hora, a intenção candidata e a mensagem variam e vão na mensagem do usuário.
SYSTEM_INTERPRETACAO = (
    INSTRUCAO_INTERPRETACAO
    + "\nARGUMENTOS PERMITIDOS POR AÇÃO: " + json.dumps(CONTRATO_ARGUMENTOS, ensure_ascii=False) + "\n"
    + BASE_OPERACIONAL
)


def _extrair_json(texto):
    """Aceita JSON puro e também markdown acidentalmente devolvido pelo modelo."""
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Gemini não devolveu conteúdo.")
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.IGNORECASE)
        texto = re.sub(r"\s*```$", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        inicio = texto.find("{")
        fim = texto.rfind("}")
        if inicio >= 0 and fim > inicio:
            try:
                return json.loads(texto[inicio:fim + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"JSON de interpretação inválido: {erro}") from erro


def _campos_da_acao(acao):
    return set(CONTRATO_ARGUMENTOS.get(acao, "sem argumentos").split(", ")) - {"sem argumentos", ""}


def _validar_comando(comando, roteamento):
    """
    Valida uma ou várias ações antes de qualquer execução. TOLERANTE com o que é
    descartável: argumento que o modelo inventou é ignorado (e registrado no log) em vez
    de derrubar a mensagem inteira, e uma ação desconhecida só some se houver outra válida.
    Estrutura inválida (não é objeto, sem nenhuma ação utilizável) ainda levanta ValueError.
    """
    if not isinstance(comando, dict):
        raise ValueError("A interpretação não é um objeto JSON.")

    itens = comando.get("acoes")
    if itens is None and "acao" in comando:
        itens = [{
            "acao": comando.get("acao"),
            "argumentos": comando.get("argumentos", {}),
            "precisa_clarificacao": comando.get("precisa_clarificacao", False),
            "pergunta": comando.get("pergunta", ""),
        }]
    if not isinstance(itens, list) or not itens:
        raise ValueError("A interpretação precisa devolver ao menos uma ação.")
    if len(itens) > MAX_ACOES_POR_MENSAGEM:
        raise ValueError("A interpretação devolveu ações demais para uma única mensagem.")

    validadas = []
    for item in itens:
        if not isinstance(item, dict):
            log.warning("interpretação: item de ação ignorado (não é objeto): %r", item)
            continue

        acao = str(item.get("acao") or "").strip()
        if acao not in ACOES_VALIDAS and acao != "conversa":
            log.warning("interpretação: ação desconhecida ignorada: %r", acao)
            continue

        argumentos = item.get("argumentos")
        if not isinstance(argumentos, dict):
            argumentos = {}

        desconhecidos = set(argumentos) - _campos_da_acao(acao)
        if desconhecidos:
            log.warning("interpretação: argumentos inventados ignorados em %s: %s", acao, sorted(desconhecidos))
            argumentos = {k: v for k, v in argumentos.items() if k not in desconhecidos}

        precisa = bool(item.get("precisa_clarificacao", False))
        pergunta = str(item.get("pergunta") or "").strip()
        if precisa and not pergunta:
            pergunta = "Pode me dar mais detalhes sobre isso?"

        validadas.append({
            "acao": acao,
            "argumentos": argumentos,
            "precisa_clarificacao": precisa,
            "pergunta": pergunta,
            "resposta": str(item.get("resposta") or "").strip(),
        })

    if not validadas:
        raise ValueError("A interpretação não trouxe nenhuma ação utilizável.")

    if roteamento.intencao_candidata:
        acoes_reais = {item["acao"] for item in validadas if item["acao"] != "conversa"}
        if (roteamento.intencao_candidata in ACOES_VALIDAS
                and roteamento.intencao_candidata not in acoes_reais):
            log.info("interpretação divergiu da intenção candidata: candidata=%s, finais=%s",
                     roteamento.intencao_candidata, sorted(acoes_reais))

    return validadas, str(comando.get("resposta") or "").strip()


def _interpretar_mensagem(mensagem, historico, agora, roteamento, telemetria):
    """
    Chamada ao Gemini sem qualquer tool/function calling. Se o JSON vier inválido
    (por exemplo, cortado), tenta uma vez mais antes de desistir.
    """
    prompt = (
        f"{_linha_de_contexto(agora)}\n\n"
        f"INTENÇÃO CANDIDATA PELO CÓDIGO: {roteamento.intencao_candidata or 'nenhuma'}\n\n"
        f"MENSAGEM DO USUÁRIO:\n{mensagem}"
    )
    contents = _historico_para_conteudo(historico, limite=min(4, roteamento.max_mensagens_historico))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
    parametros = {
        "system_instruction": SYSTEM_INTERPRETACAO,
        "response_mime_type": "application/json",
        "max_output_tokens": GEMINI_MAX_SAIDA_INTERPRETACAO,
    }
    ultimo_erro = None
    for tentativa in (1, 2):
        resposta = _chamar_com_retentativas(
            lambda: _gerar(contents, parametros, GEMINI_THINKING_INTERPRETACAO)
        )
        telemetria["chamadas_gemini"] += 1
        _registrar_uso(telemetria, resposta, GEMINI_THINKING_INTERPRETACAO)
        try:
            return _extrair_json(resposta.text or "")
        except ValueError as erro:
            ultimo_erro = erro
            log.warning("interpretação inválida (tentativa %s/2): %s", tentativa, erro)
    raise ultimo_erro


# ============================================================
# RESPOSTAS DO CÓDIGO (sem segunda chamada ao Gemini)
# ============================================================
PERGUNTA_CONFLITO = "Confirma que quer fazer mesmo assim?"


def _resposta_erro(resultado):
    if not resultado:
        return "Não consegui concluir essa solicitação."
    erro = resultado.get("erro")
    if erro:
        linhas = [erro]
        candidatas = resultado.get("candidatas") or []
        if candidatas:
            linhas.append("Encontrei mais de uma opção:")
            linhas.extend(f"- #{c['id_tarefa']} {c['titulo']}" for c in candidatas[:5])
        return "\n".join(linhas)
    return "Não consegui concluir essa solicitação."


def _formatar_consulta(acao, resultado):
    """Respostas curtas para consultas simples."""
    if "erro" in (resultado or {}):
        return _resposta_erro(resultado)

    if acao == "consultar_tarefas":
        tarefas = resultado.get("tarefas", [])
        if not tarefas:
            return "Você não tem tarefas nesse período."
        linhas = [f"Você tem {resultado.get('total', len(tarefas))} tarefa(s):"]
        for t in tarefas[:LIMITE_TAREFAS_NA_RESPOSTA]:
            atraso = " · atrasada" if t.get("atrasada") else ""
            linhas.append(f"{t['titulo']} — {_quando(t['inicio'], t['fim'])}{atraso} · {t['status']}")
        return "\n".join(linhas)

    if acao == "consultar_agenda":
        blocos = []
        for chave, rotulo in (("tarefas", "Tarefas"), ("compromissos", "Compromissos"), ("rotina", "Rotina")):
            for item in resultado.get(chave, []):
                titulo = item.get("titulo") or item.get("descricao") or "Sem título"
                blocos.append(f"{rotulo}: {titulo} — {_quando(item['inicio'], item['fim'])}")
        if not blocos:
            return "Não encontrei nada ocupando esse período."
        situacao = resultado.get("situacao_agora")
        prefixo = ""
        if situacao:
            prefixo = "Você está ocupado agora" if situacao.get("ocupado_com") else "Você está livre agora"
            if situacao.get("proximo_bloco"):
                prefixo += f"; próximo bloco: {situacao['proximo_bloco']['titulo']}"
            prefixo += ".\n"
        return prefixo + "\n".join(blocos[:LIMITE_TAREFAS_NA_RESPOSTA])

    if acao == "consultar_perfil_usuario":
        perfil = resultado.get("perfil") or {}
        nome = perfil.get("nome", "")
        partes = [f"Perfil de {nome}" if nome else "Seu perfil"]
        if perfil.get("trabalha") is not None:
            partes.append(f"trabalha: {'sim' if perfil['trabalha'] else 'não'}")
        if perfil.get("estuda") is not None:
            partes.append(f"estuda: {'sim' if perfil['estuda'] else 'não'}")
        if perfil.get("turno"):
            partes.append(f"turno: {perfil['turno']}")
        if resultado.get("hobbies"):
            partes.append("hobbies: " + ", ".join(resultado["hobbies"]))
        return " · ".join(partes)

    if acao == "consultar_aprendizado":
        if resultado.get("observacao"):
            return resultado["observacao"]
        partes = []
        if resultado.get("padroes"):
            partes.append("Padrões: " + "; ".join(
                f"{p['tipo']}={p['valor']} ({p.get('fonte','declarado')}, {p.get('confianca','sem confiança')})"
                for p in resultado["padroes"][:8]
            ))
        if resultado.get("divergencia"):
            partes.append(resultado["divergencia"])
        if resultado.get("metricas"):
            partes.append("Métricas: " + "; ".join(f"{k}={v:g}" for k, v in list(resultado["metricas"].items())[:8]))
        return "\n".join(partes) if partes else "Ainda não há aprendizado suficiente para mostrar."

    if acao == "sugerir_horarios":
        sugestoes = resultado.get("sugestoes", [])
        if not sugestoes:
            return resultado.get("observacao", "Não encontrei um horário livre desse tamanho.")
        return "Melhores horários:\n" + "\n".join(
            f"{_quando(s['inicio'], s['fim'])} — " + ", ".join(s.get("base") or [])
            for s in sugestoes
        )

    if acao == "recomendar_tarefa_agora":
        if resultado.get("observacao"):
            return resultado["observacao"]
        for t in resultado.get("candidatas", []):
            if t.get("id_tarefa") == resultado.get("recomendada"):
                return f"Agora, a melhor opção é: {t['titulo']} — {t['motivo']}."
        return "Não encontrei uma tarefa adequada para agora."

    return "Consulta concluída."


def _formatar_acao(acao, resultado):
    if resultado.get("sucesso") is True:
        return linha_de_confirmacao(acao, resultado) or "Concluído."
    if resultado.get("conflitos"):
        conflito = "; ".join(
            f"{c['titulo']} ({_quando(c['inicio'], c['fim'])})" for c in resultado["conflitos"]
        )
        return f"Há conflito com: {conflito}. {PERGUNTA_CONFLITO}"
    return _resposta_erro(resultado)


def _executar_acao(acao, argumentos, executores):
    if acao == "conversa":
        return None
    executor = executores.get(acao)
    if executor is None:
        raise ValueError(f"Executor inexistente para a ação {acao!r}.")
    return _json_seguro(executor(**argumentos))


def _executar_e_formatar(acao, argumentos, executores, telemetria, pendentes_novos):
    """
    Executa UMA ação e devolve o texto para o usuário. Erro de validação (ValueError)
    é mostrado; qualquer outro erro vai para o log e o usuário recebe uma mensagem
    genérica (nunca texto interno de banco ou de biblioteca).
    """
    try:
        resultado = _executar_acao(acao, argumentos, executores)
        telemetria["chamadas_ferramentas"].append(acao)
    except ValueError as erro:
        resultado = {"sucesso": False, "erro": str(erro)}
    except TypeError:
        log.exception("Ação %s sem argumento obrigatório: %r", acao, argumentos)
        resultado = {"sucesso": False, "erro": "Faltou uma informação para fazer isso. Pode repetir com mais detalhes (o quê e quando)?"}
    except Exception:
        log.exception("Falha na ação %s", acao)
        resultado = {"sucesso": False, "erro": "Não consegui concluir essa ação agora. Tenta de novo em um instante."}

    if resultado is None:
        return MENSAGEM_FALHA
    pendente = resultado.pop("_pendente", None)
    if pendente:
        pendentes_novos.append(pendente)
    texto = _formatar_acao(acao, resultado) if acao in FERRAMENTAS_DE_ALTERACAO else _formatar_consulta(acao, resultado)
    return limpar_resposta(texto) if texto else ""


def _executar_deterministico(acao, agora, executores):
    if acao == "saudacao":
        return "Oi! O que você precisa organizar?"
    if acao == "data_atual":
        return f"Hoje é {_DIAS_PT[agora.weekday()]}, {agora:%d/%m/%Y}."
    if acao.startswith("agenda_"):
        dia = acao.split("_", 1)[1]
        if dia == "agora":
            resultado = executores["consultar_agenda"]()
        else:
            alvo = agora.date() if dia == "hoje" else (agora + timedelta(days=1)).date()
            iso = alvo.isoformat()
            resultado = executores["consultar_agenda"](data_inicio=iso, data_fim=iso)
        return _formatar_consulta("consultar_agenda", _json_seguro(resultado))
    raise ValueError(f"Ação determinística desconhecida: {acao}")


# ============================================================
# AÇÃO PENDENTE DE CONFIRMAÇÃO (conflito de agenda)
# O conflito deixa a ação guardada (banco; memória se a tabela ainda não existir).
# O "sim" seguinte a executa direto: não depende de o modelo reescrever o comando
# nem de uma nova chamada ao Gemini.
# ============================================================
MAX_IDADE_PENDENTE_MIN = 15
ACOES_COM_CONFLITO = {"criar_tarefa", "criar_compromisso", "atualizar_tarefa"}
_PENDENTES_MEMORIA = {}
_avisou_tabela_pendentes = False


def _avisar_tabela_pendentes(erro):
    global _avisou_tabela_pendentes
    if not _avisou_tabela_pendentes:
        _avisou_tabela_pendentes = True
        log.warning("Não consegui usar a tabela acoes_pendentes (%s). Rode neocortex_correcoes_migracao.sql. "
                    "Enquanto isso, a confirmação fica só na memória deste processo.", erro)


def _salvar_pendentes(id_usuario, acoes):
    try:
        db.salvar_acoes_pendentes(id_usuario, acoes)
    except Exception as erro:
        _avisar_tabela_pendentes(erro)
        _PENDENTES_MEMORIA[id_usuario] = (time.time(), acoes)


def _buscar_pendentes(id_usuario):
    try:
        return db.buscar_acoes_pendentes(id_usuario, MAX_IDADE_PENDENTE_MIN) or []
    except Exception as erro:
        _avisar_tabela_pendentes(erro)
        item = _PENDENTES_MEMORIA.get(id_usuario)
        if item and time.time() - item[0] <= MAX_IDADE_PENDENTE_MIN * 60:
            return item[1]
        return []


def _apagar_pendentes(id_usuario):
    _PENDENTES_MEMORIA.pop(id_usuario, None)
    try:
        db.apagar_acoes_pendentes(id_usuario)
    except Exception as erro:
        _avisar_tabela_pendentes(erro)


def _executar_pendentes(pendentes, executores, telemetria):
    """Executa as ações guardadas COM a confirmação do usuário. Valida de novo o que veio do armazenamento."""
    respostas, sem_uso = [], []
    for pendente in pendentes:
        acao = pendente.get("acao") if isinstance(pendente, dict) else None
        if acao not in ACOES_COM_CONFLITO:
            continue
        argumentos = pendente.get("argumentos")
        argumentos = argumentos if isinstance(argumentos, dict) else {}
        permitidos = _campos_da_acao(acao)
        argumentos = {k: v for k, v in argumentos.items() if k in permitidos}
        argumentos["confirmar_conflito"] = True
        respostas.append(_executar_e_formatar(acao, argumentos, executores, telemetria, sem_uso))
    return "\n".join(r for r in respostas if r)


# ============================================================
# CONVERSA GERAL
# ============================================================
def _responder_conversa(mensagem, historico, agora, telemetria):
    """Conversa geral: um único chamado, sem tools, com o prompt do perfil escolhido."""
    contents = _historico_para_conteudo(historico, limite=min(6, roteador.MAX_MENSAGENS_HISTORICO))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"{_linha_de_contexto(agora)}\n\n{mensagem}")],
    ))
    parametros = {"system_instruction": prompt_da_conversa()}
    resposta = _chamar_com_retentativas(
        lambda: _gerar(contents, parametros, GEMINI_THINKING_RESPOSTA)
    )
    telemetria["chamadas_gemini"] += 1
    _registrar_uso(telemetria, resposta, GEMINI_THINKING_RESPOSTA)
    texto = limpar_resposta(resposta.text or MENSAGEM_FALHA)
    return _proteger_texto_do_modelo(texto, mensagem)


# ============================================================
# FLUXO PRINCIPAL
# ============================================================
def _acoes_do_interpretador_local(mensagem, agora):
    """Frase clara o bastante para o código interpretar sozinho? Devolve ações no formato do Gemini, ou None."""
    try:
        acoes = interpretador_local.interpretar(mensagem, agora)
    except Exception:
        log.exception("Falha no interpretador local (seguindo para o Gemini)")
        return None
    if not acoes:
        return None
    return {"acoes": [{"acao": a["acao"], "argumentos": a["argumentos"],
                       "precisa_clarificacao": False, "pergunta": ""} for a in acoes]}


def responder_com_telemetria(id_usuario, mensagem, historico=None, agora=None):
    """
    Fluxo híbrido do NEOCORTEX (ver o cabeçalho do arquivo). Devolve (texto, telemetria).
    """
    agora = agora or datetime.now()
    historico = historico or []
    ultima_da_ia = historico[-1].get("conteudo") if historico and historico[-1].get("autor") == "assistente" else None
    executores = _construir_executores(id_usuario, agora)

    telemetria = {
        "modo": None,
        "origem": None,
        "intencoes": [],
        "intencao_candidata": None,
        "chamadas_gemini": 0,
        "chamadas_ferramentas": [],
        "tokens_prompt_por_chamada": [],
        "tokens_por_chamada": [],
    }

    try:
        # 0) "sim"/"não" para uma pergunta de conflito: executa o que ficou guardado
        houve_pergunta_de_conflito = "mesmo assim" in _normalizar(ultima_da_ia or "")
        if houve_pergunta_de_conflito:
            pendentes = _buscar_pendentes(id_usuario)
            if pendentes:
                if roteador.e_confirmacao(mensagem):
                    _apagar_pendentes(id_usuario)
                    telemetria.update(modo="confirmacao", origem="codigo")
                    texto = _executar_pendentes(pendentes, executores, telemetria)
                    return _finalizar(texto or MENSAGEM_FALHA, telemetria)
                _apagar_pendentes(id_usuario)   # recusou ou mudou de assunto: o pedido antigo não vale mais
                if roteador.e_negacao(mensagem):
                    telemetria.update(modo="confirmacao", origem="codigo")
                    return _finalizar("Certo, não registrei nada.", telemetria)

        roteamento = roteador.classificar(mensagem, ultima_da_ia)
        telemetria.update(modo=roteamento.modo, intencoes=roteamento.intencoes,
                          intencao_candidata=roteamento.intencao_candidata)

        # 1) consulta/saudação exata: o código responde
        if roteamento.modo == MODO_DETERMINISTICO:
            telemetria["origem"] = "codigo"
            texto = _executar_deterministico(roteamento.acao_deterministica, agora, executores)
            log.info("ia fluxo determinístico: %s", roteamento.acao_deterministica)
            return _finalizar(texto, telemetria)

        # 4) conversa livre: Gemini com o prompt enxuto
        if roteamento.modo == MODO_CONVERSA:
            telemetria["origem"] = "gemini_conversa"
            texto = _responder_conversa(mensagem, historico, agora, telemetria)
            return _finalizar(texto or MENSAGEM_FALHA, telemetria)

        # 2) frase operacional clara: o código interpreta  /  3) senão, o Gemini
        comando = _acoes_do_interpretador_local(mensagem, agora)
        if comando is not None:
            telemetria["origem"] = "interpretador_local"
        else:
            telemetria["origem"] = "gemini_json"
            comando = _interpretar_mensagem(mensagem, historico, agora, roteamento, telemetria)

        acoes, resposta_geral = _validar_comando(comando, roteamento)
        respostas, perguntas, pendentes_novos = [], [], []

        for item in acoes:
            acao = item["acao"]
            argumentos = dict(item["argumentos"])

            if item["precisa_clarificacao"]:
                perguntas.append(item["pergunta"])
                continue

            if acao == "conversa":
                texto_conversa = item.get("resposta") or resposta_geral
                if texto_conversa:
                    respostas.append(_proteger_texto_do_modelo(str(texto_conversa), mensagem))
                continue

            # A confirmação de conflito é decidida exclusivamente pelo código. Este caminho só
            # é usado se a ação pendente não foi encontrada (expirou, outro processo...).
            if acao in ACOES_COM_CONFLITO:
                argumentos["confirmar_conflito"] = bool(houve_pergunta_de_conflito and roteador.e_confirmacao(mensagem))

            texto = _executar_e_formatar(acao, argumentos, executores, telemetria, pendentes_novos)
            if texto:
                respostas.append(texto)

        if pendentes_novos:
            _salvar_pendentes(id_usuario, pendentes_novos)

        # Ações completas são executadas mesmo quando outra ação da mesma mensagem
        # ainda precisa de um dado. Não perde trabalho já determinado.
        for pergunta in perguntas:
            if pergunta and pergunta not in respostas:
                respostas.append(pergunta)

        texto_final = "\n".join(r for r in respostas if r)
        if not texto_final:
            texto_final = resposta_geral or "Pode me explicar um pouco melhor o que você precisa?"

        log.info("ia fluxo híbrido: origem=%s, acoes=%s, chamadas_gemini=%s, execucoes=%s",
                 telemetria["origem"], [a["acao"] for a in acoes], telemetria["chamadas_gemini"],
                 telemetria["chamadas_ferramentas"])
        return _finalizar(limpar_resposta(texto_final) or MENSAGEM_FALHA, telemetria)

    except Exception as erro:
        log.exception("Falha no fluxo híbrido da IA: %s", erro)
        telemetria["erro"] = str(erro)
        return _finalizar(MENSAGEM_FALHA, telemetria)


def responder(id_usuario, mensagem, historico=None):
    """Ponto de entrada usado pelo app.py. Devolve só o texto da resposta."""
    return responder_com_telemetria(id_usuario, mensagem, historico)[0]





def gerar_titulos_fragmentos(titulo_objetivo, prazo, foco, ritmo, quantidade):
    """
    Única chamada ao Gemini por fragmentação: só os TÍTULOS, sem data/hora —
    isso é responsabilidade do decisao.py (determinístico).
    """
    prazo_texto = prazo.isoformat() if prazo else "sem prazo definido"
    prompt = (
        f'Objetivo do usuário: "{titulo_objetivo}"\n'
        f"Prazo: {prazo_texto}\n"
        f"Foco principal escolhido: {foco}\n"
        f"Ritmo preferido: {ritmo}\n\n"
        f"Divida esse objetivo em exatamente {quantidade} passos concretos, em ordem lógica de progressão "
        f"(do mais básico ao mais avançado). Cada passo é uma ação específica, nunca uma categoria vaga.\n\n"
        f"Responda SOMENTE com um JSON: uma lista de {quantidade} strings, cada uma um título curto "
        f"(máximo 60 caracteres), sem numeração, sem texto além do JSON."
    )

    resposta = _chamar_com_retentativas(lambda: cliente.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    ))

    try:
        titulos = json.loads(resposta.text)
    except (ValueError, AttributeError, TypeError):
        return []
    if not isinstance(titulos, list):
        return []
    return [str(t).strip()[:60] for t in titulos if str(t).strip()][:quantidade]