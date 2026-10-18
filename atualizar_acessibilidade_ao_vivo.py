"""
NEOCORTEX - atualizar_acessibilidade_ao_vivo.py

Liga o módulo static/onboarding_acessibilidade.js à página do onboarding (templates/onboarding.html): acrescenta a linha que o
carrega, logo depois do onboarding_objetivo.js (ou, se ele não existir, depois do onboarding.js).

Com isso, a preferência escolhida na pergunta de acessibilidade (fonte maior, alto contraste ou fonte para dislexia) passa a valer
NA HORA, durante o cadastro, e não só depois dele.

Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_acessibilidade_ao_vivo.py            # só mostra
    python atualizar_acessibilidade_ao_vivo.py --aplicar  # grava (cópia .bak; confere a sintaxe antes)

Rodar de novo é seguro. Se não reconhecer o trecho, NÃO mexe no arquivo e explica como fazer à mão.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()
LINHA = "<script src=\"{{ url_for('static', filename='onboarding_acessibilidade.js') }}\"></script>"
APOS_OBJETIVO = re.compile(r"([ \t]*)(<script src=\"\{\{ url_for\('static', filename='onboarding_objetivo\.js'\) \}\}\"></script>)")
APOS_ONBOARDING = re.compile(r"([ \t]*)(<script src=\"\{\{ url_for\('static', filename='onboarding\.js'\) \}\}\"></script>)")


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def jinja_confere(texto):
    try:
        import jinja2
        jinja2.Environment().parse(texto)
        return True, ""
    except ImportError:
        return True, ""
    except Exception as e:
        return False, str(e)[:300]


def preparar(texto):
    if "onboarding_acessibilidade.js" in texto:
        return None, "onboarding.html: já carrega o módulo de acessibilidade (nada a fazer)."
    for padrao in (APOS_OBJETIVO, APOS_ONBOARDING):
        achados = padrao.findall(texto)
        if len(achados) == 1:
            novo = padrao.sub(lambda m: m.group(1) + m.group(2) + "\n" + m.group(1) + LINHA, texto, count=1)
            return novo, "onboarding.html: carrega o módulo de acessibilidade ao vivo."
    return None, ("onboarding.html: NÃO achei a linha que carrega o onboarding.js nem o onboarding_objetivo.js.\n"
                  "  Faça à mão: depois delas, acrescente  " + LINHA)


def main():
    ap = argparse.ArgumentParser(description="Liga a acessibilidade ao vivo ao onboarding.")
    ap.add_argument("--aplicar", action="store_true", help="grava a mudança (sem isso, só mostra)")
    args = ap.parse_args()
    arquivo = RAIZ / "templates" / "onboarding.html"
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    if not (RAIZ / "static" / "onboarding_acessibilidade.js").exists():
        print("ATENÇÃO: não achei static/onboarding_acessibilidade.js. Copie esse arquivo do pacote para a pasta static/.\n")
    if not arquivo.exists():
        print("templates/onboarding.html não existe.")
        return 1
    texto, crlf = ler(arquivo)
    novo, msg = preparar(texto)
    print(("-> " if novo is not None else "   ") + msg)
    if novo is None:
        return 0 if "nada a fazer" in msg else 1
    ok, erro = jinja_confere(novo)
    if not ok:
        print(f"   ERRO: o arquivo novo não passou na conferência de sintaxe ({erro}). Nada foi gravado.")
        return 1
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_acessibilidade_ao_vivo.py --aplicar")
        return 0
    copia = arquivo.with_name(arquivo.name + ".bak")
    n = 1
    while copia.exists():
        n += 1
        copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
    shutil.copy2(arquivo, copia)
    arquivo.write_bytes(gravar_texto(novo, crlf))
    print(f"\ngravado: templates/onboarding.html  (cópia do original: {copia.name})\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
