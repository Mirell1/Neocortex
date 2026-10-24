/* ============================================================
   NEOCORTEX - Semana temática  ->  static/semana_tematica.js
   Desenha os 7 dias da semana (segunda a domingo) no visual do tema:
     cafeteria  -> prateleira de xícaras que enchem
     campeonato -> escalação: uma camisa por dia, domingo no gol
     papelaria  -> planner: uma folha por dia presa com fita, um quadradinho por tarefa
     padrao     -> trilha de dias: uma bolinha por tarefa; a conexão com o dia
                   seguinte só acende quando TODAS as tarefas do dia foram concluídas
   Usado pela tela inicial (dados do servidor) e pelo calendário
   (dados da /api/eventos). Cada dia é um RESUMO (concluídas de
   planejadas), nunca uma tarefa desenhada: funciona com 0 ou 15 tarefas.

   Uso:
     NCSemana.render(elemento, 'cafeteria', dias, { aoClicar: function (dataISO) {...} })
     dias = [{ data: 'AAAA-MM-DD', total: 3, concluidas: 2 }, ...]   (7 itens, de segunda a domingo)
   ============================================================ */
(function () {
  'use strict';

  const NOMES = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  const NOMES_LONGOS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function chave(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function paraData(k) { const p = k.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function plural(n, um, varios) { return n + ' ' + (n === 1 ? um : varios); }

  /* Estado de cada dia: sempre com TEXTO, nunca só cor. Nada soa como derrota. */
  function descrever(dia, hojeK) {
    const d = paraData(dia.data);
    const t = dia.total || 0, c = dia.concluidas || 0;
    const info = {
      data: dia.data, total: t, concluidas: c,
      nome: NOMES[d.getDay()], nomeLongo: NOMES_LONGOS[d.getDay()],
      dataCurta: pad(d.getDate()) + '/' + pad(d.getMonth() + 1),
      hoje: dia.data === hojeK, futuro: dia.data > hojeK,
    };
    if (info.futuro) {
      info.estado = t ? 'planejado' : 'livre';
      info.resumo = t ? plural(t, 'planejada', 'planejadas') : 'sem tarefas';
      info.nivel = 0;
    } else if (!t) {
      info.estado = 'livre'; info.resumo = 'sem tarefas'; info.nivel = 0;
    } else {
      info.estado = info.hoje ? 'hoje' : (c === t ? 'feito' : (c ? 'parcial' : 'aberto'));
      info.resumo = c + ' de ' + t;
      info.nivel = c / t;
    }
    return info;
  }

  const ROTULOS = {
    papelaria: { feito: 'feito', parcial: 'em andamento', hoje: 'hoje', aberto: 'em aberto', planejado: 'planejado', livre: 'sem tarefas' },
    padrao: { feito: 'dia conectado ✓', parcial: 'em andamento', hoje: 'hoje', aberto: 'em aberto', planejado: 'planejado', livre: 'sem tarefas' },
    cafeteria: { feito: 'cheia', parcial: 'pela metade', hoje: 'hoje', aberto: 'em aberto', planejado: 'a preparar', livre: 'sem tarefas' },
    campeonato: { feito: 'concluído', parcial: 'em andamento', hoje: 'hoje', aberto: 'em aberto', planejado: 'escalado', livre: 'sem tarefas' },
  };

  function rotuloAcessivel(i, tema) {
    return i.nomeLongo + ', ' + i.dataCurta + ': ' + (i.estado === 'livre' ? 'sem tarefas' :
      (i.futuro ? plural(i.total, 'tarefa planejada', 'tarefas planejadas') : i.concluidas + ' de ' + i.total + ' concluídas')) +
      (i.hoje ? ', hoje' : '') + '. Abrir o dia.';
  }

  /* ---------- CAFETERIA: prateleira ---------- */
  function xicara(i, idx, uid) {
    const altura = 34 * i.nivel;
    const vapor = i.estado === 'feito'
      ? '<path class="vapor" d="M24 14 Q20 9 24 4 M34 14 Q30 9 34 4"/>' : '';
    return '<svg viewBox="0 0 64 70" width="64" height="70" aria-hidden="true">' + vapor +
      '<path class="alca" d="M50 30 Q62 30 60 42 Q58 52 48 51"/>' +
      '<clipPath id="nc-xc-' + uid + '-' + idx + '"><path d="M8 20 L52 20 L48 54 Q47 60 40 60 L20 60 Q13 60 12 54 Z"/></clipPath>' +
      '<rect class="cafe" x="0" y="' + (60 - altura).toFixed(1) + '" width="64" height="' + altura.toFixed(1) + '" clip-path="url(#nc-xc-' + uid + '-' + idx + ')"/>' +
      '<path class="copo" d="M8 20 L52 20 L48 54 Q47 60 40 60 L20 60 Q13 60 12 54 Z"/>' +
      '<ellipse class="pires" cx="30" cy="64" rx="26" ry="4.5"/></svg>';
  }

  function prateleira(infos, uid) {
    return '<ul class="nc-prateleira">' + infos.map(function (i, idx) {
      return '<li><button type="button" class="nc-dia-xicara estado-' + i.estado + (i.hoje ? ' is-hoje' : '') + '" data-dia="' + i.data + '" aria-label="' + esc(rotuloAcessivel(i)) + '">' +
        xicara(i, idx, uid) +
        '<span class="dia">' + i.nome + ' <small>' + i.dataCurta + '</small></span>' +
        '<span class="resumo">' + esc(i.resumo) + '</span>' +
        '<span class="estado">' + ROTULOS.cafeteria[i.estado] + '</span></button></li>';
    }).join('') + '</ul>';
  }

  /* ---------- CAMPEONATO: escalação ---------- */
  // segunda a quarta numa linha, quinta a sábado na outra, domingo no gol
  const POSICOES = { 1: [36, 20], 2: [36, 50], 3: [36, 80], 4: [70, 20], 5: [70, 50], 6: [70, 80], 0: [9, 50] };
  const GRUPO = { 1: 'grupo-a', 2: 'grupo-a', 3: 'grupo-a', 4: 'grupo-b', 5: 'grupo-b', 6: 'grupo-b', 0: 'grupo-gol' };
  const ICONES = {
    feito: '<path d="M13 21 L18 26 L27 15" class="traco"/>',
    parcial: '<circle cx="20" cy="21" r="7" class="anel"/><path d="M20 14 A7 7 0 0 1 20 28 Z" class="cheio"/>',
    hoje: '<circle cx="20" cy="21" r="7" class="anel"/><path d="M20 14 A7 7 0 0 1 27 21 L20 21 Z" class="cheio"/>',
    aberto: '<circle cx="20" cy="21" r="7" class="anel"/>',
    planejado: '<circle cx="20" cy="21" r="7" class="anel tracejado"/>',
    livre: '<text x="20" y="26" text-anchor="middle" class="letra">z</text>',
  };

  function escalacao(infos) {
    const camisas = infos.map(function (i) {
      const dow = paraData(i.data).getDay();
      const pos = POSICOES[dow];
      return '<button type="button" class="nc-camisa ' + GRUPO[dow] + ' estado-' + i.estado + (i.hoje ? ' is-hoje' : '') + '" data-dia="' + i.data + '" ' +
        'style="left:' + pos[0] + '%;top:' + pos[1] + '%;" aria-label="' + esc(rotuloAcessivel(i)) + '">' +
        '<svg viewBox="0 0 40 36" width="46" height="42" aria-hidden="true">' +
        '<path class="tecido" d="M12 3 L6 6 L1 14 L7 18 L9 15 L9 34 L31 34 L31 15 L33 18 L39 14 L34 6 L28 3 Q20 9 12 3 Z"/>' +
        ICONES[i.estado] + '</svg>' +
        '<span class="dia">' + i.nome + ' <small>' + i.dataCurta + '</small></span>' +
        '<span class="resumo">' + esc(i.resumo) + '</span></button>';
    }).join('');
    return '<div class="nc-escalacao-rolagem"><div class="nc-escalacao" role="group" aria-label="Escalação da semana: uma camisa por dia">' +
      '<span class="linha borda" aria-hidden="true"></span><span class="linha meio" aria-hidden="true"></span>' +
      '<span class="linha circulo" aria-hidden="true"></span><span class="linha area esq" aria-hidden="true"></span>' +
      '<span class="linha area dir" aria-hidden="true"></span>' + camisas + '</div></div>' +
      '<ul class="nc-escalacao-legenda">' +
      '<li><span class="cor grupo-a"></span>Seg a Qua</li><li><span class="cor grupo-b"></span>Qui a Sáb</li>' +
      '<li><span class="cor grupo-gol"></span>Domingo no gol</li>' +
      '<li>✓ concluído · meia-lua em andamento · tracejado escalado · z livre</li></ul>';
  }

  /* ---------- PADRÃO: trilha de dias (rede) ---------- */
  const MAX_BOLINHAS = 8;

  function completo(i) { return !i.futuro && i.total > 0 && i.concluidas === i.total; }

  function trilha(infos) {
    const partes = [];
    infos.forEach(function (i, idx) {
      let bolinhas = '';
      for (let k = 0; k < Math.min(i.total, MAX_BOLINHAS); k++) {
        const tipo = i.futuro ? 'planejada' : (k < i.concluidas ? 'feita' : 'afazer');
        bolinhas += '<span class="bolinha ' + tipo + '"></span>';
      }
      if (i.total > MAX_BOLINHAS) bolinhas += '<span class="mais">+' + (i.total - MAX_BOLINHAS) + '</span>';
      if (!i.total) bolinhas = '<span class="vazio">—</span>';

      // hoje: deixa explícito quanto falta, para ninguém achar que já terminou
      let resumo = i.resumo;
      if (i.hoje && i.total && i.concluidas < i.total) {
        const faltam = i.total - i.concluidas;
        resumo += ' · falta' + (faltam === 1 ? ' ' : 'm ') + faltam;
      }
      const est = completo(i) ? 'feito' : i.estado;

      partes.push('<button type="button" class="nc-dia-trilha estado-' + est + (i.hoje ? ' is-hoje' : '') + '" data-dia="' + i.data + '" aria-label="' + esc(rotuloAcessivel(i)) + '">' +
        '<span class="dia">' + i.nome + ' <small>' + i.dataCurta + '</small></span>' +
        '<span class="bolinhas" aria-hidden="true">' + bolinhas + '</span>' +
        '<span class="resumo">' + esc(resumo) + '</span>' +
        '<span class="estado">' + ROTULOS.padrao[est] + '</span></button>');
      if (idx < infos.length - 1) {
        partes.push('<span class="nc-conexao' + (completo(i) ? ' acesa' : '') + '" aria-hidden="true"></span>');
      }
    });
    return '<div class="nc-trilha-moldura"><div class="nc-trilha-rolagem"><div class="nc-trilha" role="group" aria-label="Rede da semana: um cartão por dia">' +
      partes.join('') + '</div></div>' +
      '<ul class="nc-trilha-legenda">' +
      '<li><span class="bolinha feita"></span>concluída</li><li><span class="bolinha afazer"></span>a fazer</li>' +
      '<li><span class="bolinha planejada"></span>planejada</li><li><span class="nc-conexao acesa"></span>dia conectado</li></ul></div>';
  }

  /* ---------- PAPELARIA: planner ---------- */
  const FITAS = ['fita-menta', 'fita-amarela', 'fita-coral', 'fita-lilas', 'fita-menta', 'fita-amarela', 'fita-lilas'];
  const ESTRELA = 'M20 2 L24.7 14.2 L37.7 14.6 L27.4 22.6 L31.1 35.1 L20 27.8 L8.9 35.1 L12.6 22.6 L2.3 14.6 L15.3 14.2 Z';

  function planner(infos) {
    return '<ul class="nc-planner">' + infos.map(function (i, idx) {
      let caixas = '';
      for (let k = 0; k < Math.min(i.total, MAX_BOLINHAS); k++) {
        caixas += '<span class="caixa ' + (i.futuro ? 'planejada' : (k < i.concluidas ? 'feita' : 'afazer')) + '"></span>';
      }
      if (i.total > MAX_BOLINHAS) caixas += '<span class="mais">+' + (i.total - MAX_BOLINHAS) + '</span>';
      const est = completo(i) ? 'feito' : i.estado;
      let resumo = i.resumo;
      if (i.hoje && i.total && i.concluidas < i.total) {
        const faltam = i.total - i.concluidas;
        resumo += ' · falta' + (faltam === 1 ? ' ' : 'm ') + faltam;
      }
      const adesivo = est === 'feito'
        ? '<svg class="adesivo" viewBox="0 0 40 40" aria-hidden="true"><path d="' + ESTRELA + '"/></svg>' : '';
      return '<li><button type="button" class="nc-folha estado-' + est + (i.hoje ? ' is-hoje' : '') + '" data-dia="' + i.data + '" aria-label="' + esc(rotuloAcessivel(i)) + '">' +
        '<span class="fita ' + FITAS[idx] + '" aria-hidden="true"></span>' +
        '<span class="dia">' + i.nome + '</span><span class="data">' + i.dataCurta + '</span>' +
        '<span class="caixas" aria-hidden="true">' + caixas + '</span>' +
        '<span class="resumo">' + esc(resumo) + '</span>' +
        '<span class="estado">' + ROTULOS.papelaria[est] + '</span>' + adesivo + '</button></li>';
    }).join('') + '</ul>';
  }

  let contador = 0;

  function render(el, tema, dias, opcoes) {
    if (!el || !dias || dias.length !== 7) return;
    opcoes = opcoes || {};
    const hojeK = chave(new Date());
    const infos = dias.map(function (d) { return descrever(d, hojeK); });
    const uid = 's' + (++contador);
    el.innerHTML = tema === 'campeonato' ? escalacao(infos)
      : tema === 'cafeteria' ? prateleira(infos, uid)
      : tema === 'papelaria' ? planner(infos)
      : trilha(infos);
    el.querySelectorAll('[data-dia]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (opcoes.aoClicar) opcoes.aoClicar(b.dataset.dia);
        else if (opcoes.urlDia) window.location.href = opcoes.urlDia + '?dia=' + b.dataset.dia;
      });
    });
  }

  /* Monta os 7 dias (segunda a domingo da semana de 'referencia') a partir de eventos da /api/eventos. */
  function diasDosEventos(eventos, referencia) {
    const r = new Date(referencia.getFullYear(), referencia.getMonth(), referencia.getDate());
    const segunda = new Date(r.getFullYear(), r.getMonth(), r.getDate() - ((r.getDay() + 6) % 7));
    const dias = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(segunda.getFullYear(), segunda.getMonth(), segunda.getDate() + i);
      dias.push({ data: chave(d), total: 0, concluidas: 0 });
    }
    const porChave = {};
    dias.forEach(function (d) { porChave[d.data] = d; });
    (eventos || []).forEach(function (e) {
      if (e.tipo !== 'tarefa' || e.status === 'cancelada') return;   // rotina e compromissos não contam
      const d = porChave[chave(new Date(e.inicio))];
      if (!d) return;
      d.total += 1;
      if (e.status === 'concluida') d.concluidas += 1;
    });
    return dias;
  }

  function segundaDa(referencia) {
    const r = new Date(referencia.getFullYear(), referencia.getMonth(), referencia.getDate());
    return new Date(r.getFullYear(), r.getMonth(), r.getDate() - ((r.getDay() + 6) % 7));
  }

  window.NCSemana = { render: render, diasDosEventos: diasDosEventos, segundaDa: segundaDa };
})();
