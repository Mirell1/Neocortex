"""
NEOCORTEX - atualizar_edicao_dos_passos.py

A prévia dos passos de um objetivo (a lista "Proposta — N fragmentos") passa a ser EDITÁVEL antes de ir para a agenda:

  - cada passo tem título, dia e hora que a pessoa pode ajustar, e um botão para remover o passo
  - confere tudo antes de enviar (título, dia, hora, data de hoje em diante) e mostra o problema junto do botão
  - erro vindo do servidor aparece na própria janela (em vez de um alerta do navegador)
  - os textos entram na tela como TEXTO (nunca como HTML), então um título estranho não vira código
  - a duração de cada passo (30 ou 60 minutos) continua a que foi sugerida

Mexe só em templates/objetivos.html. Pré-requisitos: o lote 1 e o pacote do prazo na janela já aplicados.
O módulo static/onboarding_objetivo.js do mesmo pacote (com o texto que mostra de quais áreas vêm as ideias) é só extrair por cima.

Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_edicao_dos_passos.py            # só mostra
    python atualizar_edicao_dos_passos.py --aplicar  # grava (cópia .bak; confere a sintaxe antes)

Rodar de novo é seguro. Se não reconhecer o trecho, NÃO mexe no arquivo e explica.
"""
import argparse
import difflib
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

FUNCAO_NOVA = r'''  function mostrarPreviaFragmentos(propostas, aviso) {
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const pad = (n) => String(n).padStart(2, '0');
    const hoje = ((d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()))(new Date());   // data local, não UTC
    document.getElementById('fragAutoPerguntas').classList.add('hidden');
    const preview = document.getElementById('fragAutoPreview');
    preview.classList.remove('hidden');

    preview.innerHTML = `
      <h3 id="fragAutoTitulo" style="margin:0 0 6px;font-size:16px;font-weight:800;color:var(--nc-text);"></h3>
      <p style="margin:0 0 12px;font-size:13px;line-height:1.5;color:var(--nc-text2);">Ajuste o título, o dia e a hora de cada passo, ou remova o que não quiser. Confira se o horário não bate com outro compromisso.</p>
      ${aviso ? `<p role="status" style="margin:0 0 12px;font-size:13px;line-height:1.5;font-weight:600;color:#B45309;">${esc(aviso)}</p>` : ''}
      <ul id="fragAutoLista" style="list-style:none;margin:0 0 12px;padding:0;max-height:300px;overflow-y:auto;"></ul>
      <p id="fragAutoErro" role="alert" style="margin:0 0 12px;min-height:18px;font-size:13px;line-height:1.4;font-weight:600;color:#B91C1C;"></p>
      <button type="button" id="btnConfirmarFragmentos" class="btn-primary" style="width:100%;height:48px;margin-bottom:10px;">Adicionar à agenda</button>
      <button type="button" class="btn-outline" style="width:100%;height:48px;" onclick="document.getElementById('modalFragAuto').classList.add('hidden')">Cancelar</button>
    `;

    const lista = document.getElementById('fragAutoLista');
    const erro = document.getElementById('fragAutoErro');
    const estilo = 'height:40px;padding:0 10px;border:1.5px solid var(--nc-border);border-radius:10px;background:var(--nc-surface, #fff);color:var(--nc-text);font:inherit;font-size:13px;box-sizing:border-box;';

    function atualizarCabecalho() {
      const n = lista.children.length;
      document.getElementById('fragAutoTitulo').textContent = 'Proposta — ' + n + (n === 1 ? ' fragmento' : ' fragmentos');
      document.getElementById('btnConfirmarFragmentos').disabled = n === 0;
      [...lista.children].forEach((li, i) => {
        li.querySelector('[data-campo="titulo"]').setAttribute('aria-label', 'Título do passo ' + (i + 1));
        li.querySelector('[data-campo="data"]').setAttribute('aria-label', 'Dia do passo ' + (i + 1));
        li.querySelector('[data-campo="hora"]').setAttribute('aria-label', 'Hora do passo ' + (i + 1));
        li.querySelector('[data-campo="remover"]').setAttribute('aria-label', 'Remover o passo ' + (i + 1));
      });
      if (n === 0) erro.textContent = 'Todos os passos foram removidos. Use Cancelar para voltar.';
    }

    function criarCampo(tipo, campo, valor, extra) {
      const c = document.createElement('input');
      c.type = tipo;
      c.value = valor;               // como valor (texto), nunca como HTML
      c.dataset.campo = campo;
      c.style.cssText = estilo + extra;
      return c;
    }

    propostas.forEach((p) => {
      const partes = String(p.inicio).split('T');
      const li = document.createElement('li');
      li.dataset.duracao = String(p.duracao_min || 30);
      li.style.cssText = 'padding:12px 0;border-bottom:1px solid var(--nc-border);';
      const titulo = criarCampo('text', 'titulo', p.titulo, 'width:100%;font-weight:600;margin-bottom:8px;');
      titulo.maxLength = 200;
      const linha = document.createElement('div');
      linha.style.cssText = 'display:flex;gap:8px;align-items:center;';
      const dia = criarCampo('date', 'data', (partes[0] || '').slice(0, 10), 'flex:1;min-width:0;');
      dia.min = hoje;
      const hora = criarCampo('time', 'hora', (partes[1] || '09:00').slice(0, 5), 'width:128px;flex:none;');   // largo o bastante para o relógio de 12 horas (10:00 AM)
      const duracao = document.createElement('span');
      duracao.textContent = (p.duracao_min || 30) + ' min';
      duracao.style.cssText = 'font-size:12px;font-weight:600;color:var(--nc-text2);white-space:nowrap;';
      const remover = document.createElement('button');
      remover.type = 'button';
      remover.dataset.campo = 'remover';
      remover.textContent = '✕';
      remover.style.cssText = 'width:40px;height:40px;flex:none;border:1.5px solid var(--nc-border);border-radius:10px;background:transparent;color:var(--nc-text2);font-size:14px;font-weight:700;cursor:pointer;';
      remover.addEventListener('click', () => { li.remove(); erro.textContent = ''; atualizarCabecalho(); });
      linha.append(dia, hora, duracao, remover);
      li.append(titulo, linha);
      lista.appendChild(li);
    });
    atualizarCabecalho();

    document.getElementById('btnConfirmarFragmentos').addEventListener('click', async function () {
      const editados = [];
      const linhas = [...lista.children];
      for (let i = 0; i < linhas.length; i++) {
        const li = linhas[i], t = li.querySelector('[data-campo="titulo"]'), d = li.querySelector('[data-campo="data"]'), h = li.querySelector('[data-campo="hora"]');
        let motivo = '', campo = null;
        if (!t.value.trim()) { motivo = 'escreva um título.'; campo = t; }
        else if (!d.value || !h.value) { motivo = 'escolha o dia e a hora.'; campo = d.value ? h : d; }
        else if (d.value < hoje) { motivo = 'escolha uma data de hoje em diante.'; campo = d; }
        if (motivo) { erro.textContent = 'Passo ' + (i + 1) + ': ' + motivo; campo.focus(); return; }
        editados.push({ titulo: t.value.trim(), inicio: d.value + 'T' + h.value, duracao_min: Number(li.dataset.duracao) || 30 });
      }
      if (!editados.length) return;
      editados.sort((a, b) => (a.inicio < b.inicio ? -1 : a.inicio > b.inicio ? 1 : 0));
      erro.textContent = '';

      const botao = this;
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
      botao.disabled = true;
      botao.textContent = 'Adicionando...';

      let url, body;
      const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken };
      if (fragAutoContexto.tipo === 'novo') {
        url = '/objetivos/novo/fragmentar/confirmar';
        body = JSON.stringify({ titulo_objetivo: fragAutoContexto.titulo, prazo: fragAutoContexto.prazo, propostas: editados });
      } else {
        url = `/objetivos/${fragAutoContexto.idObjetivo}/fragmentar/confirmar`
          + (fragAutoContexto.prazoEscolhido ? '?prazo=' + encodeURIComponent(fragAutoContexto.prazoEscolhido) : '');
        body = JSON.stringify(editados);
      }

      try {
        const resp = await fetch(url, { method: 'POST', headers, body });
        const dados = await resp.json();
        if (!resp.ok) { erro.textContent = dados.erro || 'Não foi possível adicionar os passos.'; botao.disabled = false; botao.textContent = 'Adicionar à agenda'; return; }
        if (dados.redirect) window.location.href = dados.redirect;
      } catch (e) {
        erro.textContent = 'Não foi possível conectar ao servidor.';
        botao.disabled = false;
        botao.textContent = 'Adicionar à agenda';
      }
    });
  }
</script>
'''

