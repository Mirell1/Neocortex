"""
NEOCORTEX - seguranca.py
Peças pequenas de segurança, sem dependências além da biblioteca padrão (por isso dá para testar sozinhas):

  LimiteTentativas      limite de tentativas (usado no login), com janela deslizante, em memória
  aplicar_cabecalhos    cabeçalhos de segurança de todas as respostas
  senha_valida          regras de tamanho da senha (mínimo e o limite de 72 bytes do bcrypt)
  acessibilidade_valida só aceita os valores que as telas realmente oferecem

Limite conhecido do LimiteTentativas: o contador fica na MEMÓRIA de cada processo. Com um único processo (o caso de
uma instância simples) ele funciona como descrito; com vários workers do gunicorn cada um conta por conta própria
(o limite efetivo fica multiplicado pelo número de workers). Reiniciar o servidor zera os contadores.
"""
import math
import threading
import time
from collections import deque

SENHA_MIN = 8
SENHA_MAX_BYTES = 72    # o bcrypt só usa os primeiros 72 bytes (e as versões novas recusam senhas maiores)

ACESSIBILIDADE = {      # o que as telas de Configurações oferecem; o primeiro de cada lista é o padrão
    "acess_fonte": ("normal", "grande", "maior"),
    "acess_contraste": ("normal", "alto"),
    "acess_tipografia": ("padrao", "dislexia"),
}

CABECALHOS = {
    "X-Content-Type-Options": "nosniff",                       # o navegador não "adivinha" o tipo do arquivo
    "X-Frame-Options": "DENY",                                 # a página não pode ser embutida em outro site (clickjacking)
    "Referrer-Policy": "strict-origin-when-cross-origin",      # não vaza endereços internos para outros sites
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=()",   # microfone só para o ditado do próprio site
}


class LimiteTentativas:
    """Bloqueia uma chave depois de `maximo` falhas dentro de `janela` segundos (janela deslizante)."""

    def __init__(self, maximo=5, janela=900, relogio=time.monotonic, max_chaves=20000):
        self.maximo = maximo
        self.janela = janela
        self.max_chaves = max_chaves
        self._agora = relogio
        self._falhas = {}                 # chave -> fila de instantes das falhas
        self._trava = threading.Lock()

    def _podar(self, chave, agora):
        fila = self._falhas.get(chave)
        if fila is None:
            return None
        while fila and agora - fila[0] >= self.janela:
            fila.popleft()
        if not fila:
            del self._falhas[chave]
            return None
        return fila

    def espera(self, chave):
        """Segundos até a pessoa poder tentar de novo. 0 = livre."""
        with self._trava:
            agora = self._agora()
            fila = self._podar(chave, agora)
            if fila is None or len(fila) < self.maximo:
                return 0
            libera_em = fila[len(fila) - self.maximo] + self.janela     # quando o número de falhas cai abaixo do máximo
            return max(1, math.ceil(libera_em - agora))

    def registrar_falha(self, chave):
        with self._trava:
            agora = self._agora()
            fila = self._podar(chave, agora)
            if fila is None:
                if len(self._falhas) >= self.max_chaves:
                    self._abrir_espaco(agora)
                fila = self._falhas.setdefault(chave, deque())
            fila.append(agora)

    def limpar(self, chave):
        with self._trava:
            self._falhas.pop(chave, None)

    def _abrir_espaco(self, agora):
        """Evita crescer sem limite se alguém gerar milhares de chaves: descarta as vencidas e, se precisar, as mais antigas."""
        for chave in list(self._falhas):
            self._podar(chave, agora)
        excesso = len(self._falhas) - int(self.max_chaves * 0.9)
        for chave in list(self._falhas)[:max(0, excesso)]:
            del self._falhas[chave]

    def quantas_chaves(self):
        with self._trava:
            return len(self._falhas)


def chave_conta(ip, email):
    """Chave por conta + IP: quem erra de um IP não tranca a conta para o dono, que acessa de outro."""
    return f"{ip}|{(email or '').strip().lower()[:254]}"


def senha_valida(senha, minimo=SENHA_MIN, maximo_bytes=SENHA_MAX_BYTES):
    """Devolve a mensagem de erro (em português) ou None se a senha serve."""
    if len(senha) < minimo:
        return f"A senha precisa ter pelo menos {minimo} caracteres."
    if len(senha.encode("utf-8")) > maximo_bytes:
        return f"A senha é longa demais (máximo de {maximo_bytes} bytes; acentos e emojis contam mais de um)."
    return None


def acessibilidade_valida(chave, valor):
    """Devolve o valor se for um dos oferecidos; senão, o padrão. Também limpa valores estranhos que já estejam salvos."""
    permitidos = ACESSIBILIDADE[chave]
    return valor if valor in permitidos else permitidos[0]


def aplicar_cabecalhos(resposta, https=False, endpoint=None):
    for nome, valor in CABECALHOS.items():
        resposta.headers.setdefault(nome, valor)
    if https:
        resposta.headers.setdefault("Strict-Transport-Security", "max-age=15552000")     # 180 dias, só em produção com HTTPS
    if endpoint not in ("static", "favicon") and resposta.mimetype == "text/html":
        resposta.headers["Cache-Control"] = "no-store"          # páginas logadas não ficam guardadas no navegador (botão Voltar após sair)
    return resposta
