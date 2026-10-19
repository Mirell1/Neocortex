"""
NEOCORTEX - atualizar_gerar_mais_passos.py

Quando um objetivo JÁ TEM passos, "Fragmentar automaticamente" agora CONTINUA de onde parou, em vez de empilhar um plano repetido:

  Antes: a IA recebia só o título do objetivo e gerava de novo os mesmos 12 passos; o planejador caía nas mesmas datas
         (os passos novos iam para 12:30 porque 12:00 já estava ocupado) e o resultado era uma lista cheia de pares quase iguais.
  Agora:
    - a IA recebe os títulos que JÁ existem, com a instrução de não repetir e de seguir a progressão depois do último;
    - o planejador começa DEPOIS da data do último passo existente (sem prazo: uma semana depois dele), e a quantidade
      de passos novos considera só o tempo que sobra até o prazo;
    - uma rede de segurança descarta qualquer título novo quase igual a um que já existe;
    - se os passos existentes já chegam ao prazo, a janela explica e sugere aumentar o prazo;
    - na tela, o botão vira "Gerar mais passos" e a janela avisa "este objetivo já tem N passos" (passos cancelados não contam);
    - objetivo SEM passos: nada muda.

Mexe em app.py, ai.py e templates/objetivos.html. É TUDO OU NADA: se qualquer trecho não for reconhecido, nada é gravado.
Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_gerar_mais_passos.py            # só mostra
    python atualizar_gerar_mais_passos.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro. Pré-requisito: o pacote de conflito e reagendamento NÃO é necessário, mas o da prévia editável sim.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

# ----------------------------------------------------------------------------------------------------------------------
# app.py
# ----------------------------------------------------------------------------------------------------------------------
PREVIA_ANTIGA = '''def _previa_fragmentos(titulo_objetivo, prazo_date, existente=False):
    """Prévia dos passos (compartilhada pelo objetivo novo e pelo existente). Nada é gravado aqui."""
    if prazo_date and prazo_date < date.today():
        return jsonify(erro=("O prazo deste objetivo já passou. Edite o objetivo e escolha uma nova data para dividir em passos." if existente
                             else "O prazo já passou. Escolha uma data de hoje em diante.")), 400
    foco = request.form.get("foco", "geral")
    ritmo = request.form.get("ritmo", "moderado")
    duracao_min = 60 if ritmo == "longo_espacado" else 30
    quantidade = calcular_quantidade_fragmentos(prazo_date)

    try:
        titulos = ai.gerar_titulos_fragmentos(titulo_objetivo, prazo_date, foco, ritmo, quantidade)
    except Exception:
        return jsonify(erro="Não consegui falar com a IA agora. Tenta de novo em instantes."), 503
    if not titulos:
        return jsonify(erro="A IA não conseguiu gerar os fragmentos. Tenta de novo."), 502

    propostas, aviso = _planejar_fragmentos(usuario_logado(), titulos, prazo_date, duracao_min, ritmo)
    if not propostas:
        return jsonify(erro=aviso), 409
    return jsonify(propostas=propostas, aviso=aviso)'''

PREVIA_NOVA = '''def _normalizar_titulo(texto):
    """Minúsculas, sem acento e sem pontuação: para comparar títulos de passos."""
    import re
    import unicodedata
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", str(texto).lower()) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sem_acento).split())


def _sem_repeticao(novos, existentes, limite=0.8):
    """[GERAR-MAIS] Tira dos títulos novos os que repetem (ou quase) um passo que já existe. A IA já é instruída a não repetir; isto é a rede de segurança."""
    import difflib
    base = [_normalizar_titulo(t) for t in existentes]
    mantidos = []
    for t in novos:
        n = _normalizar_titulo(t)
        palavras = set(n.split())
        repetido = False
        for b in base:
            parecidas = len(palavras & set(b.split())) / max(1, len(palavras | set(b.split())))
            if n == b or difflib.SequenceMatcher(None, n, b).ratio() >= limite or parecidas >= limite:
                repetido = True
                break
        if not repetido:
            mantidos.append(t)
    return mantidos


def _previa_fragmentos(titulo_objetivo, prazo_date, existente=False, ja_existentes=None):
    """Prévia dos passos (compartilhada pelo objetivo novo e pelo existente). Nada é gravado aqui.
    [GERAR-MAIS] Com passos já existentes, continua DEPOIS do último, sem repetir os títulos que já existem."""
    if prazo_date and prazo_date < date.today():
        return jsonify(erro=("O prazo deste objetivo já passou. Edite o objetivo e escolha uma nova data para dividir em passos." if existente
                             else "O prazo já passou. Escolha uma data de hoje em diante.")), 400
    foco = request.form.get("foco", "geral")
    ritmo = request.form.get("ritmo", "moderado")
    duracao_min = 60 if ritmo == "longo_espacado" else 30
    ativos = [f for f in (ja_existentes or []) if f.get("status") != "cancelada"]
    titulos_existentes = [f["titulo"] for f in ativos]
    datas = [f["data_inicio"].date() if hasattr(f["data_inicio"], "date") else f["data_inicio"] for f in ativos if f.get("data_inicio")]
    a_partir_de = max(datas) if datas else None
    quantidade = calcular_quantidade_fragmentos(prazo_date, hoje=max(date.today(), a_partir_de) if a_partir_de else None)

    try:
        pedido_extra = {"existentes": titulos_existentes[-30:]} if titulos_existentes else {}
        titulos = ai.gerar_titulos_fragmentos(titulo_objetivo, prazo_date, foco, ritmo, quantidade, **pedido_extra)
    except Exception:
        return jsonify(erro="Não consegui falar com a IA agora. Tenta de novo em instantes."), 503
    if not titulos:
        return jsonify(erro="A IA não conseguiu gerar os fragmentos. Tenta de novo."), 502
    if titulos_existentes:
        titulos = _sem_repeticao(titulos, titulos_existentes)
        if not titulos:
            return jsonify(erro="A IA só repetiu passos que você já tem. Tente outro foco ou ritmo."), 409

    propostas, aviso = _planejar_fragmentos(usuario_logado(), titulos, prazo_date, duracao_min, ritmo, a_partir_de=a_partir_de)
    if not propostas:
        return jsonify(erro=aviso), 409
    return jsonify(propostas=propostas, aviso=aviso)'''

ROTA_ANTIGA = '''    prazo = objetivo["prazo"]
    prazo_date = prazo.date() if hasattr(prazo, "date") else prazo
    if prazo_date:
        return _previa_fragmentos(objetivo["titulo"], prazo_date, existente=True)
    try:
        prazo_date = _prazo_date(request.form.get("prazo"))      # vazio -> None (sem prazo: 4 passos, uma semana entre eles)
    except ValueError:
        return jsonify(erro="Prazo inválido. Escolha uma data de hoje em diante."), 400
    return _previa_fragmentos(objetivo["titulo"], prazo_date)'''
ROTA_NOVA = '''    prazo = objetivo["prazo"]
    prazo_date = prazo.date() if hasattr(prazo, "date") else prazo
    ja_existentes = db.listar_fragmentos_objetivo(id_objetivo, usuario_logado())   # [GERAR-MAIS]
    if prazo_date:
        return _previa_fragmentos(objetivo["titulo"], prazo_date, existente=True, ja_existentes=ja_existentes)
    try:
        prazo_date = _prazo_date(request.form.get("prazo"))      # vazio -> None (sem prazo: 4 passos, uma semana entre eles)
    except ValueError:
        return jsonify(erro="Prazo inválido. Escolha uma data de hoje em diante."), 400
    return _previa_fragmentos(objetivo["titulo"], prazo_date, ja_existentes=ja_existentes)'''

APP = (
    ("planejador: parâmetro a_partir_de",
     "def _planejar_fragmentos(id_usuario, titulos, prazo, duracao_min, ritmo, hoje=None):",
     "def _planejar_fragmentos(id_usuario, titulos, prazo, duracao_min, ritmo, hoje=None, a_partir_de=None):"),
    ("planejador: começa depois do último passo que já existe (com prazo)",
     '''    total = len(titulos)
    if prazo:
        inicio_janela = hoje if prazo <= hoje else hoje + timedelta(days=1)''',
     '''    total = len(titulos)
    if prazo and a_partir_de and prazo <= a_partir_de:   # [GERAR-MAIS] os passos que já existem chegam ao prazo
        return [], "Os passos que você já tem chegam até o prazo; não sobrou dia livre depois deles. Edite o objetivo para um prazo maior."
    base = max(hoje, a_partir_de) if a_partir_de else hoje   # [GERAR-MAIS] continua DEPOIS do último passo que já existe
    if prazo:
        inicio_janela = base if prazo <= base else base + timedelta(days=1)'''),
    ("planejador: começa depois do último passo que já existe (sem prazo)",
     "        dias = [hoje + timedelta(days=i) for i in range(1, 7 * total + 8)]",
     "        dias = [base + timedelta(days=i) for i in range(1, 7 * total + 8)]"),
    ("prévia: IA recebe os passos existentes, descarte de repetidos e planejador a partir do último", PREVIA_ANTIGA, PREVIA_NOVA),
    ("rota da prévia: lê os passos que o objetivo já tem", ROTA_ANTIGA, ROTA_NOVA),
)

# ----------------------------------------------------------------------------------------------------------------------
# ai.py
# ----------------------------------------------------------------------------------------------------------------------
AI_ANTIGA = '''def gerar_titulos_fragmentos(titulo_objetivo, prazo, foco, ritmo, quantidade):
    """
    Única chamada ao Gemini por fragmentação: só os TÍTULOS, sem data/hora —
    isso é responsabilidade do decisao.py (determinístico).
    """
    prazo_texto = prazo.isoformat() if prazo else "sem prazo definido"
    prompt = (
        f'Objetivo do usuário: "{titulo_objetivo}"\\n'
        f"Prazo: {prazo_texto}\\n"
        f"Foco principal escolhido: {foco}\\n"
        f"Ritmo preferido: {ritmo}\\n\\n"
        f"Divida esse objetivo em exatamente {quantidade} passos concretos, em ordem lógica de progressão "
        f"(do mais básico ao mais avançado). Cada passo é uma ação específica, nunca uma categoria vaga.\\n\\n"
        f"Responda SOMENTE com um JSON: uma lista de {quantidade} strings, cada uma um título curto "
        f"(máximo 60 caracteres), sem numeração, sem texto além do JSON."
    )'''
AI_NOVA = '''def gerar_titulos_fragmentos(titulo_objetivo, prazo, foco, ritmo, quantidade, existentes=None):
    """
    Única chamada ao Gemini por fragmentação: só os TÍTULOS, sem data/hora —
    isso é responsabilidade do decisao.py (determinístico).
    [GERAR-MAIS] Com 'existentes' (títulos dos passos que o objetivo já tem), pede passos NOVOS que continuam a progressão.
    """
    prazo_texto = prazo.isoformat() if prazo else "sem prazo definido"
    ja_existem = ""
    if existentes:
        ja_existem = ("Passos que JÁ existem neste objetivo (NÃO repita, não reescreva e não parafraseie nenhum deles):\\n"
                      + "\\n".join(f"- {str(t)[:60]}" for t in existentes) + "\\n\\n")
        pedido = (f"Crie exatamente {quantidade} passos NOVOS e concretos que CONTINUAM a progressão depois do último passo "
                  f"que já existe (ainda mais avançados). Cada passo é uma ação específica, nunca uma categoria vaga.\\n\\n")
    else:
        pedido = (f"Divida esse objetivo em exatamente {quantidade} passos concretos, em ordem lógica de progressão "
                  f"(do mais básico ao mais avançado). Cada passo é uma ação específica, nunca uma categoria vaga.\\n\\n")
    prompt = (
        f'Objetivo do usuário: "{titulo_objetivo}"\\n'
        f"Prazo: {prazo_texto}\\n"
        f"Foco principal escolhido: {foco}\\n"
        f"Ritmo preferido: {ritmo}\\n\\n"
        + ja_existem + pedido +
        f"Responda SOMENTE com um JSON: uma lista de {quantidade} strings, cada uma um título curto "
        f"(máximo 60 caracteres), sem numeração, sem texto além do JSON."
    )'''
AI = (("IA: pedir passos NOVOS que continuam os existentes", AI_ANTIGA, AI_NOVA),)

# ----------------------------------------------------------------------------------------------------------------------
# templates/objetivos.html
# ----------------------------------------------------------------------------------------------------------------------
HTML = (
    ("botão do card: 'Gerar mais passos' quando já há passos",
     '''onclick='abrirFragmentacaoAutomatica({{ o.id_objetivo }}, {{ o.titulo|tojson }}, {{ (o.prazo is not none)|tojson }})' style="width:100%;height:40px;margin-bottom:14px;">✨ Fragmentar automaticamente</button>''',
     '''onclick='abrirFragmentacaoAutomatica({{ o.id_objetivo }}, {{ o.titulo|tojson }}, {{ (o.prazo is not none)|tojson }}, {{ ativos|length }})' style="width:100%;height:40px;margin-bottom:14px;">{% if ativos %}✨ Gerar mais passos{% else %}✨ Fragmentar automaticamente{% endif %}</button>'''),
    ("botão do card: lista dos passos que contam (sem os cancelados)",
     '''<button type="button" class="btn-outline" onclick='abrirFragmentacaoAutomatica(''',
     '''{% set ativos = fragmentos | rejectattr('status', 'equalto', 'cancelada') | list %}   {# [GERAR-MAIS] #}
          <button type="button" class="btn-outline" onclick='abrirFragmentacaoAutomatica('''),
    ("janela de perguntas: aviso de que o objetivo já tem passos",
     '''<h3 style="margin:0 0 18px;font-size:18px;font-weight:800;color:var(--nc-text);">Duas perguntas rápidas</h3>''',
     '''<h3 style="margin:0 0 18px;font-size:18px;font-weight:800;color:var(--nc-text);">Duas perguntas rápidas</h3>
  <p id="fragAutoJaTem" class="hidden" role="status" style="margin:-6px 0 16px;font-size:13px;line-height:1.5;font-weight:600;color:var(--nc-text2);"></p>'''),
    ("abrir a janela de um objetivo existente: mostra quantos passos já tem",
     '''  function abrirFragmentacaoAutomatica(idObjetivo, titulo, temPrazo) {
    fragAutoContexto = { tipo: 'existente', idObjetivo };''',
     '''  function abrirFragmentacaoAutomatica(idObjetivo, titulo, temPrazo, jaTem) {
    fragAutoContexto = { tipo: 'existente', idObjetivo };
    const avisoJaTem = document.getElementById('fragAutoJaTem');   // [GERAR-MAIS]
    avisoJaTem.textContent = jaTem > 0 ? 'Este objetivo já tem ' + jaTem + (jaTem === 1 ? ' passo' : ' passos') + '. Vamos acrescentar mais, sem repetir os que já existem.' : '';
    avisoJaTem.classList.toggle('hidden', !(jaTem > 0));'''),
    ("abrir a janela de um objetivo novo: esconde o aviso",
     '''    fragAutoContexto = { tipo: 'novo', titulo, prazo };''',
     '''    fragAutoContexto = { tipo: 'novo', titulo, prazo };
    document.getElementById('fragAutoJaTem').classList.add('hidden');   // [GERAR-MAIS] objetivo novo: ainda não tem passos'''),
)

ALVOS = (
    ("app.py", APP, "[GERAR-MAIS]"),
    ("ai.py", AI, "[GERAR-MAIS]"),
    ("templates/objetivos.html", HTML, "[GERAR-MAIS]"),
)


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def confere(rel, texto):
    if rel.endswith(".py"):
        try:
            compile(texto, rel, "exec")
        except SyntaxError as e:
            return False, f"erro de sintaxe: {e}"
    elif rel.endswith(".html"):
        try:
            import jinja2
            jinja2.Environment().parse(texto)
        except ImportError:
            pass
        except Exception as e:
            return False, f"erro de sintaxe do template: {str(e)[:200]}"
    return True, ""


def main():
    ap = argparse.ArgumentParser(description="Faz 'Fragmentar automaticamente' continuar de onde parou quando o objetivo já tem passos.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    plano, problemas = [], []
    for rel, trocas, marca in ALVOS:
        arquivo = RAIZ / rel
        if not arquivo.exists():
            problemas.append(f"{rel}: o arquivo não existe.")
            continue
        texto, crlf = ler(arquivo)
        if marca in texto and all(depois in texto for _, _, depois in trocas):
            print(f"   {rel}: já corrigido (nada a fazer).")
            continue
        faltam = [rotulo for rotulo, antes, _ in trocas if texto.count(antes) != 1]
        if faltam:
            problemas.append(f"{rel}: NÃO reconheci: " + "; ".join(faltam))
            continue
        novo = texto
        for _, antes, depois in trocas:
            novo = novo.replace(antes, depois, 1)
        ok, motivo = confere(rel, novo)
        if not ok:
            problemas.append(f"{rel}: {motivo}")
            continue
        print(f"-> {rel}: {len(trocas)} ajuste(s)")
        for rotulo, _, _ in trocas:
            print(f"     - {rotulo}")
        plano.append((arquivo, novo, crlf))
    if problemas:
        print("\nNADA FOI GRAVADO (é tudo ou nada). Motivo:")
        for p in problemas:
            print("  " + p)
        print("  Me mande o arquivo citado que eu ajusto.")
        return 1
    if not plano:
        return 0
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_gerar_mais_passos.py --aplicar")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
