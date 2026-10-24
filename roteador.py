"""
NEOCORTEX — roteador.py

Roteador leve e determinístico.

Responsabilidade:
- identificar intenções de alta confiança sem chamar o LLM;
- resolver consultas exatas que não precisam de interpretação;
- indicar uma intenção candidata para reduzir o espaço de interpretação do Gemini;
- nunca executar banco, agenda ou ações do usuário.

O roteador NÃO tenta entender toda a linguagem natural. Quando a frase não é
suficientemente clara, a responsabilidade passa ao Gemini, que devolve um
comando estruturado SEM tools. O código valida e executa esse comando depois.
"""

import re
import unicodedata
from dataclasses import dataclass, field


MAX_MENSAGENS_HISTORICO = 6

INTENCOES_ACAO = (
    "consultar_tarefas",
    "consultar_agenda",
    "consultar_perfil_usuario",
    "consultar_aprendizado",
    "sugerir_horarios",
    "recomendar_tarefa_agora",
    "criar_tarefa",
    "configurar_rotina",
    "criar_compromisso",
    "atualizar_tarefa",
    "concluir_tarefa",
    "cancelar_tarefa",
)

SO_ACAO_DETERMINISTICA = {"saudacao", "data_atual", "agenda_hoje", "agenda_amanha", "agenda_agora"}

_SO_SAUDACAO = {
    "oi", "oie", "ola", "opa", "eae", "eai", "salve", "hey", "hello", "hi",
    "bom", "boa", "dia", "tarde", "noite", "tudo", "bem", "td", "blz", "beleza",
    "como", "vai", "voce", "vc", "esta", "ta", "valeu", "vlw", "obrigado", "obrigada",
    "brigado", "brigada", "agradeco", "tmj", "abraco", "abracos", "ate", "logo", "mais",
    "tchau", "flw", "falou", "de", "nada", "por", "favor", "kkk", "kkkk", "haha", "rs",
    "rsrs", "show", "massa", "top", "legal", "otimo",
}

# Pelo menos UMA destas precisa aparecer; "mais tarde", "de noite", "por favor" sozinhos não são saudação.
_NUCLEO_SAUDACAO = {
    "oi", "oie", "ola", "opa", "eae", "eai", "salve", "hey", "hello", "hi", "bom", "boa", "tudo",
    "td", "blz", "beleza", "valeu", "vlw", "obrigado", "obrigada", "brigado", "brigada",
    "agradeco", "tmj", "abraco", "abracos", "tchau", "flw", "falou", "kkk", "kkkk", "haha",
    "rs", "rsrs", "show", "massa", "top", "legal", "otimo",
}

_CONSULTAS_DATA_ATUAL = {
    "que dia e hoje", "qual dia e hoje", "qual a data de hoje", "data de hoje",
}

_CONSULTAS_AGENDA_EXATAS = (
    re.compile(r"^(?:o que|quais)\s+(?:eu\s+)?(?:tenho|tenho de)\s+(?:na\s+agenda\s+)?(hoje|amanha|agora)$"),
    re.compile(r"^(?:qual(?: e)?\s+)?(?:a\s+)?(?:minha\s+)?agenda\s+(?:de\s+)?(hoje|amanha|agora)$"),
    re.compile(r"^tenho algo\s+(?:na\s+agenda\s+)?(hoje|amanha|agora)$"),
)

