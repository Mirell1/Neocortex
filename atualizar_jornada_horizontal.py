"""
NEOCORTEX - atualizar_jornada_horizontal.py

Atualiza a rota /jornada do app.py para a TRILHA HORIZONTAL (a Etapa 7, agora com o anel de progresso que preenche):

  - sem gamificação ligada, a página volta para o Início (não há níveis nem mascote para mostrar);
  - cada nível passa a levar a lista dos acessórios que libera ("+ Óculos", "+ Gorro"...), do mascote em uso;
  - some a conta das coordenadas do desenho em zigue-zague (x, y e altura do SVG), que o desenho novo não usa.

O desenho em si está em templates/jornada.html, que vem no zip: este script só cuida do app.py.

Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_jornada_horizontal.py            # só mostra
    python atualizar_jornada_horizontal.py --aplicar  # grava (cópia .bak; confere a sintaxe antes)

Rodar de novo é seguro. Se não reconhecer o trecho, NÃO mexe no arquivo e diz como fazer à mão.
"""
import argparse
import difflib
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ROTA_ANTIGA = '''@app.route("/jornada")
@login_obrigatorio
def jornada():
    pontos = db.calcular_pontos_mascote(usuario_logado())
    nivel_atual = nivel_mascote(pontos)
    nos = []
    for i, n in enumerate(NIVEIS_MASCOTE):
        if n["nivel"] == nivel_atual["nivel"]:
            status = "atual"
        elif pontos >= n["pontos_min"]:
            status = "concluido"
        else:
            status = "bloqueado"
        nos.append({
            **n,
            "x": 150 if i % 2 == 0 else 346,
            "y": 70 + i * 170,
            "status": status,
        })
    altura_svg = 70 + len(NIVEIS_MASCOTE) * 170
    return render_template("jornada.html", nos=nos, altura_svg=altura_svg, **_pagina("jornada", "Jornada"))
'''

ROTA_NOVA = '''@app.route("/jornada")
@login_obrigatorio
def jornada():
    if not GAMIFICACAO_ATIVA:   # sem gamificação não há níveis nem mascote: volta ao Início
        return redirect(url_for("dashboard"))
    pontos = db.calcular_pontos_mascote(usuario_logado())
    nivel_atual = nivel_mascote(pontos)
    catalogo = acessorios_do_mascote(_skin_atual(usuario_logado()))   # [ACESSÓRIOS] os itens variam por mascote
    nos = []
    for i, n in enumerate(NIVEIS_MASCOTE):
        if n["nivel"] == nivel_atual["nivel"]:
            status = "atual"
        elif pontos >= n["pontos_min"]:
            status = "concluido"
        else:
            status = "bloqueado"
        proximo_min = NIVEIS_MASCOTE[i + 1]["pontos_min"] if i + 1 < len(NIVEIS_MASCOTE) else float("inf")
        # acessórios liberados ENTRE este nível e o próximo (nomes reais, do mascote em uso)
        itens = [a["nome"] for a in catalogo if n["pontos_min"] <= a["pontos_min"] < proximo_min]
        nos.append({**n, "status": status, "itens": itens})
    return render_template("jornada.html", nos=nos, **_pagina("jornada", "Jornada"))
'''

EXIGE = ("def acessorios_do_mascote(", "def _skin_atual(", "GAMIFICACAO_ATIVA")


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def preparar(texto):
    if ROTA_NOVA in texto:
        return None, "app.py: a rota /jornada já é a da trilha horizontal (nada a fazer)."
    faltam = [x for x in EXIGE if x not in texto]
    if faltam:
        return None, ("app.py: faltam peças que a rota nova usa: " + ", ".join(f.replace("def ", "").rstrip("(") for f in faltam) + ".\n"
                      "  São das etapas dos acessórios e da gamificação. O arquivo ficou como estava. Me mande o app.py e eu ajusto.")
    if texto.count(ROTA_ANTIGA) != 1:
        return None, ("app.py: NÃO reconheci a rota /jornada (ela já foi alterada à mão?). O arquivo ficou como estava.\n"
                      "  Faça à mão, dentro de def jornada():\n"
                      "    1) no começo:  if not GAMIFICACAO_ATIVA: return redirect(url_for(\"dashboard\"))\n"
                      "    2) antes do for:  catalogo = acessorios_do_mascote(_skin_atual(usuario_logado()))\n"
                      "    3) no lugar de \"x\", \"y\" e altura_svg:  itens = [a[\"nome\"] for a in catalogo if n[\"pontos_min\"] <= a[\"pontos_min\"] < proximo_min]\n"
                      "       (veja o trecho completo neste script, em ROTA_NOVA) e render_template(\"jornada.html\", nos=nos, **_pagina(...)).")
    return texto.replace(ROTA_ANTIGA, ROTA_NOVA, 1), "app.py: a rota /jornada agora alimenta a trilha horizontal."


def main():
    ap = argparse.ArgumentParser(description="Atualiza a rota /jornada para a trilha horizontal.")
    ap.add_argument("--aplicar", action="store_true", help="grava a mudança (sem isso, só mostra)")
    args = ap.parse_args()
    arquivo = RAIZ / "app.py"
    if not arquivo.exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    modelo = RAIZ / "templates" / "jornada.html"
    if modelo.exists() and "altura_svg" in modelo.read_text(encoding="utf-8", errors="replace"):
        print("ATENÇÃO: templates/jornada.html ainda é o desenho antigo (zigue-zague). Extraia o zip do pacote por cima, para trazer o novo.\n")
    texto, crlf = ler(arquivo)
    novo, msg = preparar(texto)
    print(("-> " if novo is not None else "   ") + msg)
    if novo is None:
        return 0 if "nada a fazer" in msg else 1
    try:
        compile(novo, "app.py", "exec")
    except SyntaxError as e:
        print(f"   ERRO: o app.py novo não passou na conferência de sintaxe ({e}). Nada foi gravado.")
        return 1
    linhas = list(difflib.unified_diff(texto.splitlines(), novo.splitlines(), "app.py (atual)", "app.py (novo)", lineterm="", n=0))
    print("\n".join(linhas[:40]) + (f"\n   ... (diff cortado: {len(linhas)} linhas)" if len(linhas) > 40 else ""))
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_jornada_horizontal.py --aplicar")
        return 0
    copia = arquivo.with_name(arquivo.name + ".bak")
    n = 1
    while copia.exists():
        n += 1
        copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
    shutil.copy2(arquivo, copia)
    arquivo.write_bytes(gravar_texto(novo, crlf))
    print(f"\ngravado: app.py  (cópia do original: {copia.name})\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
