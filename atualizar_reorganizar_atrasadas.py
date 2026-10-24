"""
NEOCORTEX - atualizar_reorganizar_atrasadas.py

Acrescenta à tela de Tarefas o botão "Reorganizar atrasadas", que dá novos horários ao que ficou para trás
(a ideia original do projeto: se o que foi marcado não é cumprido, a rotina se readapta sem culpa):

  - o botão aparece quando há tarefas atrasadas (últimas 2 semanas) e mostra quantas são;
  - ao clicar, o sistema procura, para cada uma, o primeiro horário livre dos próximos 14 dias, usando o que aprendeu:
    período em que a pessoa rende (por categoria), folga pelo atraso típico; mais importantes e mais antigas primeiro (até 12);
  - uma proposta não disputa o horário de outra; passos de objetivo nunca passam do prazo do objetivo;
  - a PRÉVIA é editável (dia, hora, tirar tarefas) e mostra o "por quê" de cada horário; NADA muda até confirmar;
  - ao confirmar, confere conflito (com a agenda e entre as próprias tarefas); com conflito, nada muda e a janela oferece
    "Reorganizar mesmo assim";
  - cada tarefa é atualizada pelo caminho de sempre (servicos.atualizar_tarefa): evento de adiamento, aprendizado e o
    mascote reconhece "replanejar" (e a versão completa do tema Campeonato conta, como ao remarcar uma atrasada).

DEPENDE de dois pacotes: "conflito e reagendamento" (corrige o falso 'tarefa não encontrada' ao adiar) e "aprendizado aplicado"
(horários por categoria e reservas). Sem eles o script recusa e diz qual falta.

Mexe em app.py e templates/tarefas.html. É TUDO OU NADA. Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto:

    python atualizar_reorganizar_atrasadas.py            # só mostra
    python atualizar_reorganizar_atrasadas.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro.

SE VOCÊ JÁ APLICOU A PRIMEIRA VERSÃO deste pacote e a janela deu "não foi possível conectar ao servidor" (erro 400 no F12):
rode este script de novo. Ele corrige a tela de Tarefas (faltava o token de segurança) e passa a explicar os erros
("Sua sessão de segurança expirou...") em vez de dizer que não conectou.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ALVOS = (
    ('app.py', '[REORGANIZAR]', (
        ('a tela de Tarefas sabe quantas atrasadas há (decide se o botão aparece)',
         r'''        categoria_filtro=categoria_filtro,
        **_pagina("tarefas", "Tarefas", **extra),
    )''',
         r'''        categoria_filtro=categoria_filtro,
        n_atrasadas=_contar_atrasadas_para_reorganizar(),   # [REORGANIZAR]
        **_pagina("tarefas", "Tarefas", **extra),
    )'''),
        ('rotas de prévia e de confirmação da reorganização',
         r'''@app.route("/tarefas/nova", methods=["POST"])''',
         r'''# ============================================================
# REORGANIZAR ATRASADAS  [REORGANIZAR]
# O que ficou para trás ganha novos horários livres, escolhidos com o que o sistema aprendeu (período em que a pessoa rende,
# por categoria, folga pelo atraso). Sempre com PRÉVIA editável e conferência de conflito; nada muda sem confirmar.
# ============================================================
REORG_MAX_TAREFAS = 12
REORG_JANELA_ATRASO_DIAS = 14     # só olha o que atrasou nas últimas 2 semanas
REORG_DIAS_A_FRENTE = 14          # procura horário livre nas próximas 2 semanas
_REORG_CATEGORIAS = ("estudo", "trabalho", "hobby", "pessoal", "saude")


def _atrasadas_para_reorganizar(id_usuario, agora):
    """Tarefas abertas com o prazo vencido (sem dependência pendente), mais prioritárias e mais antigas primeiro."""
    abertas = db.listar_tarefas_abertas(id_usuario, data_fim_minima=agora - timedelta(days=REORG_JANELA_ATRASO_DIAS))
    abertas = db.enriquecer_tarefas(id_usuario, abertas)
    atrasadas = [t for t in abertas if t["data_fim"] < agora and not t.get("dependencia_pendente")]
    prioridade = {"alta": 0, "media": 1, "baixa": 2}
    atrasadas.sort(key=lambda t: (prioridade.get(t.get("prioridade"), 1), t["data_fim"]))
    return atrasadas


def _contar_atrasadas_para_reorganizar():
    """Quantas atrasadas podem ser reorganizadas (decide se o botão aparece). Nunca derruba a tela de Tarefas."""
    try:
        return len(_atrasadas_para_reorganizar(usuario_logado(), datetime.now()))
    except Exception:
        return 0


@app.route("/tarefas/reorganizar/previa", methods=["POST"])
@login_obrigatorio
def reorganizar_previa():
    agora = datetime.now()
    atrasadas = _atrasadas_para_reorganizar(usuario_logado(), agora)
    if not atrasadas:
        return jsonify(erro="Você não tem tarefas atrasadas para reorganizar."), 409
    propostas, sem_horario, reservas = [], [], []
    for t in atrasadas[:REORG_MAX_TAREFAS]:
        duracao_min = int(min(max((t["data_fim"] - t["data_inicio"]).total_seconds() // 60, 15), 480))
        categoria = t.get("categoria") if t.get("categoria") in _REORG_CATEGORIAS else None
        limite = t["objetivo_prazo"].date() if t.get("objetivo_prazo") else None     # passo de objetivo não passa do prazo dele
        achou = None
        for desloc in range(0, REORG_DIAS_A_FRENTE + 1):
            dia = agora.date() + timedelta(days=desloc)
            if limite and dia > limite:
                break
            r = decisao.sugerir_horarios(usuario_logado(), dia, duracao_min, agora, max_sugestoes=1, categoria=categoria, reservas=reservas)
            if r["sugestoes"]:
                achou = r["sugestoes"][0]
                break
        if not achou:
            sem_horario.append({"id_tarefa": t["id_tarefa"], "titulo": t["titulo"]})
            continue
        inicio, fim = datetime.fromisoformat(achou["inicio"]), datetime.fromisoformat(achou["fim"])
        reservas.append((inicio, fim + timedelta(minutes=achou.get("folga_min", 0))))     # a próxima proposta não disputa este horário
        propostas.append({
            "id_tarefa": t["id_tarefa"], "titulo": t["titulo"], "categoria": t.get("categoria"), "duracao_min": duracao_min,
            "de": {"inicio": t["data_inicio"].isoformat(timespec="minutes"), "fim": t["data_fim"].isoformat(timespec="minutes")},
            "inicio": achou["inicio"], "fim": achou["fim"], "motivo": achou["base"],
        })
    if not propostas:
        return jsonify(erro=f"Não encontrei horário livre nos próximos {REORG_DIAS_A_FRENTE} dias para as tarefas atrasadas."), 409
    return jsonify(propostas=propostas, sem_horario=sem_horario, total_atrasadas=len(atrasadas))


def _conflitos_da_reorganizacao(id_usuario, itens):
    """Conflito de cada novo horário com a agenda (ignorando a própria tarefa) e dos itens entre si."""
    saida = []
    for i, p in enumerate(itens):
        achados = list(agenda.conflitos_para(id_usuario, p["inicio"], p["fim"], categoria=p["categoria"], ignorar_id_tarefa=p["id_tarefa"]))
        for j, q in enumerate(itens):
            if j != i and p["inicio"] < q["fim"] and q["inicio"] < p["fim"]:
                achados.append({"tipo": "tarefa", "titulo": q["titulo"], "inicio": q["inicio"].isoformat(timespec="minutes"),
                                "fim": q["fim"].isoformat(timespec="minutes")})
        if achados:
            saida.append({"indice": i, "titulo": p["titulo"], "inicio": p["inicio"].isoformat(timespec="minutes"),
                          "fim": p["fim"].isoformat(timespec="minutes"), "conflitos": achados})
    return saida


@app.route("/tarefas/reorganizar/confirmar", methods=["POST"])
@login_obrigatorio
def reorganizar_confirmar():
    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens")
    if not isinstance(itens, list) or not 1 <= len(itens) <= REORG_MAX_TAREFAS:
        return jsonify(erro="Nada para reorganizar."), 400
    agora, validados, vistos = datetime.now(), [], set()
    for it in itens:
        try:
            id_tarefa = int(it["id_tarefa"])
            inicio = datetime.fromisoformat(str(it["inicio"]))
        except (KeyError, TypeError, ValueError):
            return jsonify(erro="Um dos itens está com tarefa ou horário inválido."), 400
        if id_tarefa in vistos:
            return jsonify(erro="A mesma tarefa aparece mais de uma vez."), 400
        vistos.add(id_tarefa)
        if not agora - timedelta(days=1) <= inicio <= agora + timedelta(days=365):
            return jsonify(erro="Um dos horários está fora do intervalo permitido (de hoje até 1 ano à frente)."), 400
        tarefa = db.buscar_tarefa(id_tarefa, usuario_logado())
        if not tarefa or tarefa["status"] not in ("pendente", "em_andamento"):
            return jsonify(erro="Uma das tarefas não está mais aberta. Reabra a janela para ver a lista atual."), 409
        fim = inicio + (tarefa["data_fim"] - tarefa["data_inicio"])        # a duração é a da própria tarefa, nunca a do navegador
        validados.append({"id_tarefa": id_tarefa, "titulo": tarefa["titulo"], "categoria": tarefa.get("categoria"), "inicio": inicio, "fim": fim})
    conflitos = _conflitos_da_reorganizacao(usuario_logado(), validados)
    if conflitos and not _confirmou_conflito_passos(dados.get("confirmar_conflito")):
        linhas = []
        for c in conflitos:
            quando = datetime.fromisoformat(c["inicio"])
            linhas.append(f"Tarefa {c['indice'] + 1} ({quando:%d/%m %H:%M}): " + servicos.descrever_conflitos(c["conflitos"]))
        return jsonify(erro="Há conflito de horário:\n" + "\n".join(linhas), conflitos=conflitos, exige_confirmacao=True), 409
    feitas = 0
    for v in validados:
        resultado = servicos.atualizar_tarefa(
            usuario_logado(), v["id_tarefa"],
            data_inicio=v["inicio"].isoformat(timespec="minutes"), data_fim=v["fim"].isoformat(timespec="minutes"), confirmar_conflito=True,
        )
        if resultado.get("sucesso"):
            feitas += 1
    if feitas:
        _mascote_evento("tarefa_replanejada")   # [MASCOTE] reorganizar o que atrasou é ajuste, não é culpa
        _liberar_tema(usuario_logado(), "campeonato")   # [TEMA]
    return jsonify(ok=True, reorganizadas=feitas, falharam=len(validados) - feitas, redirect=url_for("tarefas"))


@app.route("/tarefas/nova", methods=["POST"])'''),
    )),
    ('templates/tarefas.html', '[REORGANIZAR]', (
        ("botão 'Reorganizar atrasadas' no cabeçalho da lista",
         r'''    </select>
  </div>

  <div class="nc-card" style="overflow:hidden;">''',
         r'''    </select>
  </div>

  {% if n_atrasadas %}
  <div style="margin:-4px 0 16px;">   {# [REORGANIZAR] #}
    <button type="button" id="btnReorganizar" class="btn-outline" style="height:40px;padding:0 18px;" onclick="abrirReorganizar()">🔄 Reorganizar atrasadas ({{ n_atrasadas }})</button>
  </div>
  {% endif %}

  <div class="nc-card" style="overflow:hidden;">'''),
        ('janela de prévia editável da reorganização',
         r'''  {% endfor %}
</div>
{% endblock %}''',
         r'''  {% endfor %}

  {# [REORGANIZAR] janela que propõe novos horários para as tarefas atrasadas #}
  {% if n_atrasadas %}
  <div id="modalReorganizar" class="modal-overlay hidden">
    <div class="modal-box" style="max-height:88vh;overflow-y:auto;" role="dialog" aria-modal="true" aria-labelledby="reorgTitulo">
      <h3 id="reorgTitulo" style="margin:0 0 6px;font-size:18px;font-weight:800;color:var(--nc-text);">Reorganizar atrasadas</h3>
      <p id="reorgAjuda" style="margin:0 0 12px;font-size:13px;line-height:1.5;color:var(--nc-text2);"></p>
      <ul id="reorgLista" style="list-style:none;margin:0 0 12px;padding:0;max-height:340px;overflow-y:auto;"></ul>
      <p id="reorgSemHorario" role="status" style="display:none;margin:0 0 12px;font-size:13px;line-height:1.5;font-weight:600;color:#B45309;"></p>
      <p id="reorgErro" role="alert" style="margin:0 0 12px;min-height:18px;font-size:13px;line-height:1.4;font-weight:600;color:#B91C1C;white-space:pre-line;"></p>
      <button type="button" id="btnReorgMesmoAssim" class="btn-outline" style="display:none;width:100%;height:44px;margin-bottom:10px;">Reorganizar mesmo assim</button>
      <button type="button" id="btnReorgConfirmar" class="btn-primary" style="width:100%;height:48px;margin-bottom:10px;" disabled>Reorganizar</button>
      <button type="button" id="btnReorgCancelar" class="btn-outline" style="width:100%;height:48px;">Cancelar</button>
    </div>
  </div>
  <script>
    (function () {
      const modal = document.getElementById('modalReorganizar');
      const lista = document.getElementById('reorgLista'), erro = document.getElementById('reorgErro'), titulo = document.getElementById('reorgTitulo');
      const ajuda = document.getElementById('reorgAjuda'), semHorario = document.getElementById('reorgSemHorario');
      const confirmar = document.getElementById('btnReorgConfirmar'), mesmoAssim = document.getElementById('btnReorgMesmoAssim');
      const pad = (n) => String(n).padStart(2, '0');
      const hoje = (function (d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); })(new Date());
      const quando = (iso) => iso.slice(8, 10) + '/' + iso.slice(5, 7) + ' ' + iso.slice(11, 16);
      const csrf = () => '{{ csrf_token() }}';   // o token vem direto do servidor (esta tela nao declara a meta csrf-token)
      const mensagemDe = (status, oque) => (status === 400 ? 'Sua sessão de segurança expirou. Recarregue a página e tente de novo.' : 'Não foi possível ' + oque + ' (código ' + status + ').');
      const estiloCampo = 'height:40px;padding:0 10px;border:1.5px solid var(--nc-border);border-radius:10px;background:var(--nc-surface, #fff);color:var(--nc-text);font:inherit;font-size:13px;box-sizing:border-box;';
      let confirmarConflito = false;

      function limparConflito() { confirmarConflito = false; mesmoAssim.style.display = 'none'; }
      function atualizarCabecalho() {
        const n = lista.children.length;
        titulo.textContent = n ? 'Reorganizar ' + n + (n === 1 ? ' tarefa atrasada' : ' tarefas atrasadas') : 'Reorganizar atrasadas';
        confirmar.disabled = n === 0;
        [].forEach.call(lista.children, function (li, i) {
          li.querySelector('[data-campo="data"]').setAttribute('aria-label', 'Novo dia da tarefa ' + (i + 1));
          li.querySelector('[data-campo="hora"]').setAttribute('aria-label', 'Nova hora da tarefa ' + (i + 1));
          li.querySelector('[data-campo="remover"]').setAttribute('aria-label', 'Não reorganizar a tarefa ' + (i + 1));
        });
        if (n === 0 && !erro.textContent) erro.textContent = 'Todas foram removidas. Use Cancelar para fechar.';
      }
      function criarLinha(p) {
        const li = document.createElement('li');
        li.dataset.id = String(p.id_tarefa);
        li.style.cssText = 'padding:12px 0;border-bottom:1px solid var(--nc-border);';
        const nome = document.createElement('div');
        nome.textContent = p.titulo;
        nome.style.cssText = 'font-size:14px;font-weight:700;color:var(--nc-text);overflow-wrap:anywhere;';
        const era = document.createElement('div');
        era.textContent = 'estava em ' + quando(p.de.inicio) + ' · ' + p.duracao_min + ' min';
        era.style.cssText = 'font-size:12px;font-weight:600;color:var(--nc-text2);margin:2px 0 8px;';
        const linha = document.createElement('div');
        linha.style.cssText = 'display:flex;gap:8px;align-items:center;';
        const dia = document.createElement('input'); dia.type = 'date'; dia.value = p.inicio.slice(0, 10); dia.min = hoje; dia.dataset.campo = 'data'; dia.style.cssText = estiloCampo + 'flex:1;min-width:0;';
        const hora = document.createElement('input'); hora.type = 'time'; hora.value = p.inicio.slice(11, 16); hora.dataset.campo = 'hora'; hora.style.cssText = estiloCampo + 'width:128px;flex:none;';
        const remover = document.createElement('button');
        remover.type = 'button'; remover.dataset.campo = 'remover'; remover.textContent = '✕';
        remover.style.cssText = 'width:40px;height:40px;flex:none;border:1.5px solid var(--nc-border);border-radius:10px;background:transparent;color:var(--nc-text2);font-size:14px;font-weight:700;cursor:pointer;';
        remover.addEventListener('click', function () { li.remove(); erro.textContent = ''; limparConflito(); atualizarCabecalho(); });
        linha.append(dia, hora, remover);
        li.append(nome, era, linha);
        const razoes = (p.motivo || []).filter(Boolean).slice(0, 2).join(' · ');
        if (razoes) {
          const motivo = document.createElement('div');
          motivo.textContent = 'Por quê: ' + razoes;
          motivo.style.cssText = 'font-size:12px;line-height:1.4;color:var(--nc-text2);margin-top:6px;';
          li.appendChild(motivo);
        }
        return li;
      }

      window.abrirReorganizar = async function () {
        modal.classList.remove('hidden');
        lista.innerHTML = ''; erro.textContent = ''; semHorario.style.display = 'none'; limparConflito();
        titulo.textContent = 'Procurando horários...'; ajuda.textContent = 'Estou olhando a sua agenda e o que aprendi sobre quando você rende.'; confirmar.disabled = true;
        try {
          const resp = await fetch('/tarefas/reorganizar/previa', { method: 'POST', headers: { 'X-CSRFToken': csrf() } });
          const dados = await resp.json().catch(function () { return {}; });
          if (!resp.ok) { titulo.textContent = 'Reorganizar atrasadas'; ajuda.textContent = ''; erro.textContent = dados.erro || mensagemDe(resp.status, 'montar a proposta'); return; }
          dados.propostas.forEach(function (p) { lista.appendChild(criarLinha(p)); });
          ajuda.textContent = 'Escolhi novos horários livres, levando em conta o que aprendi sobre você. Ajuste o dia ou a hora, ou tire o que não quiser reorganizar agora. Nada muda até você confirmar.';
          const mostradas = dados.propostas.length + dados.sem_horario.length;
          if (dados.sem_horario.length) {
            semHorario.textContent = 'Sem horário livre nos próximos dias: ' + dados.sem_horario.map(function (s) { return s.titulo; }).join(', ') + '. Elas continuam como estão.';
            semHorario.style.display = 'block';
          }
          if (dados.total_atrasadas > mostradas) ajuda.textContent += ' (Mostrando as ' + mostradas + ' mais importantes de ' + dados.total_atrasadas + '.)';
          atualizarCabecalho();
        } catch (e) {
          titulo.textContent = 'Reorganizar atrasadas'; ajuda.textContent = ''; erro.textContent = 'Não foi possível conectar ao servidor.';
        }
      };

      async function enviar() {
        const itens = [];
        const linhas = [].slice.call(lista.children);
        for (let i = 0; i < linhas.length; i++) {
          const d = linhas[i].querySelector('[data-campo="data"]'), h = linhas[i].querySelector('[data-campo="hora"]');
          let motivo = '';
          if (!d.value || !h.value) motivo = 'escolha o dia e a hora.';
          else if (d.value < hoje) motivo = 'escolha uma data de hoje em diante.';
          if (motivo) { erro.textContent = 'Tarefa ' + (i + 1) + ': ' + motivo; (d.value ? h : d).focus(); return; }
          itens.push({ id_tarefa: Number(linhas[i].dataset.id), inicio: d.value + 'T' + h.value });
        }
        if (!itens.length) return;
        erro.textContent = '';
        confirmar.disabled = true; const rotulo = confirmar.textContent; confirmar.textContent = 'Reorganizando...';
        try {
          const resp = await fetch('/tarefas/reorganizar/confirmar', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify({ itens: itens, confirmar_conflito: confirmarConflito }) });
          const dados = await resp.json().catch(function () { return {}; });
          if (!resp.ok) {
            erro.textContent = dados.erro || mensagemDe(resp.status, 'reorganizar');
            mesmoAssim.style.display = (resp.status === 409 && dados.exige_confirmacao) ? 'block' : 'none';
            confirmar.disabled = false; confirmar.textContent = rotulo; return;
          }
          window.location.href = dados.redirect || '/tarefas';
        } catch (e) {
          erro.textContent = 'Não foi possível conectar ao servidor.'; confirmar.disabled = false; confirmar.textContent = rotulo;
        }
      }
      confirmar.addEventListener('click', enviar);
      mesmoAssim.addEventListener('click', function () { confirmarConflito = true; enviar(); });
      lista.addEventListener('input', limparConflito);
      document.getElementById('btnReorgCancelar').addEventListener('click', function () { modal.classList.add('hidden'); });
    })();
  </script>
  {% endif %}
</div>
{% endblock %}'''),
    ))
)

# Correções de uma versão anterior deste pacote (a janela dava erro 400 ao clicar: faltava o token CSRF nesta tela)
CORRECOES = (
    ('templates/tarefas.html',
     r'''const csrf = () => { const m = document.querySelector('meta[name="csrf-token"]'); return m ? m.content : ''; };''',
     r'''const csrf = () => '{{ csrf_token() }}';   // o token vem direto do servidor (esta tela nao declara a meta csrf-token)
      const mensagemDe = (status, oque) => (status === 400 ? 'Sua sessão de segurança expirou. Recarregue a página e tente de novo.' : 'Não foi possível ' + oque + ' (código ' + status + ').');'''),
    ('templates/tarefas.html',
     r'''const dados = await resp.json();
          if (!resp.ok) { titulo.textContent = 'Reorganizar atrasadas'; ajuda.textContent = ''; erro.textContent = dados.erro || 'Não foi possível montar a proposta.'; return; }''',
     r'''const dados = await resp.json().catch(function () { return {}; });
          if (!resp.ok) { titulo.textContent = 'Reorganizar atrasadas'; ajuda.textContent = ''; erro.textContent = dados.erro || mensagemDe(resp.status, 'montar a proposta'); return; }'''),
    ('templates/tarefas.html',
     r'''const dados = await resp.json();
          if (!resp.ok) {
            erro.textContent = dados.erro || 'Não foi possível reorganizar.';''',
     r'''const dados = await resp.json().catch(function () { return {}; });
          if (!resp.ok) {
            erro.textContent = dados.erro || mensagemDe(resp.status, 'reorganizar');'''),
)

PRE_REQUISITOS = (
    ("db.py", "[REAGENDAMENTO]", "o pacote 'conflito e reagendamento' (sem ele, adiar uma tarefa pode responder 'não encontrada')"),
    ("app.py", "def _confirmou_conflito_passos(", "o pacote 'conflito e reagendamento'"),
    ("decisao.py", "reservas=None", "o pacote 'aprendizado aplicado'"),
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
    ap = argparse.ArgumentParser(description="Acrescenta o botão Reorganizar atrasadas à tela de Tarefas.")
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
        ambiguo = [antes for arq_c, antes, _ in CORRECOES if arq_c == rel and texto.count(antes) > 1]
        if ambiguo:
            problemas.append(f"{rel}: um trecho a corrigir aparece mais de uma vez.")
            continue
        corrigido = False
        for arq_c, errado, certo in CORRECOES:
            if arq_c == rel and errado in texto:
                texto = texto.replace(errado, certo)
                corrigido = True
        if marca in texto and all(depois in texto for _, _, depois in trocas):
            if corrigido:
                print(f"-> {rel}: correção do token CSRF da janela (a versão anterior deste pacote dava erro 400 ao clicar)")
                plano.append((arquivo, texto, crlf))
            else:
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
        print("\nNada foi alterado. Para aplicar:  python atualizar_reorganizar_atrasadas.py --aplicar")
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