_PATTERNS = {
    "consultar_tarefas": (
        re.compile(r"\b(tarefa|tarefas|pendencia|pendencias|pendente|pendentes)\b"),
        re.compile(r"\b(list(a|e|ar)|mostrar|mostra|ver|tenho|quais|o que)\w*\b"),
    ),
    "consultar_agenda": (
        re.compile(r"\b(agenda|calendario|compromisso|compromissos)\b"),
        re.compile(r"\b(tenho|mostrar|mostra|ver|quais|o que|livre|ocupado)\b"),
    ),
    "consultar_perfil_usuario": (
        re.compile(r"\b(meu|meus|minha|minhas)\b"),
        re.compile(r"\b(perfil|dados|cadastro|trabalho|estudo|hobbies?|preferencias?)\b"),
    ),
    "consultar_aprendizado": (
        re.compile(r"\b(padrao|padroes|produtividade|comportamento|historico|aprendeu|aprendizado|desempenho)\b"),
        re.compile(r"\b(como|qual|quais|o que|me mostra|me mostre|tenho)\b"),
        re.compile(r"\b(como estou indo|como estou|meu progresso|meu desempenho)\b"),
    ),
    "sugerir_horarios": (
        re.compile(r"\b(melhor|melhores|suger(e|ir)|sugest(ao|oes)|horario|horarios|quando posso|quando consigo|janela|janelas)\b"),
        re.compile(r"\b(livre|disponivel|disponiveis|encaixar|marcar)\b"),
        re.compile(r"\b(quando posso|quando consigo)\b"),
    ),
    "recomendar_tarefa_agora": (
        re.compile(r"\b(agora|neste momento|nesse momento)\b"),
        re.compile(r"\b(o que|qual|devo|fac(o|a)|fa(c|ç)o)\b"),
    ),
    "criar_tarefa": (
        re.compile(r"\b(coloc\w*|bot(a|e|ar)|ponh\w*|poe|adicion\w*|cri\w*|agend\w*|anot\w*|registr\w*|inclu\w*|insir\w*|program\w*|marc\w*)\b"),
        re.compile(r"\b(dia|amanha|hoje|segunda|terca|quarta|quinta|sexta|sabado|domingo|\d{1,2}/\d{1,2})\b|\b\d{1,2}([h:]|\s+h)"),
    ),
    "criar_compromisso": (
        re.compile(r"\b(tenho|vou|preciso|vou ter|fui convidad[oa]|tem)\b"),
        re.compile(r"\b(amanha|hoje|segunda|terca|quarta|quinta|sexta|sabado|domingo|dia\s+\d{1,2}|\d{1,2}/\d{1,2})\b"),
        re.compile(r"\b(ir|visitar|visita|casa|dentista|medico|medica|reuniao|consulta|evento|compromisso)\b"),
    ),
    "configurar_rotina": (
        re.compile(r"\b(todos?\s+os\s+dias|todo\s+dia|diariamente|rotina|toda\s+semana)\b"),
        re.compile(r"\b\d{1,2}(?::\d{2}|\s*h(?:oras?)?)\b"),
    ),
    "atualizar_tarefa": (
        re.compile(r"\b(adi(a|ar)|adi(em|e)|reagend\w*|remarc\w*|muda\w*|alter\w*|troca\w*|antecipa\w*|empurr\w*)\b"),
        re.compile(r"\b(tarefa|horario|data|prazo)\b"),
    ),
    "concluir_tarefa": (
        re.compile(r"\b(conclu\w*|terminei|finaliz\w*|fiz)\b"),
        re.compile(r"\b(tarefa|tarefas|atividade|atividades)\b"),
    ),
    "cancelar_tarefa": (
        re.compile(r"\b(cancel\w*|remov\w*|apag\w*|exclu\w*)\b"),
        re.compile(r"\b(tarefa|tarefas|atividade|atividades)\b"),
    ),
}


