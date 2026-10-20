"""
NEOCORTEX - atualizar_cronometro_discreto.py

Deixa o cronômetro opcional mais DISCRETO na tela de Tarefas e dá a opção de desligá-lo:

  - só a PRÓXIMA tarefa (a que está valendo agora ou vem em seguida) mostra a pílula "▶ Começar"; as outras mostram só um ícone ▶;
  - com um cronômetro rodando, nenhuma tarefa mostra a pílula (a pessoa já está fazendo algo);
  - em Configurações, a linha "Cronômetro nas tarefas" liga e desliga os botões de começar (ligado por padrão). Desligar não atrapalha o
    que já está em andamento: dá para pausar e concluir normalmente.

DEPENDE do pacote "cronômetro opcional". Sem ele o script recusa e diz o que falta.
Mexe em app.py, templates/tarefas.html e templates/configuracoes.html. É TUDO OU NADA. Por padrão só MOSTRA o que mudaria.
Rode na pasta do projeto (a do app.py):

    python atualizar_cronometro_discreto.py            # só mostra
    python atualizar_cronometro_discreto.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ALVOS = (
    ('app.py', '[CRONOMETRO-DISCRETO]', (
        ('começar só na próxima tarefa, e a opção de desligar',
         r'''def _anexar_cronometro(tarefas):
    """[CRONOMETRO] Acrescenta a cada tarefa o estado do cronômetro opcional (só quem está em andamento precisa de consulta)
    e se vale oferecer 'Começar'. Nunca derruba a tela de Tarefas."""
    hoje = datetime.now().date()
    agora = None
    for t in tarefas:
        t["cronometro"] = None
        t["pode_comecar"] = t["status"] == "pendente" and t["data_inicio"].date() <= hoje
        if t["status"] == "em_andamento":
            try:
                agora = agora or servicos.hora_do_cronometro()
                estado = servicos.estado_do_cronometro(usuario_logado(), t["id_tarefa"], agora)
                t["cronometro"] = {**estado, "rotulo": cronometro.rotulo_tempo(estado["acumulado_s"])}
            except Exception:
                t["cronometro"] = None
    return tarefas''',
         r'''def _cronometro_ativo():
    """[CRONOMETRO-DISCRETO] Opcional: a pessoa pode desligar os botões 'Começar' em Configurações. Ligado por padrão."""
    try:
        return db.buscar_preferencia(usuario_logado(), "cronometro_ativo") != "false"
    except Exception:
        return True


def _anexar_cronometro(tarefas):
    """
    [CRONOMETRO] Acrescenta a cada tarefa o estado do cronômetro opcional (só quem está em andamento precisa de consulta),
    se vale oferecer 'Começar' e QUAL tarefa recebe o botão em destaque.
    [CRONOMETRO-DISCRETO] Para a tela não ficar poluída: só a PRÓXIMA tarefa (a que está valendo agora ou vem em seguida) ganha a
    pílula 'Começar'; as outras ganham só o ícone ▶; e com um cronômetro rodando ninguém ganha pílula. Quem desligou o cronômetro
    em Configurações não vê 'Começar' (o que já está em andamento continua podendo pausar e concluir).
    Nunca derruba a tela de Tarefas.
    """
    agora_local = datetime.now()
    hoje = agora_local.date()
    ativo = _cronometro_ativo()
    agora = None
    ha_rodando = False
    for t in tarefas:
        t["cronometro"] = None
        t["comecar_destaque"] = False
        t["pode_comecar"] = ativo and t["status"] == "pendente" and t["data_inicio"].date() <= hoje
        if t["status"] == "em_andamento":
            try:
                agora = agora or servicos.hora_do_cronometro()
                estado = servicos.estado_do_cronometro(usuario_logado(), t["id_tarefa"], agora)
                t["cronometro"] = {**estado, "rotulo": cronometro.rotulo_tempo(estado["acumulado_s"])}
                ha_rodando = ha_rodando or estado["estado"] == "rodando"
            except Exception:
                t["cronometro"] = None
    if not ha_rodando:
        proximas = [t for t in tarefas if t["pode_comecar"] and t.get("data_fim") and t["data_fim"] >= agora_local]
        if proximas:
            min(proximas, key=lambda t: t["data_inicio"])["comecar_destaque"] = True
    return tarefas'''),
        ('rota para ligar e desligar o cronômetro',
         r'''@app.route("/configuracoes/notificacoes", methods=["POST"])''',
         r'''@app.route("/configuracoes/cronometro", methods=["POST"])
@login_obrigatorio
def salvar_cronometro():
    """[CRONOMETRO-DISCRETO] Liga ou desliga os botões 'Começar' das tarefas. O que já está em andamento continua podendo pausar e concluir."""
    ativado = request.form.get("cronometro_ativo") == "on"
    db.salvar_preferencia(usuario_logado(), "cronometro_ativo", "true" if ativado else "false")
    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/notificacoes", methods=["POST"])'''),
        ('a tela de Configurações recebe a opção',
         r'''        notificacoes_ativas=notificacoes_ativas,
''',
         r'''        notificacoes_ativas=notificacoes_ativas,
        cronometro_ativo=_cronometro_ativo(),   # [CRONOMETRO-DISCRETO]
'''),
    )),
    ('templates/tarefas.html', '[CRONOMETRO-DISCRETO]', (
        ('pílula na próxima tarefa e ícone nas outras',
         r'''      {% elif t.pode_comecar %}
      <form method="POST" action="{{ url_for('cronometro_tarefa', id_tarefa=t.id_tarefa, acao='iniciar') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" title="Opcional: cronometre esta tarefa. Ajuda o NEOCORTEX a aprender o seu ritmo{{ ' e dá +5 pontos' if mascote_ativo else '' }}."
          style="height:28px;padding:0 10px;border-radius:14px;border:1.5px solid var(--nc-border);background:transparent;color:var(--nc-text);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;">▶ Começar</button>
      </form>
''',
         r'''      {% elif t.pode_comecar %}
      {# [CRONOMETRO-DISCRETO] só a próxima tarefa ganha a pílula; as outras, um ícone discreto #}
      {% if t.comecar_destaque %}
      <form method="POST" action="{{ url_for('cronometro_tarefa', id_tarefa=t.id_tarefa, acao='iniciar') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" title="Opcional: cronometre esta tarefa. Ajuda o NEOCORTEX a aprender o seu ritmo{{ ' e dá +5 pontos' if mascote_ativo else '' }}." aria-label="Começar a tarefa {{ t.titulo }} com o cronômetro"
          style="height:28px;padding:0 10px;border-radius:14px;border:1.5px solid var(--nc-border);background:transparent;color:var(--nc-text);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;">▶ Começar</button>
      </form>
      {% else %}
      <form method="POST" action="{{ url_for('cronometro_tarefa', id_tarefa=t.id_tarefa, acao='iniciar') }}" style="margin:0;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" title="Opcional: cronometre esta tarefa. Ajuda o NEOCORTEX a aprender o seu ritmo{{ ' e dá +5 pontos' if mascote_ativo else '' }}." aria-label="Começar a tarefa {{ t.titulo }} com o cronômetro"
          style="width:30px;height:30px;border-radius:50%;border:1.5px solid var(--nc-border);background:transparent;color:var(--nc-text2);font-size:11px;font-weight:700;cursor:pointer;line-height:1;padding:0;">▶</button>
      </form>
      {% endif %}
'''),
    )),
    ('templates/configuracoes.html', '[CRONOMETRO-DISCRETO]', (
        ("linha 'Cronômetro nas tarefas' em Configurações",
         r'''      <div style="height:1px;background:var(--nc-border);"></div>
      <div id="rowExcluirConta" class="settings-row-click"''',
         r'''      <div style="height:1px;background:var(--nc-border);"></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 0;">   {# [CRONOMETRO-DISCRETO] #}
        <div>
          <p style="margin:0;font-size:14px;font-weight:700;color:var(--nc-text);">Cronômetro nas tarefas</p>
          <p style="margin:0;font-size:11px;color:var(--nc-text2);">Opcional. Mostra o botão ▶ para cronometrar uma tarefa. Desligar só esconde os botões de começar.</p>
        </div>
        <form method="POST" action="{{ url_for('salvar_cronometro') }}" style="margin:0;">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="checkbox" name="cronometro_ativo" aria-label="Mostrar o cronômetro nas tarefas" {{ 'checked' if cronometro_ativo else '' }} onchange="this.form.submit()">
        </form>
      </div>
      <div style="height:1px;background:var(--nc-border);"></div>
      <div id="rowExcluirConta" class="settings-row-click"'''),
    ))
)

PRE_REQUISITOS = (
    ('app.py', 'def _anexar_cronometro(', "o pacote 'cronômetro opcional'"),
    ('templates/tarefas.html', '[CRONOMETRO]', "o pacote 'cronômetro opcional'"),
    ('templates/configuracoes.html', 'rowExcluirConta', 'o arquivo templates/configuracoes.html do projeto'),
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
    ap = argparse.ArgumentParser(description="Deixa o cronômetro mais discreto e opcional.")
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
        print("\nNada foi alterado. Para aplicar:  python atualizar_cronometro_discreto.py --aplicar")
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
