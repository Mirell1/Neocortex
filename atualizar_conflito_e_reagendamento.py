"""
NEOCORTEX - atualizar_conflito_e_reagendamento.py

Dois defeitos do relatório de avaliação (itens 02 e 47), corrigidos juntos:

  ITEM 02 - "Reagendar diz 'Tarefa não encontrada'" (db.py)
    db.atualizar_tarefa devolvia cur.rowcount, que é o resultado do ÚLTIMO comando executado, e não do UPDATE da tarefa.
    Ao ADIAR uma tarefa (ou cancelá-la), ela ainda registra o evento e depois resolve as recomendações; sem recomendação
    aberta esse último comando afeta 0 linhas, a função devolvia 0 e o serviço respondia "Tarefa não encontrada", embora a
    tarefa JÁ tivesse sido alterada. Agora o número vem do UPDATE da própria tarefa.

  ITEM 47 - passos de objetivo ignoravam a agenda (db.py, servicos.py, app.py, templates/objetivos.html)
    Os passos criados à mão ou pela prévia (agora editável) iam direto ao banco: sem conferir conflito de horário e sem o
    evento "criou" que as tarefas normais registram (o histórico do aprendizado não via esses passos). Agora:
      - o passo grava o evento "criou", igual a uma tarefa normal;
      - antes de gravar, a lista inteira é conferida contra a agenda E contra os próprios passos entre si;
      - na prévia: se houver conflito, NADA é criado, a janela mostra o que bate com o quê e oferece
        "Adicionar mesmo assim" (ou a pessoa edita o horário e confirma de novo);
      - no passo manual: a tela mostra o aviso com "Adicionar mesmo assim";
      - NEOCORTEX_CONFLITO_UI=avisar continua valendo: grava sem perguntar, como nas tarefas;
      - de quebra, o passo manual deixa de dar erro 500 com data inválida e confere se o objetivo é da pessoa.

É TUDO OU NADA: se qualquer trecho de qualquer arquivo não for reconhecido, nenhum arquivo é gravado.
Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_conflito_e_reagendamento.py            # só mostra
    python atualizar_conflito_e_reagendamento.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

# ----------------------------------------------------------------------------------------------------------------------
# db.py
# ----------------------------------------------------------------------------------------------------------------------
DB = (
    ("item 02: guardar o rowcount do UPDATE da tarefa",
     '''                valores,
            )

            novo_inicio = _como_datetime(campos.get("data_inicio", antes["data_inicio"]))''',
     '''                valores,
            )
            linhas_alteradas = cur.rowcount   # [REAGENDAMENTO] guardar já: os comandos abaixo (evento, recomendações) mudam o cur.rowcount

            novo_inicio = _como_datetime(campos.get("data_inicio", antes["data_inicio"]))'''),
    ("item 02: devolver o número do UPDATE, não o do último comando",
     '''                _resolver_recomendacoes_da_tarefa(cur, id_tarefa, "recusou", "cancelada")

            return cur.rowcount''',
     '''                _resolver_recomendacoes_da_tarefa(cur, id_tarefa, "recusou", "cancelada")

            return linhas_alteradas'''),
    ("item 47: o passo grava o evento 'criou', como uma tarefa normal",
     '''            id_tarefa = cur.fetchone()["id_tarefa"]
            cur.execute(
                "INSERT INTO tarefa_objetivos (id_tarefa, id_objetivo) VALUES (%s, %s) ON CONFLICT DO NOTHING",''',
     '''            id_tarefa = cur.fetchone()["id_tarefa"]
            _registrar_evento(cur, id_tarefa, "criou", {"origem": "manual"})   # [CONFLITO-PASSOS] igual a db.criar_tarefa: o histórico passa a ver o passo
            cur.execute(
                "INSERT INTO tarefa_objetivos (id_tarefa, id_objetivo) VALUES (%s, %s) ON CONFLICT DO NOTHING",'''),
)

# ----------------------------------------------------------------------------------------------------------------------
# servicos.py
# ----------------------------------------------------------------------------------------------------------------------
FUNCAO_SERVICO = '''def conflitos_de_passos(id_usuario, passos):
    """
    [CONFLITO-PASSOS] Confere uma lista de passos ANTES de gravar qualquer um (cada passo: dict com titulo, inicio e fim, datetime).
    Devolve [{'indice', 'titulo', 'inicio', 'fim', 'conflitos': [{'tipo', 'titulo', 'inicio', 'fim'}]}], só dos passos que colidem.
    Além da agenda (agenda.conflitos_para), considera os choques ENTRE os próprios passos da lista, que a agenda ainda não conhece.
    """
    saida = []
    for i, p in enumerate(passos):
        achados = list(agenda.conflitos_para(id_usuario, p["inicio"], p["fim"]))
        for j, q in enumerate(passos):
            if j != i and p["inicio"] < q["fim"] and q["inicio"] < p["fim"]:
                achados.append({"tipo": "passo", "titulo": q["titulo"],
                                "inicio": q["inicio"].isoformat(timespec="minutes"), "fim": q["fim"].isoformat(timespec="minutes")})
        if achados:
            saida.append({"indice": i, "titulo": p["titulo"], "inicio": p["inicio"].isoformat(timespec="minutes"),
                          "fim": p["fim"].isoformat(timespec="minutes"), "conflitos": achados})
    return saida


'''
ANTES_ATUALIZAR = "def atualizar_tarefa(id_usuario, id_tarefa, titulo=None, categoria=_AUSENTE, data_inicio=None,"
SERVICOS = (
    ("item 47: conferir uma lista de passos contra a agenda e entre si",
     ANTES_ATUALIZAR, FUNCAO_SERVICO + ANTES_ATUALIZAR),
)

# ----------------------------------------------------------------------------------------------------------------------
# app.py
# ----------------------------------------------------------------------------------------------------------------------
HELPERS_APP = '''def _confirmou_conflito():
    return CONFLITO_UI_MODO == "avisar" or request.form.get("confirmar_conflito") in _VERDADEIRO


def _confirmou_conflito_passos(valor):
    """[CONFLITO-PASSOS] 'avisar' grava sem perguntar; 'confirmar' (o padrão) só grava se a pessoa disse 'adicionar mesmo assim'."""
    return CONFLITO_UI_MODO == "avisar" or valor is True or str(valor).strip().lower() in _VERDADEIRO


def _resposta_conflito_passos(conflitos):
    """409 com o que bate com o quê; nada foi gravado. A prévia mostra o texto e oferece 'Adicionar mesmo assim'."""
    linhas = []
    for c in conflitos:
        inicio = datetime.fromisoformat(c["inicio"])
        linhas.append(f"Passo {c['indice'] + 1} ({inicio:%d/%m %H:%M}): " + servicos.descrever_conflitos(c["conflitos"]))
    return jsonify(erro="Há conflito de horário:\\n" + "\\n".join(linhas), conflitos=conflitos, exige_confirmacao=True), 409'''

MANUAL_ANTIGA = '''@app.route("/objetivos/<int:id_objetivo>/fragmentos", methods=["POST"])
def criar_fragmento_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    titulo = request.form.get("titulo", "").strip()
    data = request.form.get("data")
    hora = request.form.get("hora") or "09:00"
    if titulo and data:
        inicio = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
        fim = inicio + timedelta(minutes=30)
        db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, titulo, inicio, fim)
        _mascote_evento("tarefa_criada")   # [MASCOTE]
        _verificar_desbloqueio_cafeteria(usuario_logado())   # [TEMA]
    return redirect(url_for("objetivos"))'''
MANUAL_NOVA = '''@app.route("/objetivos/<int:id_objetivo>/fragmentos", methods=["POST"])
def criar_fragmento_rota(id_objetivo):
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    titulo = " ".join(request.form.get("titulo", "").split())[:200]
    data = request.form.get("data", "")
    hora = request.form.get("hora") or "09:00"
    if not titulo or not data:
        return redirect(url_for("objetivos"))
    try:
        inicio = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        abort(400)   # data ou hora inválida: só chega assim por envio manual (os campos do navegador não deixam)
    if not db.buscar_objetivo(id_objetivo, usuario_logado()):
        abort(404)   # objetivo de outra pessoa (ou que não existe): não cria nada e não conta ponto
    passo = {"titulo": titulo, "inicio": inicio, "fim": inicio + timedelta(minutes=30)}
    conflitos = servicos.conflitos_de_passos(usuario_logado(), [passo])   # [CONFLITO-PASSOS]
    if conflitos and not _confirmou_conflito_passos(request.form.get("confirmar_conflito")):
        return _render_objetivos(conflito_passo={
            "id_objetivo": id_objetivo, "titulo": titulo, "data": data, "hora": hora, "data_br": inicio.strftime("%d/%m/%Y"),
            "texto": servicos.descrever_conflitos(conflitos[0]["conflitos"]),
        })
    db.criar_fragmento_objetivo(usuario_logado(), id_objetivo, passo["titulo"], passo["inicio"], passo["fim"])
    _mascote_evento("tarefa_criada")   # [MASCOTE]
    _verificar_desbloqueio_cafeteria(usuario_logado())   # [TEMA]
    return redirect(url_for("objetivos"))'''

APP = (
    ("item 47: funções de apoio do conflito de passos",
     '''def _confirmou_conflito():
    return CONFLITO_UI_MODO == "avisar" or request.form.get("confirmar_conflito") in _VERDADEIRO''', HELPERS_APP),
    ("item 47: tela de Objetivos reaproveitável (cabeçalho)",
     '''@app.route("/objetivos")
def objetivos():
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    lista = db.listar_objetivos(usuario_logado())''',
     '''def _render_objetivos(conflito_passo=None):   # [CONFLITO-PASSOS] a tela também serve ao aviso de conflito do passo manual
    lista = db.listar_objetivos(usuario_logado())'''),
    ("item 47: tela de Objetivos reaproveitável (final) e a rota",
     '''        abrir_fragmentacao=abrir,
        **_pagina("objetivos", "Objetivos"),
    )
''',
     '''        abrir_fragmentacao=abrir,
        conflito_passo=conflito_passo,
        **_pagina("objetivos", "Objetivos"),
    )


@app.route("/objetivos")
def objetivos():
    if not usuario_logado():
        return redirect(url_for("tela_login"))
    return _render_objetivos()
'''),
    ("item 47: passo manual confere conflito, data e dono do objetivo", MANUAL_ANTIGA, MANUAL_NOVA),
    ("item 47: confirmar passos de objetivo NOVO confere conflito",
     '''        return jsonify(erro=erro), 400      # nada foi criado: a lista inteira é conferida antes de gravar

    id_objetivo = db.criar_objetivo(usuario_logado(), titulo_objetivo, prazo=prazo_str)''',
     '''        return jsonify(erro=erro), 400      # nada foi criado: a lista inteira é conferida antes de gravar
    conflitos = servicos.conflitos_de_passos(usuario_logado(), passos)   # [CONFLITO-PASSOS]
    if conflitos and not _confirmou_conflito_passos(dados.get("confirmar_conflito")):
        return _resposta_conflito_passos(conflitos)      # nada foi criado (nem o objetivo)

    id_objetivo = db.criar_objetivo(usuario_logado(), titulo_objetivo, prazo=prazo_str)'''),
    ("item 47: confirmar passos de objetivo EXISTENTE confere conflito",
     '''        return jsonify(erro="O prazo já passou. Escolha uma data de hoje em diante."), 400
    if prazo_escolhido and not objetivo["prazo"]:''',
     '''        return jsonify(erro="O prazo já passou. Escolha uma data de hoje em diante."), 400
    conflitos = servicos.conflitos_de_passos(usuario_logado(), passos)   # [CONFLITO-PASSOS]
    if conflitos and not _confirmou_conflito_passos(request.args.get("confirmar_conflito")):
        return _resposta_conflito_passos(conflitos)      # nada foi criado nem alterado (nem o prazo)
    if prazo_escolhido and not objetivo["prazo"]:'''),
)

# ----------------------------------------------------------------------------------------------------------------------
# templates/objetivos.html
# ----------------------------------------------------------------------------------------------------------------------
BANNER = '''  <div style="display:flex;flex-direction:column;gap:14px;">
    {% if conflito_passo %}
    <div class="nc-card" role="alert" style="padding:18px 24px;border:2px solid #B45309;">
      <p style="margin:0 0 6px;font-size:14px;font-weight:800;color:var(--nc-text);">Esse horário já está ocupado</p>
      <p style="margin:0 0 14px;font-size:13px;line-height:1.5;color:var(--nc-text2);overflow-wrap:anywhere;">O passo “{{ conflito_passo.titulo }}” ({{ conflito_passo.data_br }} às {{ conflito_passo.hora }}) conflita com: {{ conflito_passo.texto }}.</p>
      <form method="post" action="{{ url_for('criar_fragmento_rota', id_objetivo=conflito_passo.id_objetivo) }}" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="titulo" value="{{ conflito_passo.titulo }}">
        <input type="hidden" name="data" value="{{ conflito_passo.data }}">
        <input type="hidden" name="hora" value="{{ conflito_passo.hora }}">
        <input type="hidden" name="confirmar_conflito" value="1">
        <button type="submit" class="btn-primary" style="height:40px;padding:0 20px;">Adicionar mesmo assim</button>
        <a href="{{ url_for('objetivos') }}" class="btn-outline" style="display:inline-flex;align-items:center;height:40px;padding:0 20px;text-decoration:none;">Escolher outro horário</a>
      </form>
    </div>
    {% endif %}
    {% for o in objetivos %}'''

HTML = (
    ("item 47: aviso de conflito do passo manual",
     '''  <div style="display:flex;flex-direction:column;gap:14px;">
    {% for o in objetivos %}''', BANNER),
    ("item 47: prévia: mensagem em várias linhas e botão 'Adicionar mesmo assim'",
     '''<p id="fragAutoErro" role="alert" style="margin:0 0 12px;min-height:18px;font-size:13px;line-height:1.4;font-weight:600;color:#B91C1C;"></p>''',
     '''<p id="fragAutoErro" role="alert" style="margin:0 0 12px;min-height:18px;font-size:13px;line-height:1.4;font-weight:600;color:#B91C1C;white-space:pre-line;"></p>
      <button type="button" id="btnMesmoAssim" class="btn-outline" style="display:none;width:100%;height:44px;margin-bottom:10px;">Adicionar mesmo assim</button>'''),
    ("item 47: prévia: variáveis do conflito",
     '''    const erro = document.getElementById('fragAutoErro');''',
     '''    const erro = document.getElementById('fragAutoErro');
    const mesmoAssim = document.getElementById('btnMesmoAssim');   // [CONFLITO-PASSOS]
    let confirmarConflito = false;
    const limparConflito = () => { confirmarConflito = false; mesmoAssim.style.display = 'none'; };'''),
    ("item 47: prévia: remover um passo refaz a conferência",
     '''remover.addEventListener('click', () => { li.remove(); erro.textContent = ''; atualizarCabecalho(); });''',
     '''remover.addEventListener('click', () => { li.remove(); erro.textContent = ''; limparConflito(); atualizarCabecalho(); });'''),
    ("item 47: prévia: o pedido leva a confirmação do conflito",
     '''        body = JSON.stringify({ titulo_objetivo: fragAutoContexto.titulo, prazo: fragAutoContexto.prazo, propostas: editados });
      } else {
        url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/confirmar`
          + (fragAutoContexto.prazoEscolhido ? '?prazo=' + encodeURIComponent(fragAutoContexto.prazoEscolhido) : '');
        body = JSON.stringify(editados);
      }''',
     '''        body = JSON.stringify({ titulo_objetivo: fragAutoContexto.titulo, prazo: fragAutoContexto.prazo, propostas: editados, confirmar_conflito: confirmarConflito });
      } else {
        const consulta = [];
        if (fragAutoContexto.prazoEscolhido) consulta.push('prazo=' + encodeURIComponent(fragAutoContexto.prazoEscolhido));
        if (confirmarConflito) consulta.push('confirmar_conflito=1');
        url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/confirmar` + (consulta.length ? '?' + consulta.join('&') : '');
        body = JSON.stringify(editados);
      }'''),
    ("item 47: prévia: mostra o conflito e oferece 'Adicionar mesmo assim'",
     '''        if (!resp.ok) { erro.textContent = dados.erro || 'Não foi possível adicionar os passos.'; botao.disabled = false; botao.textContent = 'Adicionar à agenda'; return; }''',
     '''        if (!resp.ok) {
          erro.textContent = dados.erro || 'Não foi possível adicionar os passos.';
          mesmoAssim.style.display = (resp.status === 409 && dados.exige_confirmacao) ? 'block' : 'none';
          botao.disabled = false; botao.textContent = 'Adicionar à agenda'; return;
        }'''),
    ("item 47: prévia: ligar o botão e refazer a conferência ao editar",
     '''        erro.textContent = 'Não foi possível conectar ao servidor.';
        botao.disabled = false;
        botao.textContent = 'Adicionar à agenda';
      }
    });
  }
</script>''',
     '''        erro.textContent = 'Não foi possível conectar ao servidor.';
        botao.disabled = false;
        botao.textContent = 'Adicionar à agenda';
      }
    });
    mesmoAssim.addEventListener('click', () => { confirmarConflito = true; document.getElementById('btnConfirmarFragmentos').click(); });
    lista.addEventListener('input', limparConflito);   // mudou o dia ou a hora: confere de novo, sem herdar o "mesmo assim"
  }
</script>'''),
)

ALVOS = (
    ("db.py", DB, "[REAGENDAMENTO]"),
    ("servicos.py", SERVICOS, "[CONFLITO-PASSOS]"),
    ("app.py", APP, "[CONFLITO-PASSOS]"),
    ("templates/objetivos.html", HTML, "[CONFLITO-PASSOS]"),
)


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\n" if not crlf else "\r\n")).encode("utf-8")


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
    ap = argparse.ArgumentParser(description="Corrige o reagendamento (item 02) e o conflito de horário nos passos (item 47).")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    plano, problemas, ja_feitos = [], [], 0
    for rel, trocas, marca in ALVOS:
        arquivo = RAIZ / rel
        if not arquivo.exists():
            problemas.append(f"{rel}: o arquivo não existe.")
            continue
        texto, crlf = ler(arquivo)
        if marca in texto and all(depois in texto for _, _, depois in trocas):
            print(f"   {rel}: já corrigido (nada a fazer).")
            ja_feitos += 1
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
        print("\nNada foi alterado. Para aplicar:  python atualizar_conflito_e_reagendamento.py --aplicar")
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