# Verbos e substantivos que indicam pedido operacional. A lista antiga não tinha
# "terminei", "adia", "anota", "marca", "coloca", "bota"..., e esses pedidos
# caíam em "conversa" (o modelo respondia sem executar nada).
_RE_SINAL_OPERACIONAL = re.compile(
    r"\b(agenda|calendario|tarefas?|compromissos?|horarios?|rotina|pendencias?|pendentes?|"
    r"cancel\w*|conclu\w*|termin\w*|finaliz\w*|fiz|feito|agend\w*|adicion\w*|cria\w*|registr\w*|"
    r"anot\w*|coloc\w*|bot(?:a|e|ar)|ponh\w*|poe|marc\w*|remarc\w*|inclu\w*|insir\w*|program\w*|"
    r"adi(?:a|ar|e|em)|reagend\w*|muda\w*|alter\w*|troca\w*|antecipa\w*|empurr\w*|"
    r"remov\w*|apag\w*|exclu\w*|lembr\w*|suger\w*|sugest\w*|"
    r"padrao|padroes|produtividade|aprendizado|desempenho|progresso|como estou indo|o que eu deveria fazer|"
    r"semana|atrasad\w*|livre|ocupad\w*|disponivel|disponiveis|pendente|pendentes)\b"
    r"|\b(?:meus?|minhas?)\s+(?:perfil|dados|cadastro|hobbies?|preferencias?)\b"
    r"|\bo que (?:eu )?(?:tenho|faco|fazer|preciso|devo)\b|\b(?:tenho|devo|preciso)\s+(?:de\s+)?fazer\b"
)
# Data ou hora na frase: mesmo informal, pode ser um pedido; deixa o código/IA de interpretação decidir.
_RE_SINAL_DE_TEMPO = re.compile(
    r"\b(hoje|amanha|depois de amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo)\b"
    r"|\b\d{1,2}/\d{1,2}\b|\b\d{1,2}\s*h\b|\b\d{1,2}:\d{2}\b"
)


def normalizar(texto):
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _palavras(texto):
    return re.findall(r"[a-z0-9]+", normalizar(texto))


def e_so_saudacao(mensagem):
    palavras = _palavras(mensagem)
    return (0 < len(palavras) <= 6
            and all(p in _SO_SAUDACAO for p in palavras)
            and any(p in _NUCLEO_SAUDACAO for p in palavras))


_PALAVRAS_AFIRMACAO = {
    "sim", "s", "pode", "ser", "faz", "faca", "fazer", "cria", "crie", "criar", "vai", "manda", "ok", "okay",
    "fechado", "fechou", "confirmo", "confirma", "confirmar", "isso", "claro", "certeza", "com", "bora",
    "mesmo", "assim", "quero", "por", "favor", "pf", "pfv", "uhum", "aham", "beleza", "blz", "combinado",
    "ta", "sim", "salva", "salve", "registra", "registre", "agenda", "marca", "pode", "sem", "problema",
}
_NUCLEO_AFIRMACAO = {
    "sim", "s", "pode", "faz", "faca", "fazer", "cria", "crie", "criar", "vai", "manda", "ok", "okay",
    "fechado", "fechou", "confirmo", "confirma", "confirmar", "isso", "claro", "bora", "quero", "uhum",
    "aham", "beleza", "blz", "combinado", "salva", "salve", "registra", "registre", "agenda", "marca",
}
_PALAVRAS_NEGACAO = {
    "nao", "n", "nope", "nunca", "deixa", "deixe", "esquece", "esqueca", "desisti", "desisto",
    "cancela", "cancele", "negativo",
}


def e_confirmacao(mensagem):
    """'sim', 'pode ser', 'faz mesmo assim', 'ok'... Curta, sem negação: resposta a "confirma?"."""
    palavras = _palavras(mensagem)
    return (0 < len(palavras) <= 6
            and all(p in _PALAVRAS_AFIRMACAO for p in palavras)
            and any(p in _NUCLEO_AFIRMACAO for p in palavras))


def e_negacao(mensagem):
    """'não', 'deixa pra lá', 'melhor não'... Curta: resposta a "confirma?"."""
    palavras = _palavras(mensagem)
    return 0 < len(palavras) <= 6 and any(p in _PALAVRAS_NEGACAO for p in palavras)


def _consulta_deterministica(mensagem):
    texto = normalizar(mensagem).strip()
    texto = re.sub(r"[?.!,;:]+$", "", texto).strip()
    if texto in _CONSULTAS_DATA_ATUAL:
        return "data_atual"
    for padrao in _CONSULTAS_AGENDA_EXATAS:
        achou = padrao.fullmatch(texto)
        if achou:
            return f"agenda_{achou.group(1)}"
    return None


