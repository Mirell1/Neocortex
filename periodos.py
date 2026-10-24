"""
NEOCORTEX — periodos.py

Regras de "período do dia" e de energia declarada, em UM lugar só. Sem
dependência de banco, para que agenda, aprendizado, ml_preparacao e
analise_energia (inclusive --demo, sem PostgreSQL) usem exatamente a mesma regra.
"""

import unicodedata

PERIODOS = ("manha", "tarde", "noite")
ENERGIAS_VALIDAS = PERIODOS + ("nao_sei",)

JANELA_LOTE_MIN = 10   # conclusões a menos de N min uma da outra = "lote" = 1 evento


def periodo_da_hora(hora):
    """manha 05-11h, tarde 12-17h, noite 18h até 04h."""
    if 5 <= hora < 12:
        return "manha"
    if 12 <= hora < 18:
        return "tarde"
    return "noite"


def normalizar_texto(texto):
    """minúsculas e sem acentos: 'Manhã' -> 'manha'."""
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def normalizar_periodo(valor):
    """'Manhã', 'manha', ' MANHÃ ' -> 'manha'. 'nao_sei' ou qualquer outro valor -> None."""
    v = normalizar_texto(valor).strip()
    return v if v in PERIODOS else None


def normalizar_energia(valor):
    """Energia declarada: 'manha' | 'tarde' | 'noite' | 'nao_sei' (aceita 'Manhã', 'Não sei'); inválido -> None."""
    v = normalizar_texto(valor).strip().replace(" ", "_")
    return v if v in ENERGIAS_VALIDAS else None
