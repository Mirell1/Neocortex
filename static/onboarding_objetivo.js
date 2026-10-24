/*
 * NEOCORTEX — onboarding_objetivo.js
 *
 * Passo OPCIONAL de objetivo do onboarding, carregado DEPOIS do onboarding.js:
 *   - sugestões prontas a partir das áreas que a pessoa escolheu ("O que você gostaria de organizar melhor?")
 *   - título curto (até 80 caracteres) e detalhes (até 300, opcional)
 *   - opção "quero ajuda para dividir em passos": depois do cadastro, a tela de Objetivos abre a prévia dos passos e
 *     PERGUNTA o prazo ali (na janela "Duas perguntas rápidas"), para aliviar o onboarding
 *
 * Ele se liga ao fluxo em tempo de execução (cria a pergunta "objetivo" antes da "personalizacao", ajusta o contador e
 * desenha o próprio formulário), então o onboarding.js não precisa ser editado. Se a equipe preferir, este conteúdo pode
 * ser movido para dentro do onboarding.js.
 *
 * PASSO ANTIGO: se o fluxo tiver o passo "Quais objetivos você quer alcançar?" (tipo lista_objetivos, id "objetivos"), este módulo o
 * RETIRA do fluxo, porque o passo novo cobre o mesmo assunto. O passo antigo só guardava o objetivo se a pessoa clicasse em
 * "+ Adicionar objetivo"; quem digitava e apertava Continuar perdia o texto. Para MANTER o passo antigo, troque
 * REMOVER_PASSO_ANTIGO para false logo abaixo (os dois ficam no fluxo).
 *
 * Resposta guardada em state.answers.objetivo:  { titulo, detalhes, fragmentar }  (só as chaves preenchidas)
 */