def _pontuar_intencoes(mensagem):
    texto = normalizar(mensagem)
    pontos = {}
    for intencao, padroes in _PATTERNS.items():
        valor = 0
        for padrao in padroes:
            if padrao.search(texto):
                valor += 1
        if valor:
            pontos[intencao] = valor
    return pontos


@dataclass
class Roteamento:
    modo: str = "interpretar"  # deterministico | interpretar | conversa
    intencoes: list = field(default_factory=list)
    intencao_candidata: str | None = None
    acao_deterministica: str | None = None
    max_mensagens_historico: int = MAX_MENSAGENS_HISTORICO

    @property
    def ferramentas(self):
        """Compatibilidade com o código antigo: nenhuma tool é entregue ao LLM."""
        return []


def classificar(mensagem, ultima_resposta_da_ia=None):
    texto = normalizar((mensagem or "").strip())
    pergunta_pendente = "?" in (ultima_resposta_da_ia or "")

    if not pergunta_pendente and e_so_saudacao(texto):
        return Roteamento(modo="deterministico", intencoes=["saudacao"], acao_deterministica="saudacao")

    if not pergunta_pendente:
        acao = _consulta_deterministica(texto)
        if acao:
            return Roteamento(modo="deterministico", intencoes=["consulta_deterministica"], acao_deterministica=acao)

    # Recorrência diária com faixa de horário representa rotina fixa no modelo
    # atual do banco. Damos preferência a essa intenção para evitar que uma
    # mensagem como "Alura todos os dias das 6 às 8" seja tratada como uma
    # única tarefa.
    if re.search(r"\b(todos?\s+os\s+dias|todo\s+dia|diariamente)\b", texto) and re.search(
        r"\b(?:das?|as?|ate)\s+\d{1,2}(?::\d{2}|\s*h(?:oras?)?)?\b|\b\d{1,2}(?::\d{2}|\s*h(?:oras?)?)\b", texto
    ):
        return Roteamento(modo="interpretar", intencoes=["configurar_rotina"], intencao_candidata="configurar_rotina")

    pontos = _pontuar_intencoes(texto)
    if pontos:
        ordenadas = sorted(pontos.items(), key=lambda item: (-item[1], item[0]))
        melhor, maior = ordenadas[0]
        segundo = ordenadas[1][1] if len(ordenadas) > 1 else 0
        # Só damos uma dica forte ao LLM quando existe sinal suficiente e
        # vantagem clara sobre as alternativas.
        if maior >= 2 and maior > segundo:
            return Roteamento(modo="interpretar", intencoes=[melhor], intencao_candidata=melhor)

    # Qualquer sinal operacional (verbo de agenda, data ou horário) vai para a interpretação:
    # é a chamada barata (prompt curto, JSON). O Gemini ainda decide a ação exata e,
    # se for só conversa, devolve acao="conversa" — sem nenhuma tool.
    if _RE_SINAL_OPERACIONAL.search(texto) or _RE_SINAL_DE_TEMPO.search(texto) or pergunta_pendente:
        return Roteamento(modo="interpretar", intencoes=["conteudo"], intencao_candidata=None)

    # Fala claramente não operacional: conversa direta (a única chamada com o prompt longo do agente).
    return Roteamento(modo="conversa", intencoes=["conversa"])


def parece_pedido_de_registro(mensagem):
    """Compatibilidade: detecta apenas o sinal de que havia pedido de registro."""
    texto = normalizar(mensagem)
    if "?" in texto:
        return False
    return bool(re.search(r"\b(coloc\w*|bot\w*|adicion\w*|cri\w*|agend\w*|anot\w*|registr\w*)\b", texto) and
                re.search(r"\b(dia|amanha|hoje|segunda|terca|quarta|quinta|sexta|sabado|domingo)\b|\b\d{1,2}([h:]|\s+h)", texto))
