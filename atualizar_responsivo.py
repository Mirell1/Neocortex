"""
NEOCORTEX - atualizar_responsivo.py

Adapta o NEOCORTEX a CELULAR e TABLET sem mudar nada no computador.

O que muda no celular e no tablet (até 900 px de largura):
  - o menu lateral vira uma GAVETA: botão ☰ na barra superior; fecha ao tocar fora, com Esc ou ao escolher uma tela;
  - o Login mostra o formulário logo (antes ele ficava fora da tela);
  - as janelas (Nova tarefa, Editar, Objetivos, Rotina) cabem na tela e rolam por dentro;
  - Tarefas: a linha vira duas camadas e os botões ficam do tamanho de um dedo;
  - Agenda, Configurações, Início, Loja e Jornada: barra que quebra em linhas, textos de no mínimo 12 px e alvos de toque maiores;
  - o botão "+" fica preso ao canto da tela e o mascote ocupa menos espaço.
Junto, três caixas de Configurações (Alto contraste, Fonte para dislexia e Notificações) ganham NOME para leitor de tela.

No computador (900 px ou mais) tudo fica IDÊNTICO: as regras de tela pequena ficam dentro de @media.

Precisa de static/responsivo.css (vem neste pacote) e DEPENDE do pacote "cronômetro discreto". Sem eles o script recusa e diz o que falta.
Mexe em 5 templates. É TUDO OU NADA. Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_responsivo.py            # só mostra
    python atualizar_responsivo.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ALVOS = (
    ('templates/base_app_novo.html', '[RESPONSIVO]', (
        ('menu em gaveta: fundo escuro, id do menu e link do CSS responsivo',
         r'''</head>
<body>
  <div class="app-shell">
    <div class="app-sidebar">''',
         r'''  <link rel="stylesheet" href="{{ url_for('static', filename='responsivo.css') }}">   {# [RESPONSIVO] #}
</head>
<body>
  <div class="app-shell">
    <div class="app-menu-fundo" id="menuFundo" hidden></div>
    <div class="app-sidebar" id="menuLateral">'''),
        ('botão ☰ na barra superior',
         r'''      <div class="app-topbar">
        <h2>{{ titulo_pagina }}</h2>''',
         r'''      <div class="app-topbar">
        <div class="app-topbar-esq">
          <button type="button" class="app-menu-btn" id="btnMenu" aria-label="Abrir menu" aria-controls="menuLateral" aria-expanded="false">☰</button>
          <h2>{{ titulo_pagina }}</h2>
        </div>'''),
        ('script da gaveta',
         r'''  <div vw class="enabled">''',
         r'''  <script>
  /* [RESPONSIVO] menu em gaveta (celular e tablet): abre pelo botão ☰ e fecha ao tocar fora, com Esc ou ao escolher uma tela */
  (function () {
    var shell = document.querySelector('.app-shell'), btn = document.getElementById('btnMenu');
    var fundo = document.getElementById('menuFundo'), menu = document.getElementById('menuLateral');
    if (!shell || !btn || !fundo || !menu) return;
    function abrir(aberto) {
      shell.classList.toggle('menu-aberto', aberto); fundo.hidden = !aberto;
      btn.setAttribute('aria-expanded', aberto ? 'true' : 'false'); btn.setAttribute('aria-label', aberto ? 'Fechar menu' : 'Abrir menu');
      if (aberto) { var a = menu.querySelector('a'); if (a) a.focus(); } else { btn.focus(); }
    }
    btn.addEventListener('click', function () { abrir(!shell.classList.contains('menu-aberto')); });
    fundo.addEventListener('click', function () { abrir(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && shell.classList.contains('menu-aberto')) abrir(false); });
    menu.addEventListener('click', function (e) { if (e.target.closest('a')) abrir(false); });
    var largo = window.matchMedia('(min-width: 901px)');
    function aoMudar(m) { if (m.matches && shell.classList.contains('menu-aberto')) { shell.classList.remove('menu-aberto'); fundo.hidden = true; btn.setAttribute('aria-expanded', 'false'); btn.setAttribute('aria-label', 'Abrir menu'); } }
    if (largo.addEventListener) largo.addEventListener('change', aoMudar); else if (largo.addListener) largo.addListener(aoMudar);
  })();
  </script>

  <div vw class="enabled">'''),
    )),
    ('templates/login.html', '[RESPONSIVO]', (
        ('link do CSS responsivo',
         r'''</head>''',
         r'''  <link rel="stylesheet" href="{{ url_for('static', filename='responsivo.css') }}">   {# [RESPONSIVO] #}
</head>'''),
        ('classe no layout em duas colunas',
         r'''<div style="display:flex;height:100vh;">
  <div class="auth-left-panel">''',
         r'''<div class="auth-layout" style="display:flex;height:100vh;">
  <div class="auth-left-panel">'''),
        ('classe no lado do formulário',
         r'''  <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:40px;background:var(--nc-surface);">''',
         r'''  <div class="auth-direita" style="flex:1;display:flex;align-items:center;justify-content:center;padding:40px;background:var(--nc-surface);">'''),
    )),
    ('templates/tarefas.html', '[RESPONSIVO]', (
        ('classe na linha da tarefa',
         r'''    <div
      style="display:flex;align-items:center;gap:16px;padding:16px 24px;{{ 'border-bottom''',
         r'''    <div class="t-linha"
      style="display:flex;align-items:center;gap:16px;padding:16px 24px;{{ 'border-bottom'''),
        ('botão de concluir ganha nome para leitor de tela e classe',
         r'''        <button type="submit"
          style="width:20px;height:20px;border-radius:6px;''',
         r'''        <button type="submit" class="t-check" aria-label="{{ 'Desfazer conclusão de ' if t.status == 'concluida' else 'Concluir ' }}{{ t.titulo }}"
          style="width:20px;height:20px;border-radius:6px;'''),
        ('classe no título',
         r'''      <div style="flex:1;min-width:0;">
        <p
          style="margin:0 0 2px;font-size:14px;font-weight:600;color:var(--nc-text);{{ 'text-decoration:line-through''',
         r'''      <div class="t-titulo" style="flex:1;min-width:0;">
        <p
          style="margin:0 0 2px;font-size:14px;font-weight:600;color:var(--nc-text);{{ 'text-decoration:line-through'''),
        ('agrupa cronômetro, status e ações',
         r'''      {# [CRONOMETRO] opcional: começar, pausar e retomar.''',
         r'''      <div class="t-acoes">   {# [RESPONSIVO] agrupa os botões; no computador não gera caixa (display: contents) #}
      {# [CRONOMETRO] opcional: começar, pausar e retomar.'''),
        ('fecha o agrupamento',
         r'''          style="background:none;border:none;color:var(--nc-text2);font-size:15px;cursor:pointer;">✕</button>
      </form>
    </div>
    {% else %}''',
         r'''          style="background:none;border:none;color:var(--nc-text2);font-size:15px;cursor:pointer;">✕</button>
      </form>
      </div>
    </div>
    {% else %}'''),
    )),
    ('templates/calendario.html', 'cal-barra', (
        ('classe na barra da Agenda',
         r'''  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div id="calTabs"''',
         r'''  <div class="cal-barra" style="display:flex;justify-content:space-between;align-items:center;">
    <div id="calTabs"'''),
    )),
    ('templates/configuracoes.html', 'aria-label="Alto contraste"', (
        ('caixa de Alto contraste ganha nome para leitor de tela',
         r'''<input type="checkbox" name="acess_contraste" value="alto"''',
         r'''<input type="checkbox" name="acess_contraste" aria-label="Alto contraste" value="alto"'''),
        ('caixa de Fonte para dislexia ganha nome para leitor de tela',
         r'''<input type="checkbox" name="acess_tipografia" value="dislexia"''',
         r'''<input type="checkbox" name="acess_tipografia" aria-label="Fonte para dislexia (Lexend)" value="dislexia"'''),
        ('caixa de Notificações ganha nome para leitor de tela',
         r'''<input type="checkbox" name="notificacoes_ativas" {{''',
         r'''<input type="checkbox" name="notificacoes_ativas" aria-label="Receber notificações" {{'''),
    ))
)

PRE_REQUISITOS = (
    ('static/responsivo.css', '[RESPONSIVO]', 'o arquivo static/responsivo.css deste pacote (extraia o zip na pasta do projeto, a mesma do app.py)'),
    ('templates/tarefas.html', '[CRONOMETRO-DISCRETO]', "o pacote 'cronômetro discreto'"),
    ('templates/configuracoes.html', 'acess_contraste', 'o arquivo templates/configuracoes.html do projeto (com a seção de acessibilidade)'),
    ('templates/base_app_novo.html', 'app-sidebar', 'o arquivo templates/base_app_novo.html do projeto'),
    ('templates/login.html', 'auth-left-panel', 'o arquivo templates/login.html do projeto'),
    ('templates/calendario.html', 'calTabs', 'o arquivo templates/calendario.html do projeto'),
)


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def confere(rel, texto):
    """Python: compila. Template (.html): o Jinja precisa conseguir ler."""
    if rel.endswith(".py"):
        try:
            compile(texto, rel, "exec")
        except SyntaxError as e:
            return False, str(e)
    elif rel.endswith(".html"):
        try:
            import jinja2
            jinja2.Environment().parse(texto)
        except ImportError:
            pass
        except Exception as e:
            return False, str(e)[:200]
    return True, ""


def main():
    ap = argparse.ArgumentParser(description="Adapta o app a celular e tablet.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    faltam = [msg for arq, marca, msg in PRE_REQUISITOS if not (RAIZ / arq).exists() or marca not in ler(RAIZ / arq)[0]]
    if faltam:
        print("NADA FOI GRAVADO. Falta aplicar antes:")
        for f in sorted(set(faltam)):
            print("  - " + f)
        return 1
    plano, problemas = [], []
    for rel, marca, trocas in ALVOS:
        arquivo = RAIZ / rel
        if not arquivo.exists():
            problemas.append(f"{rel}: o arquivo não existe.")
            continue
        texto, crlf = ler(arquivo)
        if marca in texto and all(depois in texto for _, _, depois in trocas):
            print(f"   {rel}: já aplicado (nada a fazer).")
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
            problemas.append(f"{rel}: o arquivo novo não passou na conferência de sintaxe ({motivo})")
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
        print("\nNada foi alterado. Para aplicar:  python atualizar_responsivo.py --aplicar")
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
