"""
NEOCORTEX - atualizar_calendario_mes.py

Conserta a visão MENSAL da Agenda (templates/calendario.html), que ficava torta com títulos longos:

  Problema: as 7 colunas do mês eram escritas como repeat(7,1fr), e uma coluna "1fr" não encolhe abaixo do conteúdo que não quebra.
  Com um título longo (por exemplo o de um passo de objetivo), a coluna do dia crescia até a largura do título (500px ou mais)
  e as outras seis ficavam espremidas (45 a 76px). A reticência "..." nunca aparecia, porque a coluna esticava para caber o texto.

  Agora:
    - as 7 colunas ficam SEMPRE iguais (repeat(7,minmax(0,1fr)), a mesma forma que a Semana e o Dia já usam no common.css);
    - o título longo é cortado com "..." numa linha só;
    - o título COMPLETO aparece ao passar o mouse (atributo title), e o "+N" lista os títulos que ficaram de fora;
    - clicar no dia continua abrindo o dia com os títulos completos.

Só mexe em templates/calendario.html. Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_calendario_mes.py            # só mostra
    python atualizar_calendario_mes.py --aplicar  # grava (cópia .bak; confere a sintaxe do template antes)

Rodar de novo é seguro. Se não reconhecer algum trecho, NÃO mexe no arquivo (nada fica pela metade) e explica.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

TROCAS = (
    # (rótulo, antes, depois)
    ("cabeçalho dos dias da semana",
     'id="calWeekdays" style="display:grid;grid-template-columns:repeat(7,1fr);',
     'id="calWeekdays" style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));'),
    ("grade dos dias do mês",
     'id="calGrid" style="display:grid;grid-template-columns:repeat(7,1fr);',
     'id="calGrid" style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));'),
    ("etiqueta de cada tarefa (título completo ao passar o mouse)",
     "return '<div style=\"padding:2px 6px;border-radius:4px;background:'",
     "return '<div title=\"' + escapeHtml(it.label) + '\" style=\"padding:2px 6px;border-radius:4px;background:'"),
    ("contador \"+N\" (lista os títulos que ficaram de fora)",
     "evHtml += '<span style=\"font-size:10px;font-weight:600;color:var(--nc-text2);padding-left:6px;\">+'",
     "evHtml += '<span title=\"' + escapeHtml(items.slice(2).map(function (x) { return x.label; }).join('\\n')) + '\" style=\"font-size:10px;font-weight:600;color:var(--nc-text2);padding-left:6px;\">+'"),
    ("comentário de apoio",
     "      let evHtml = items.slice(0, 2).map(function (it) {",
     "      // [CALENDÁRIO-MÊS] uma linha com \"...\" na etiqueta; o título completo fica no title (passar o mouse) e ao abrir o dia\n      let evHtml = items.slice(0, 2).map(function (it) {"),
)
MARCA = "[CALENDÁRIO-MÊS]"


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
    if MARCA in texto and "repeat(7,1fr)" not in texto:
        return None, "calendario.html: a visão mensal já está corrigida (nada a fazer)."
    faltam = [rotulo for rotulo, antes, _ in TROCAS if texto.count(antes) != 1]
    if faltam:
        return None, ("calendario.html: NÃO reconheci estes trechos: " + "; ".join(faltam) + ".\n"
                      "  O arquivo ficou como estava (nada pela metade). Faça à mão o essencial: nas duas linhas que têm\n"
                      "  grid-template-columns:repeat(7,1fr) (id=\"calWeekdays\" e id=\"calGrid\"), troque por repeat(7,minmax(0,1fr)).")
    novo = texto
    for _, antes, depois in TROCAS:
        novo = novo.replace(antes, depois, 1)
    return novo, "calendario.html: a visão mensal agora tem 7 colunas iguais e corta o título longo com \"...\"."


def main():
    ap = argparse.ArgumentParser(description="Conserta a visão mensal da Agenda com títulos longos.")
    ap.add_argument("--aplicar", action="store_true", help="grava a mudança (sem isso, só mostra)")
    args = ap.parse_args()
    arquivo = RAIZ / "templates" / "calendario.html"
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    if not arquivo.exists():
        print("templates/calendario.html não existe.")
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
    for rotulo, _, _ in TROCAS[:4]:
        print(f"   - {rotulo}")
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_calendario_mes.py --aplicar")
        return 0
    copia = arquivo.with_name(arquivo.name + ".bak")
    n = 1
    while copia.exists():
        n += 1
        copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
    shutil.copy2(arquivo, copia)
    arquivo.write_bytes(gravar_texto(novo, crlf))
    print(f"\ngravado: templates/calendario.html  (cópia do original: {copia.name})\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
