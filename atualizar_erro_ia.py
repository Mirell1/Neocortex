"""
NEOCORTEX - atualizar_erro_ia.py

Quando a IA falha ao sugerir os passos de um objetivo, o app mostrava sempre "Não consegui falar com a IA agora" e NÃO
registrava nada no terminal: o erro verdadeiro (cota, sobrecarga, chave, modelo) ficava invisível.

Agora, na prévia dos passos:
  - o terminal registra o tipo do erro, o code, o status e a mensagem (a chave da IA é trocada por ***);
  - a janela diz o que fazer, conforme o erro:
      429 / RESOURCE_EXHAUSTED ... "A IA atingiu o limite de uso por enquanto. Espere cerca de um minuto e tente de novo."
      500, 502, 503, 504 / UNAVAILABLE ... "A IA está sobrecarregada agora. Tenta de novo em instantes."
      401, 403 / chave ........ "A IA não aceitou a chave de acesso. Avise quem cuida da configuração."
      404 / NOT_FOUND ......... "O modelo de IA configurado não foi encontrado. Avise quem cuida da configuração."
      qualquer outro .......... a mensagem de sempre.

Só mexe no app.py. Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_erro_ia.py            # só mostra
    python atualizar_erro_ia.py --aplicar  # grava (cópia .bak; confere a sintaxe antes)

Rodar de novo é seguro. Funciona com ou sem o pacote "gerar mais passos".
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()
MARCA = "[ERRO-IA]"

HELPER = '''def _mensagem_erro_ia(erro):
    """[ERRO-IA] Traduz o erro do Gemini numa mensagem que a pessoa consiga usar; o detalhe técnico vai para o terminal."""
    codigo = getattr(erro, "code", None)
    texto = (str(getattr(erro, "status", "") or "") + " " + str(erro)).upper()
    if codigo == 429 or "RESOURCE_EXHAUSTED" in texto:
        return "A IA atingiu o limite de uso por enquanto. Espere cerca de um minuto e tente de novo."
    if codigo in (500, 502, 503, 504) or "UNAVAILABLE" in texto:
        return "A IA está sobrecarregada agora. Tenta de novo em instantes."
    if codigo in (401, 403) or "API_KEY" in texto or "API KEY" in texto or "PERMISSION_DENIED" in texto:
        return "A IA não aceitou a chave de acesso. Avise quem cuida da configuração."
    if codigo == 404 or "NOT_FOUND" in texto:
        return "O modelo de IA configurado não foi encontrado. Avise quem cuida da configuração."
    return "Não consegui falar com a IA agora. Tenta de novo em instantes."


'''
ANTES_PREVIA = "def _previa_fragmentos(titulo_objetivo, prazo_date, existente=False"

TROCAS = (
    ("função que traduz o erro da IA em mensagem", ANTES_PREVIA, HELPER + ANTES_PREVIA),
    ("a prévia registra o erro real e mostra a mensagem certa",
     '''    except Exception:
        return jsonify(erro="Não consegui falar com a IA agora. Tenta de novo em instantes."), 503''',
     '''    except Exception as erro_ia:
        chave = os.getenv("GEMINI_API_KEY", "")   # [ERRO-IA] antes o erro real nunca aparecia no terminal
        detalhe = str(erro_ia).replace(chave, "***") if chave else str(erro_ia)
        app.logger.error("Falha ao pedir os passos à IA: %s (code=%s, status=%s): %s",
                         type(erro_ia).__name__, getattr(erro_ia, "code", None), getattr(erro_ia, "status", None), detalhe[:500])
        return jsonify(erro=_mensagem_erro_ia(erro_ia)), 503'''),
)


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def main():
    ap = argparse.ArgumentParser(description="Registra o erro real da IA e mostra mensagens úteis na prévia dos passos.")
    ap.add_argument("--aplicar", action="store_true", help="grava a mudança (sem isso, só mostra)")
    args = ap.parse_args()
    arquivo = RAIZ / "app.py"
    if not arquivo.exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    texto, crlf = ler(arquivo)
    if MARCA in texto and all(depois in texto for _, _, depois in TROCAS):
        print("   app.py: o erro da IA já é registrado e explicado (nada a fazer).")
        return 0
    faltam = [rotulo for rotulo, antes, _ in TROCAS if texto.count(antes) != 1]
    if faltam:
        print("NADA FOI GRAVADO. NÃO reconheci no app.py: " + "; ".join(faltam) + ".")
        print("  Me mande o app.py que eu ajusto.")
        return 1
    novo = texto
    for _, antes, depois in TROCAS:
        novo = novo.replace(antes, depois, 1)
    try:
        compile(novo, "app.py", "exec")
    except SyntaxError as e:
        print(f"ERRO: o app.py novo não passou na conferência de sintaxe ({e}). Nada foi gravado.")
        return 1
    print(f"-> app.py: {len(TROCAS)} ajuste(s)")
    for rotulo, _, _ in TROCAS:
        print(f"     - {rotulo}")
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_erro_ia.py --aplicar")
        return 0
    copia = arquivo.with_name(arquivo.name + ".bak")
    n = 1
    while copia.exists():
        n += 1
        copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
    shutil.copy2(arquivo, copia)
    arquivo.write_bytes((novo.replace("\n", "\r\n") if crlf else novo).encode("utf-8"))
    print(f"\ngravado: app.py  (cópia do original: {copia.name})\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