RE_FUNCAO = re.compile(r"  function mostrarPreviaFragmentos\(propostas, aviso\) \{\n.*?\n  \}\n</script>\n", re.S)


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
    if 'id="fragAutoLista"' in texto:
        return None, "objetivos.html: a prévia já é editável (nada a fazer)."
    faltas = []
    if "fragAutoPrazoBloco" not in texto:
        faltas.append("o pacote do prazo na janela (atualizar_prazo_na_janela.py)")
    if "const esc = (s)" not in texto:
        faltas.append("o lote 1 (corrigir_lote1.py)")
    if faltas:
        return None, "objetivos.html: falta aplicar antes " + " e ".join(faltas) + ". O arquivo ficou como estava."
    if len(RE_FUNCAO.findall(texto)) != 1:
        return None, ("objetivos.html: NÃO reconheci a função mostrarPreviaFragmentos (a versão que eu conheço termina logo antes de </script>).\n"
                      "  O arquivo ficou como estava. Me mande o arquivo e eu ajusto.")
    return RE_FUNCAO.sub(lambda m: FUNCAO_NOVA, texto, count=1), "objetivos.html: a prévia dos passos agora é editável (título, dia e hora, e remover)."


def main():
    ap = argparse.ArgumentParser(description="Torna editável a prévia dos passos de um objetivo.")
    ap.add_argument("--aplicar", action="store_true", help="grava a mudança (sem isso, só mostra)")
    args = ap.parse_args()
    arquivo = RAIZ / "templates" / "objetivos.html"
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    if not arquivo.exists():
        print("templates/objetivos.html não existe.")
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
    linhas = list(difflib.unified_diff(texto.splitlines(), novo.splitlines(), "objetivos.html (atual)", "objetivos.html (novo)", lineterm="", n=0))
    print("\n".join(linhas[:30]) + (f"\n   ... (diff cortado: {len(linhas)} linhas)" if len(linhas) > 30 else ""))
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_edicao_dos_passos.py --aplicar")
        return 0
    copia = arquivo.with_name(arquivo.name + ".bak")
    n = 1
    while copia.exists():
        n += 1
        copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
    shutil.copy2(arquivo, copia)
    arquivo.write_bytes(gravar_texto(novo, crlf))
    print(f"\ngravado: templates/objetivos.html  (cópia do original: {copia.name})\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
