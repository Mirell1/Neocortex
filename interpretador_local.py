"""
NEOCORTEX — interpretador_local.py

Interpreta SEM chamar o Gemini as frases operacionais mais comuns e inequívocas:

    "coloca dentista amanhã 15h"            -> criar_tarefa
    "bota academia sexta das 17h às 18h"    -> criar_tarefa
    "adia a academia pra amanhã 7h"         -> atualizar_tarefa
    "terminei o relatório"                  -> concluir_tarefa
    "cancela a tarefa de estudar"           -> cancelar_tarefa

Regra de ouro: na menor dúvida devolve None, e quem interpreta é o Gemini. Só
reconhece frases COMPLETAS (a data e a hora no fim, uma única data, uma única
ação). O que não for exatamente isso (várias ações, datas ambíguas como "sexta"
dita numa sexta, horário sem período como "às 3", pergunta, compromisso como
"reunião" ou "dentista") continua indo para o Gemini.

Não consulta banco e não executa nada: devolve a mesma estrutura de ação que o
Gemini devolveria, e o ai.py valida e executa pelo mesmo caminho.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta

MAX_CARACTERES = 160

_DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}

# Palavras que sugerem compromisso (evento com hora marcada), não tarefa: deixa o Gemini decidir.
_PALAVRAS_DE_COMPROMISSO = {
    "reuniao", "consulta", "dentista", "medico", "medica", "aula", "evento", "compromisso", "visita",
    "entrevista", "show", "festa", "casamento", "aniversario", "voo", "viagem", "exame", "audiencia",
    "cinema", "jantar", "almoco", "formatura", "velorio", "enterro",
}
_TITULOS_GENERICOS = {
    "tudo", "todas", "todos", "tarefa", "tarefas", "as tarefas", "minhas tarefas", "todas as tarefas",
    "tudo isso", "isso", "essa", "esse", "aquela", "aquele",
}
_PALAVRAS_QUE_NAO_SAO_TAREFA = {"compromisso", "compromissos", "rotina", "agenda", "tarefas", "todas", "todos", "tudo"}

_VERBOS_CRIAR = r"(?:coloca|coloque|colocar|bota|bote|botar|poe|ponha|adiciona|adicione|adicionar|anota|anote|anotar|agenda|agende|agendar|cria|crie|criar)"
_VERBOS_ADIAR = r"(?:adia|adie|adiar|remarca|remarque|remarcar|reagenda|reagende|reagendar|muda|mude|mudar|passa|passe|passar|move|mova|mover|transfere|transfira|transferir)"
_VERBOS_CONCLUIR = r"(?:conclui|concluir|concluiu|terminei|finalizei|finalizar|completei|completar)"
_VERBOS_CANCELAR = r"(?:cancela|cancele|cancelar|remove|remova|remover|apaga|apague|apagar|exclui|exclua|excluir|deleta|delete|deletar)"

_ARTIGO = r"(?:(?:a|o|as|os|uma|um)\s+)?"
_DATA = (r"(?:depois de amanha|amanha|hoje|(?:segunda|terca|quarta|quinta|sexta)(?:-feira)?|sabado|domingo"
         r"|(?:no\s+)?dia\s+\d{1,2}|\d{1,2}/\d{1,2})")
_TEMPO = r"\d{1,2}\s*(?:hs?\s*\d{2}|hs?(?:oras?)?|:\s*\d{2})"
_PERIODO = r"(?:\s+(?:da|de)\s+(?P<per>manha|tarde|noite))?"

_RE_CRIAR = re.compile(
    rf"^{_VERBOS_CRIAR}\s+{_ARTIGO}(?:tarefa\s+)?(?:de\s+)?(?P<titulo>.+?)\s+(?:(?:para|pra|no|na|em|d[ao])\s+)?"
    rf"(?P<data>{_DATA})\s+(?:(?P<pre>a partir das?|das?|as|de)\s+)?(?P<ini>{_TEMPO}|(?(pre)\d{{1,2}}(?!\d)))"
    rf"(?:\s*(?:as|ate|a|-)\s*(?P<fim>{_TEMPO}|\d{{1,2}}(?!\d)))?{_PERIODO}$"
)
_RE_ADIAR = re.compile(
    rf"^{_VERBOS_ADIAR}\s+{_ARTIGO}(?:tarefa\s+(?:de\s+)?)?(?P<titulo>.+?)\s+(?:para|pra|pro)\s+{_ARTIGO}"
    rf"(?P<data>{_DATA})\s+(?:(?P<pre>as|a partir das?|de)\s+)?(?P<ini>{_TEMPO}|(?(pre)\d{{1,2}}(?!\d))){_PERIODO}$"
)
_RE_CONCLUIR = re.compile(rf"^{_VERBOS_CONCLUIR}\s+(?:de\s+)?{_ARTIGO}(?:tarefa\s+(?:de\s+)?)?(?P<titulo>.+)$")
_RE_CANCELAR = re.compile(rf"^{_VERBOS_CANCELAR}\s+{_ARTIGO}(?:tarefa\s+(?:de\s+)?)?(?P<titulo>.+)$")

_RE_DATAS = re.compile(rf"\b{_DATA}\b")
_RE_TEMPOS = re.compile(_TEMPO)
_RE_RECORRENTE = re.compile(r"\b(todo\s+dia|todos\s+os\s+dias|diariamente|toda\s+semana|toda\s+(?:segunda|terca|quarta|quinta|sexta)|todo\s+(?:sabado|domingo))\b")
_RE_FINAL_SOLTO = re.compile(r"\s+(?:hoje|agora|ja|ontem|mesmo|por favor|pf|pfv)$")


# ============================================================
# NORMALIZAÇÃO ALINHADA
# ============================================================
def _normalizar_alinhado(texto):
    """
    minúsculas e sem acento, UM caractere de saída para cada caractere de entrada,
    para que as posições achadas no texto normalizado valham no texto original
    (o título é extraído do original, mantendo acentos e maiúsculas).
    """
    saida = []
    for ch in texto:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
        base = base.lower()
        saida.append(base if len(base) == 1 else ch)
    return "".join(saida)


# ============================================================
# DATAS E HORAS
# ============================================================
def _resolver_data(token, hoje):
    """Texto -> date, ou None se for ambíguo/inválido (o Gemini decide)."""
    token = token.strip()
    if token == "hoje":
        return hoje
    if token == "amanha":
        return hoje + timedelta(days=1)
    if token == "depois de amanha":
        return hoje + timedelta(days=2)
    nome = token.replace("-feira", "")
    if nome in _DIAS_SEMANA:
        distancia = (_DIAS_SEMANA[nome] - hoje.weekday()) % 7
        return None if distancia == 0 else hoje + timedelta(days=distancia)   # "sexta" dita numa sexta: ambíguo
    achou = re.fullmatch(r"(?:no\s+)?dia\s+(\d{1,2})", token)
    if achou:
        dia = int(achou.group(1))
        for deslocamento in (0, 1):
            ano, mes = hoje.year, hoje.month + deslocamento
            if mes > 12:
                ano, mes = ano + 1, 1
            try:
                candidata = date(ano, mes, dia)
            except ValueError:
                continue
            if candidata >= hoje:
                return candidata
        return None
    achou = re.fullmatch(r"(\d{1,2})/(\d{1,2})", token)
    if achou:
        try:
            candidata = date(hoje.year, int(achou.group(2)), int(achou.group(1)))
        except ValueError:
            return None
        return candidata if candidata >= hoje else None   # data já passada: ambíguo
    return None


def _resolver_hora(token, periodo):
    """'15h30', '9', '15:30' (+ período) -> (hora, minuto), ou None se ambíguo/inválido."""
    achou = re.fullmatch(r"(\d{1,2})\s*(?:(?:hs?(?:oras?)?)\s*(\d{2})?|:\s*(\d{2}))?", token.strip())
    if not achou:
        return None
    hora = int(achou.group(1))
    minuto = int(achou.group(2) or achou.group(3) or 0)
    if hora > 23 or minuto > 59:
        return None
    if periodo in ("tarde", "noite") and hora < 12:
        hora += 12
    elif periodo == "manha" and hora == 12:
        hora = 0
    elif periodo is None and 1 <= hora <= 6:
        return None   # "às 3": 3h da manhã ou da tarde? deixa o Gemini decidir
    return hora, minuto


def _iso(dia, hora_minuto):
    return datetime(dia.year, dia.month, dia.day, hora_minuto[0], hora_minuto[1]).isoformat(timespec="minutes")


# ============================================================
# TÍTULOS
# ============================================================
def _titulo_ok(titulo, minimo=2, maximo=80):
    if not (minimo <= len(titulo) <= maximo) or not re.search(r"[A-Za-zÀ-ÿ]", titulo):
        return False
    return "?" not in titulo and ";" not in titulo


def _limpar_titulo_busca(titulo):
    """Tira 'hoje/agora/já' soltos no fim: 'terminei a academia hoje' busca 'academia'."""
    anterior = None
    while anterior != titulo:
        anterior = titulo
        titulo = _RE_FINAL_SOLTO.sub("", titulo).strip()
    return titulo


def _titulo_busca_valido(titulo_norm):
    palavras = re.findall(r"[a-z0-9]+", titulo_norm)
    if not any(len(p) >= 3 for p in palavras):
        return False
    if titulo_norm.strip() in _TITULOS_GENERICOS or _PALAVRAS_QUE_NAO_SAO_TAREFA & set(palavras):
        return False
    return "?" not in titulo_norm and len(palavras) <= 8


# ============================================================
# INTERPRETAÇÃO
# ============================================================
def interpretar(mensagem, agora):
    """
    Retorna uma lista com UMA ação ({'acao', 'argumentos'}) quando a frase é clara,
    ou None quando o Gemini deve interpretar.
    """
    original = (mensagem or "").strip()
    original = re.sub(r"[\s]+", " ", original)
    original = re.sub(r"[.!]+$", "", original).strip()
    if not original or len(original) > MAX_CARACTERES or "?" in original:
        return None
    texto = _normalizar_alinhado(original)
    if len(texto) != len(original):
        return None
    if _RE_RECORRENTE.search(texto):
        return None   # rotina: o Gemini (configurar_rotina) cuida

    hoje = agora.date()

    # ---- concluir / cancelar (alteram uma tarefa existente, achada pelo título)
    for regex, acao in ((_RE_CONCLUIR, "concluir_tarefa"), (_RE_CANCELAR, "cancelar_tarefa")):
        achou = regex.match(texto)
        if achou:
            titulo = _limpar_titulo_busca(texto[achou.start("titulo"):achou.end("titulo")].strip())
            if not _titulo_busca_valido(titulo) or _RE_DATAS.search(titulo):
                return None
            return [{"acao": acao, "argumentos": {"titulo_busca": titulo}}]

    # ---- criar / adiar: exigem UMA data e horário no fim da frase
    if len(_RE_DATAS.findall(texto)) != 1 or len(_RE_TEMPOS.findall(texto)) > 2:
        return None

    achou = _RE_ADIAR.match(texto)
    if achou:
        dia = _resolver_data(achou.group("data"), hoje)
        hora = _resolver_hora(achou.group("ini"), achou.group("per"))
        titulo = texto[achou.start("titulo"):achou.end("titulo")].strip()
        if dia is None or hora is None or not _titulo_busca_valido(titulo):
            return None
        return [{"acao": "atualizar_tarefa",
                 "argumentos": {"titulo_busca": titulo, "nova_data_inicio": _iso(dia, hora)}}]

    achou = _RE_CRIAR.match(texto)
    if achou:
        titulo_original = original[achou.start("titulo"):achou.end("titulo")].strip(" ,-")
        titulo_norm = texto[achou.start("titulo"):achou.end("titulo")]
        if not _titulo_ok(titulo_original) or _PALAVRAS_DE_COMPROMISSO & set(re.findall(r"[a-z]+", titulo_norm)):
            return None
        dia = _resolver_data(achou.group("data"), hoje)
        periodo = achou.group("per")
        inicio = _resolver_hora(achou.group("ini"), periodo)
        if dia is None or inicio is None:
            return None
        argumentos = {"titulo": titulo_original, "data_inicio": _iso(dia, inicio)}
        if achou.group("fim"):
            fim = _resolver_hora(achou.group("fim"), periodo)
            if fim is None or fim <= inicio:
                return None
            argumentos["data_fim"] = _iso(dia, fim)
        return [{"acao": "criar_tarefa", "argumentos": argumentos}]

    return None