(function () {
  'use strict';
  if (window.__ncObjetivoOnboarding) return;
  if (typeof onboardingFlow === 'undefined' || typeof state === 'undefined' || typeof els === 'undefined' || typeof renderQuestion !== 'function') {
    if (window.console) console.warn('[objetivo] o onboarding.js não foi encontrado: o passo de objetivo não foi ativado.');
    return;
  }
  window.__ncObjetivoOnboarding = true;

  var REMOVER_PASSO_ANTIGO = true;
  var MAX_TITULO = 80;
  var MAX_DETALHES = 300;

  // Ideias por área (os valores são os da pergunta "areas_melhoria"). Títulos curtos, no jeito de um objetivo de verdade.
  var SUGESTOES = {
    estudos: ['Organizar minha rotina de estudos', 'Me preparar para as próximas provas', 'Terminar um curso ou certificação'],
    trabalho: ['Organizar minhas tarefas do trabalho', 'Entregar um projeto no prazo', 'Parar de deixar tudo para a última hora'],
    vida_pessoal: ['Criar uma rotina que caiba na minha semana', 'Reservar um tempo para mim todo dia', 'Cuidar melhor das tarefas de casa']
  };

  // ---------------------------------------------------------------- pergunta e ligações do fluxo
  onboardingFlow.objetivo = {
    id: 'objetivo',
    type: 'objetivo',
    title: 'Tem um objetivo que você gostaria de começar agora?',
    description: 'Essa etapa é opcional. Ele aparece na aba Objetivos e você pode ajustar depois.',
    messageTitle: 'Um primeiro passo concreto.',
    message: 'Pode ser pequeno. Ter um objetivo seu já dá ao NEOCORTEX algo para organizar com você.',
    optional: true,
    next: onboardingFlow.personalizacao ? 'personalizacao' : 'fim'
  };

  // retira o passo antigo (lista de objetivos) e faz quem apontava para ele apontar para o passo novo
  var relinkadasDoAntigo = 0;
  if (REMOVER_PASSO_ANTIGO && onboardingFlow.objetivos && onboardingFlow.objetivos.type === 'lista_objetivos') {
    Object.keys(onboardingFlow).forEach(function (id) {
      if (id === 'objetivos' || id === 'objetivo') return;
      var q = onboardingFlow[id];
      if (q.next === 'objetivos') { q.next = 'objetivo'; relinkadasDoAntigo += 1; }
      if (q.nextByValue) Object.keys(q.nextByValue).forEach(function (v) { if (q.nextByValue[v] === 'objetivos') { q.nextByValue[v] = 'objetivo'; relinkadasDoAntigo += 1; } });
      (q.options || []).forEach(function (o) { if (o.next === 'objetivos') { o.next = 'objetivo'; relinkadasDoAntigo += 1; } });
    });
    delete onboardingFlow.objetivos;
    if (typeof progressSequence !== 'undefined') { var pos0; while ((pos0 = progressSequence.indexOf('objetivos')) >= 0) progressSequence.splice(pos0, 1); }
    delete state.answers.objetivos;                                              // sobra de um cadastro anterior no mesmo navegador
    if (Array.isArray(state.history)) state.history = state.history.filter(function (id) { return id !== 'objetivos'; });
    if (state.currentQuestionId === 'objetivos') state.currentQuestionId = 'objetivo';
  }

  (function ligar() {
    var destino = onboardingFlow.objetivo.next;
    var ligadas = relinkadasDoAntigo;
    Object.keys(onboardingFlow).forEach(function (id) {
      if (id === 'objetivo') return;
      var q = onboardingFlow[id];
      if (q.next === destino) { q.next = 'objetivo'; ligadas += 1; }
      if (q.nextByValue) Object.keys(q.nextByValue).forEach(function (v) { if (q.nextByValue[v] === destino) { q.nextByValue[v] = 'objetivo'; ligadas += 1; } });
      (q.options || []).forEach(function (o) { if (o.next === destino) { o.next = 'objetivo'; ligadas += 1; } });
    });
    if (!ligadas && window.console) console.warn('[objetivo] não achei a pergunta que antecede "' + destino + '": o passo de objetivo não ficou ligado ao fluxo.');
  })();

  if (typeof progressSequence !== 'undefined' && progressSequence.indexOf('objetivo') < 0) {   // o contador "X de N" estima o total por esta lista
    var pos = progressSequence.indexOf(onboardingFlow.objetivo.next);
    progressSequence.splice(pos >= 0 ? pos : progressSequence.length, 0, 'objetivo');
  }

  // ---------------------------------------------------------------- estilo (tudo com prefixo onb-obj, não mexe no resto)
  var css = [
    '.onb-obj { display: grid; gap: 20px; }',
    '.onb-obj-rotulo { margin: 0 0 8px; font-size: 13px; font-weight: 700; color: var(--nc-text2, #64748B); }',
    '.onb-obj-chips { display: flex; flex-wrap: wrap; gap: 8px; }',
    '.onb-obj-chip { min-height: 40px; padding: 8px 14px; border-radius: 999px; border: 1.5px solid var(--nc-border, #E2E5EC); background: var(--nc-surface, #FFFFFF);',
    '  color: var(--nc-text, #0F172A); font: inherit; font-size: 14px; font-weight: 600; text-align: left; cursor: pointer; }',
    '.onb-obj-chip:hover { border-color: var(--nc-blue, #2563EB); }',
    '.onb-obj-chip[aria-pressed="true"] { background: rgba(37,99,235,.08); border-color: var(--nc-blue, #2563EB); color: #1D4ED8; }',
    '.onb-obj-cabeca { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 6px; }',
    '.onb-obj label.onb-obj-label { font-size: 14px; font-weight: 700; color: var(--nc-text, #0F172A); }',
    '.onb-obj-opcional { font-weight: 500; color: var(--nc-text2, #64748B); }',
    '.onb-obj-contador { font-size: 12px; font-weight: 600; color: var(--nc-text2, #64748B); }',
    '.onb-obj input[type="text"], .onb-obj textarea { display: block; width: 100%; box-sizing: border-box; padding: 12px 14px;',
    '  border: 1.5px solid var(--nc-border, #E2E5EC); border-radius: 12px; background: var(--nc-surface, #FFFFFF); color: var(--nc-text, #0F172A); font: inherit; font-size: 15px; }',
    '.onb-obj textarea { min-height: 84px; resize: vertical; line-height: 1.5; }',
    '.onb-obj input:focus-visible, .onb-obj textarea:focus-visible { outline: none; border-color: var(--nc-blue, #2563EB); box-shadow: 0 0 0 3px rgba(37,99,235,.18); }',
    '.onb-obj-chip:focus-visible, .onb-obj-check:focus-within { outline: 3px solid rgba(37,99,235,.35); outline-offset: 2px; }',
    '.onb-obj-check { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border: 1.5px solid var(--nc-border, #E2E5EC); border-radius: 14px; background: var(--nc-surface, #FFFFFF); cursor: pointer; }',
    '.onb-obj-check input { flex: none; width: 20px; height: 20px; margin: 2px 0 0; accent-color: var(--nc-blue, #2563EB); }',
    '.onb-obj-check strong { display: block; font-size: 15px; color: var(--nc-text, #0F172A); }',
    '.onb-obj-check small { display: block; margin-top: 4px; font-size: 13px; line-height: 1.45; font-weight: 500; color: var(--nc-text2, #64748B); }',
    '.onb-obj-aviso { margin: 0; min-height: 20px; font-size: 13px; font-weight: 600; color: #B45309; }',
    '.onb-obj-aviso.info { color: var(--nc-text2, #64748B); }'
  ].join('\n');
  var estilo = document.createElement('style');
  estilo.setAttribute('data-onb-objetivo', '');
  estilo.textContent = css;
  document.head.appendChild(estilo);

  // ---------------------------------------------------------------- utilitários
  var NOMES_AREAS = { estudos: 'estudos', trabalho: 'trabalho', vida_pessoal: 'vida pessoal' };

  // "estudos, trabalho e vida pessoal": deixa visível de onde vêm as ideias (da pergunta "O que você gostaria de organizar melhor?")
  function textoDasAreas() {
    var areas = state.answers && state.answers.areas_melhoria;
    if (!Array.isArray(areas)) return '';
    var nomes = areas.filter(function (a) { return NOMES_AREAS[a]; }).map(function (a) { return NOMES_AREAS[a]; });
    if (!nomes.length) return '';
    var ultimo = nomes.pop();
    return nomes.length ? nomes.join(', ') + ' e ' + ultimo : ultimo;
  }

  function sugestoesDasAreas() {
    var areas = state.answers && state.answers.areas_melhoria;
    if (!Array.isArray(areas)) return [];
    var listas = areas.filter(function (a) { return SUGESTOES[a]; }).map(function (a) { return SUGESTOES[a]; });
    var saida = [];
    for (var rodada = 0; saida.length < 3 && rodada < 3; rodada += 1) {
      for (var i = 0; i < listas.length && saida.length < 3; i += 1) {
        var item = listas[i][rodada];
        if (item && saida.indexOf(item) < 0) saida.push(item);
      }
    }
    return saida;
  }

  function criar(tag, atributos, texto) {
    var el = document.createElement(tag);
    Object.keys(atributos || {}).forEach(function (k) { el.setAttribute(k, atributos[k]); });
    if (texto) el.textContent = texto;
    return el;
  }

  // ---------------------------------------------------------------- desenho do passo
  function montar() {
    var anterior = state.answers.objetivo;
    if (typeof anterior === 'string') anterior = { titulo: anterior };   // versão antiga do passo guardava só o texto
    anterior = anterior && typeof anterior === 'object' ? anterior : {};

    var raiz = criar('div', { 'class': 'onb-obj', id: 'onbObjetivo' });
    var sugestoes = sugestoesDasAreas();
    var chips = [];
    if (sugestoes.length) {
      var bloco = criar('div');
      var areasTxt = textoDasAreas();
      bloco.appendChild(criar('p', { 'class': 'onb-obj-rotulo', id: 'onbObjSugRotulo' }, areasTxt ? 'Ideias para ' + areasTxt + ' (toque para usar)' : 'Ideias para começar (toque para usar)'));
      var grupo = criar('div', { 'class': 'onb-obj-chips', role: 'group', 'aria-labelledby': 'onbObjSugRotulo' });
      sugestoes.forEach(function (texto) {
        var chip = criar('button', { type: 'button', 'class': 'onb-obj-chip', 'aria-pressed': 'false' }, texto);
        chips.push(chip);
        grupo.appendChild(chip);
      });
      bloco.appendChild(grupo);
      raiz.appendChild(bloco);
    }

    var campoTitulo = criar('div');
    var cabecaT = criar('div', { 'class': 'onb-obj-cabeca' });
    cabecaT.appendChild(criar('label', { 'class': 'onb-obj-label', 'for': 'onbObjTitulo' }, 'Em poucas palavras, qual é o objetivo?'));
    var contador = criar('span', { 'class': 'onb-obj-contador', 'aria-hidden': 'true' }, '0/' + MAX_TITULO);
    cabecaT.appendChild(contador);
    var titulo = criar('input', { type: 'text', id: 'onbObjTitulo', maxlength: String(MAX_TITULO), autocomplete: 'off', placeholder: 'Ex.: terminar o TCC' });
    campoTitulo.appendChild(cabecaT); campoTitulo.appendChild(titulo); raiz.appendChild(campoTitulo);

    var campoDet = criar('div');
    var cabecaD = criar('div', { 'class': 'onb-obj-cabeca' });
    var rotD = criar('label', { 'class': 'onb-obj-label', 'for': 'onbObjDetalhes' }, 'Quer contar mais? ');
    rotD.appendChild(criar('span', { 'class': 'onb-obj-opcional' }, '(opcional)'));
    cabecaD.appendChild(rotD);
    var detalhes = criar('textarea', { id: 'onbObjDetalhes', rows: '3', maxlength: String(MAX_DETALHES), placeholder: 'Pode escrever do seu jeito: por que isso importa agora, o que costuma travar…' });
    campoDet.appendChild(cabecaD); campoDet.appendChild(detalhes); raiz.appendChild(campoDet);

    var rotuloCheck = criar('label', { 'class': 'onb-obj-check' });
    var fragmentar = criar('input', { type: 'checkbox', id: 'onbObjFragmentar', 'aria-describedby': 'onbObjFragDica' });
    var textoCheck = criar('span');
    textoCheck.appendChild(criar('strong', {}, 'Quero ajuda para dividir em passos pequenos'));
    textoCheck.appendChild(criar('small', { id: 'onbObjFragDica' }, 'Depois do cadastro, eu pergunto até quando e mostro uma sugestão de passos para você revisar antes de salvar.'));
    rotuloCheck.appendChild(fragmentar); rotuloCheck.appendChild(textoCheck); raiz.appendChild(rotuloCheck);

    var aviso = criar('p', { 'class': 'onb-obj-aviso', id: 'onbObjAviso', role: 'status', 'aria-live': 'polite' });
    raiz.appendChild(aviso);

    titulo.value = typeof anterior.titulo === 'string' ? anterior.titulo.slice(0, MAX_TITULO) : '';
    detalhes.value = typeof anterior.detalhes === 'string' ? anterior.detalhes.slice(0, MAX_DETALHES) : '';
    fragmentar.checked = anterior.fragmentar === true;

    function atualizar(origem) {
      var t = titulo.value.replace(/\s+/g, ' ').trim();
      var d = detalhes.value.trim();
      var f = fragmentar.checked;
      contador.textContent = titulo.value.length + '/' + MAX_TITULO;
      chips.forEach(function (c) { c.setAttribute('aria-pressed', c.textContent === t ? 'true' : 'false'); });

      var resposta = {};
      if (t) resposta.titulo = t;
      if (d) resposta.detalhes = d;
      if (f) resposta.fragmentar = true;
      if (Object.keys(resposta).length) state.answers.objetivo = resposta; else delete state.answers.objetivo;
      if (typeof saveState === 'function') saveState();

      var problema = '';
      if (!t && (d || f)) problema = 'Escreva o título curto para guardar o objetivo (ou apague os outros campos para pular).';

      aviso.textContent = problema;
      aviso.className = 'onb-obj-aviso';

      if (origem !== 'montagem' || problema) {
        els.continue.disabled = Boolean(problema);
        els.footerHint.textContent = problema ? 'Falta um ajuste para continuar.' : 'Pronto. Você pode continuar.';   // o mesmo texto que o motor usa nas outras perguntas
      }
    }

    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        titulo.value = chip.textContent;
        atualizar('chip');
        titulo.focus();
        try { titulo.setSelectionRange(titulo.value.length, titulo.value.length); } catch (e) { /* alguns navegadores não deixam */ }
        aviso.textContent = 'Título preenchido com a sugestão. Você pode mudar o texto.';
        aviso.className = 'onb-obj-aviso info';
      });
    });
    [titulo, detalhes].forEach(function (c) { c.addEventListener('input', function () { atualizar('digitando'); }); });
    fragmentar.addEventListener('change', function () { atualizar('digitando'); });

    els.custom.appendChild(raiz);
    atualizar('montagem');
  }

  // ---------------------------------------------------------------- liga o desenho ao motor do onboarding
  var renderOriginal = renderQuestion;
  renderQuestion = function () {
    renderOriginal.apply(this, arguments);
    var pergunta = typeof getQuestion === 'function' ? getQuestion() : null;
    if (pergunta && pergunta.type === 'objetivo') montar();
  };

  // o onboarding.js já desenhou a primeira pergunta antes deste módulo carregar: redesenha para o contador "1 de N" já contar o passo novo
  try { renderQuestion(); } catch (e) { /* o próximo avanço já usa o contador certo */ }
})();
