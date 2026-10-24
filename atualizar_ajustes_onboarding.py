"""
NEOCORTEX - atualizar_ajustes_onboarding.py

Dois ajustes pequenos, achados ao testar o onboarding real inteiro:

  1. static/onboarding.js - o CONTADOR DE PROGRESSO ("3 / 20" e a barra) contava a partir de "areas_melhoria", mas a primeira
     pergunta hoje é "acessibilidade". Resultado: as duas primeiras telas mostravam "1 / 20", todas as outras ficavam uma
     casa atrás e a última pergunta mostrava 19/20 (95%), nunca 20/20. Agora a contagem começa na primeira pergunta de verdade.

  2. templates/cadastro_conta.html - a tela pedia "mínimo 8 caracteres", mas o campo aceitava 6 (minlength="6"); o servidor exige 8
     e só então recusava. Agora o navegador já avisa com 8.

Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_ajustes_onboarding.py            # só mostra
    python atualizar_ajustes_onboarding.py --aplicar  # grava (cópia .bak de cada arquivo)

Rodar de novo é seguro. Se não reconhecer um trecho, NÃO mexe naquele arquivo e explica.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

CONTADOR_ANTES = '  let id = "areas_melhoria";'
CONTADOR_DEPOIS = '  let id = progressSequence[0];   // [CONTADOR] começa na primeira pergunta de verdade (hoje, a de acessibilidade)'
RE_SENHA = re.compile(r'(<input id="suPassword"[^>]*?)minlength="6"')


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def ajustar_contador(texto):
    if "[CONTADOR]" in texto:
        return None, "static/onboarding.js: o contador já começa na primeira pergunta (nada a fazer)."
    if texto.count(CONTADOR_ANTES) != 1 or "function getPathSoFar()" not in texto:
        return None, ("static/onboarding.js: NÃO reconheci a função getPathSoFar (esperava a linha  " + CONTADOR_ANTES.strip() + ").\n"
                      "  Faça à mão: nessa função, troque \"areas_melhoria\" por progressSequence[0].")
    return texto.replace(CONTADOR_ANTES, CONTADOR_DEPOIS, 1), "static/onboarding.js: o contador agora começa na primeira pergunta (acessibilidade)."


def ajustar_senha(texto):
    if 'id="suPassword"' in texto and not RE_SENHA.search(texto):
        if re.search(r'<input id="suPassword"[^>]*minlength="8"', texto):
            return None, "templates/cadastro_conta.html: o campo já exige 8 caracteres (nada a fazer)."
    if len(RE_SENHA.findall(texto)) != 1:
        return None, ("templates/cadastro_conta.html: NÃO achei o campo da senha com minlength=\"6\".\n"
                      "  Faça à mão: no campo id=\"suPassword\", troque minlength=\"6\" por minlength=\"8\".")
    return RE_SENHA.sub(lambda m: m.group(1) + 'minlength="8"', texto, count=1), "templates/cadastro_conta.html: o campo da senha agora exige 8 caracteres."


ALVOS = (("static/onboarding.js", ajustar_contador), ("templates/cadastro_conta.html", ajustar_senha))


def main():
    ap = argparse.ArgumentParser(description="Ajusta o contador do onboarding e o tamanho mínimo da senha.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    plano, problemas = [], 0
    for rel, funcao in ALVOS:
        arquivo = RAIZ / rel
        if not arquivo.exists():
            print(f"   {rel}: não existe.")
            problemas += 1
            continue
        texto, crlf = ler(arquivo)
        novo, msg = funcao(texto)
        print(("-> " if novo is not None else "   ") + msg)
        if novo is not None:
            plano.append((arquivo, novo, crlf))
        elif "nada a fazer" not in msg:
            problemas += 1
    if not plano:
        return 1 if problemas else 0
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_ajustes_onboarding.py --aplicar")
        return 0
    for arquivo, novo, crlf in plano:
        copia = arquivo.with_name(arquivo.name + ".bak")
        n = 1
        while copia.exists():
            n += 1
            copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
        shutil.copy2(arquivo, copia)
        arquivo.write_bytes(gravar_texto(novo, crlf))
        print(f"gravado: {arquivo.relative_to(RAIZ)}  (cópia do original: {copia.name})")
    print("\nPronto. Reinicie o servidor.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
