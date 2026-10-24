/*
 * NEOCORTEX — onboarding_acessibilidade.js
 *
 * Aplica NA HORA, ainda durante o cadastro, a preferência escolhida na pergunta "acessibilidade":
 *   fonte_grande    -> fonte maior (a mesma ampliação de 15% que o app usa)
 *   alto_contraste  -> alto contraste: o do app (common.css) + azul mais escuro, destaques sólidos e bordas firmes
 *   dislexia        -> fonte Lexend, com um pouco mais de espaço entre as letras
 *   padrao          -> volta à aparência normal
 *
 * Marca o <html> com data-fonte, data-contraste e data-tipografia (os mesmos atributos que o resto do app usa) e traz os estilos
 * que a página do onboarding precisa para mostrar o efeito. O servidor continua gravando a escolha ao concluir o cadastro; este
 * arquivo só antecipa o efeito visual. Carregado DEPOIS do onboarding.js (e do onboarding_objetivo.js).
 */
(function () {
  'use strict';
  if (window.__ncOnbAcessibilidade) return;
  if (typeof state === 'undefined' || typeof els === 'undefined' || typeof renderQuestion !== 'function' || !els.options) {
    if (window.console) console.warn('[acessibilidade] o onboarding.js não foi encontrado: a acessibilidade ao vivo não foi ativada.');
    return;
  }
  window.__ncOnbAcessibilidade = true;

  var PERGUNTA = 'acessibilidade';
  var PADRAO = { fonte: 'normal', contraste: 'normal', tipografia: 'padrao', aviso: 'Aparência padrão.' };
  var MODOS = {
    fonte_grande: { fonte: 'grande', contraste: 'normal', tipografia: 'padrao', aviso: 'Fonte maior ativada.' },
    alto_contraste: { fonte: 'normal', contraste: 'alto', tipografia: 'padrao', aviso: 'Alto contraste ativado.' },
    dislexia: { fonte: 'normal', contraste: 'normal', tipografia: 'dislexia', aviso: 'Fonte para dislexia ativada.' }
  };

  var css = [
    '/* fonte maior: a mesma ampliação (15%) que o app usa */',
    'html[data-fonte="grande"] { zoom: 1.15; }',
    '/* o zoom deixaria a página 15% mais alta que a janela (ela tem 100vh): compensa, para o botão Continuar não sair da tela */',
    'html[data-fonte="grande"] body, html[data-fonte="grande"] .onboarding-shell { height: calc(100vh / 1.15); min-height: calc(100vh / 1.15); }',
    '/* com o texto maior a pergunta pode não caber na janela: cabeçalho e rodapé ficam no lugar e só o conteúdo rola, então o botão Continuar nunca some */',
    'html[data-fonte="grande"] .onboarding-content { flex: 1 1 auto; min-height: 0; overflow-y: auto; }',
    '/* dislexia: Lexend e um respiro a mais entre as letras */',
    'html[data-tipografia="dislexia"] body, html[data-tipografia="dislexia"] button, html[data-tipografia="dislexia"] input, html[data-tipografia="dislexia"] textarea {',
    "  font-family: 'Lexend', 'Segoe UI', Arial, sans-serif; letter-spacing: 0.02em; }",
    '/* alto contraste: o common.css (que esta página já carrega) troca texto, fundo, superfície e borda para preto e branco; aqui entra o que ele NÃO cobre */',
    'html[data-contraste="alto"] { --nc-blue: #0B2E9E; }   /* o azul da marca (5,2:1) sobe para 10:1 */',
    'html[data-contraste="alto"] .onboarding-header { background: #0B1F5C; box-shadow: none; }',
    'html[data-contraste="alto"] .header-back { border-color: #FFFFFF; background: rgba(255,255,255,.18); }',
    'html[data-contraste="alto"] .onboarding-option { border-width: 2px; box-shadow: none; }',
    'html[data-contraste="alto"] .option-index { background: #E5E7EB; color: #000000; }',
    'html[data-contraste="alto"] .onboarding-option.selected { background: #0B2E9E; border-color: #0B2E9E; color: #FFFFFF; box-shadow: none; }',
    'html[data-contraste="alto"] .onboarding-option.selected .option-label, html[data-contraste="alto"] .onboarding-option.selected .option-description { color: #FFFFFF; }',
    'html[data-contraste="alto"] .selected .option-index { background: #FFFFFF; color: #0B2E9E; }',
    'html[data-contraste="alto"] .option-check { border-color: var(--nc-border); }',
    'html[data-contraste="alto"] .selected .option-check { background: #FFFFFF; border-color: #FFFFFF; color: #0B2E9E; }',
    'html[data-contraste="alto"] .neo-caption, html[data-contraste="alto"] .footer-hint { color: var(--nc-text2); }',
    'html[data-contraste="alto"] .validation-message { color: #991B1B; }',
    'html[data-contraste="alto"] .onboarding-continue { background: #0B2E9E; box-shadow: none; }',
    'html[data-contraste="alto"] .onboarding-continue:disabled { background: #374151; color: #FFFFFF; opacity: 1; }',
    'html[data-contraste="alto"] .onb-obj-chip[aria-pressed="true"] { background: #0B2E9E; border-color: #0B2E9E; color: #FFFFFF; }',
    'html[data-contraste="alto"] .onb-obj-aviso { color: #7C2D12; }',
    'html[data-contraste="alto"] :focus-visible { outline: 3px solid var(--nc-text); outline-offset: 3px; }'
  ].join('\n');
  var estilo = document.createElement('style');
  estilo.setAttribute('data-onb-acessibilidade', '');
  estilo.textContent = css;
  document.head.appendChild(estilo);

  // aviso falado para leitores de tela quando a aparência muda (invisível na tela)
  var aviso = document.createElement('p');
  aviso.id = 'onbAcessAviso';
  aviso.setAttribute('role', 'status');
  aviso.setAttribute('aria-live', 'polite');
  aviso.style.cssText = 'position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;';
  document.body.appendChild(aviso);

  function carregarLexend() {
    if (document.getElementById('onbLexend')) return;
    var link = document.createElement('link');
    link.id = 'onbLexend';
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=Lexend:wght@400;600;800&display=swap';
    document.head.appendChild(link);
  }

  var atual = null;
  function escolha() {
    var v = state.answers && state.answers[PERGUNTA];
    if (Array.isArray(v)) v = v[0];
    return typeof v === 'string' ? v : null;
  }
  function aplicar(anunciar) {
    var chave = escolha() || 'padrao';
    var modo = MODOS[chave] || PADRAO;
    var html = document.documentElement;
    html.setAttribute('data-fonte', modo.fonte);
    html.setAttribute('data-contraste', modo.contraste);
    html.setAttribute('data-tipografia', modo.tipografia);
    if (modo.tipografia === 'dislexia') carregarLexend();
    if (anunciar && chave !== atual) aviso.textContent = modo.aviso;
    atual = chave;
  }

  // o motor guarda a resposta no clique do botão da opção; este ouvinte, no recipiente, roda logo depois dele
  els.options.addEventListener('click', function () { setTimeout(function () { aplicar(true); }, 0); });

  // ao avançar, voltar ou recarregar a pergunta, reaplica a escolha guardada
  var renderOriginal = renderQuestion;
  renderQuestion = function () {
    renderOriginal.apply(this, arguments);
    aplicar(false);
  };
  aplicar(false);
})();
