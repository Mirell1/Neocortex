/*
 * NEOCORTEX — voz_chat.js
 * Ditado por voz no chat do Assistente (Web Speech API do navegador, em português do Brasil).
 *
 *  - Só TRANSCREVE para o campo de mensagem: a pessoa revisa e envia (nada é enviado sozinho).
 *  - O áudio é processado pelo serviço de voz do próprio navegador (no Chrome, da Google).
 *    O NEOCORTEX não grava nem recebe áudio: só recebe o texto, quando a pessoa envia a mensagem.
 *  - Sem suporte (ex.: Firefox) ou fora de https/localhost, o botão fica escondido e o chat segue só com o teclado.
 *
 * Uso:  const voz = NCVoz.iniciar({ botao, campo, status, form });
 * Os textos mostrados à pessoa estão em MENSAGENS, logo abaixo, para o grupo poder revisar.
 */
(function (global) {
  'use strict';

  const MENSAGENS = {
    dica: 'Dica: toque no microfone para ditar. O áudio é transcrito pelo serviço de voz do navegador.',
    ouvindo: 'Ouvindo… fale agora. Toque no microfone para parar.',
    finalizando: 'Finalizando…',
    revisar: 'Pronto. Revise o texto e envie.',
    nada: 'Não ouvi nada. Tente de novo, mais perto do microfone.',
    erros: {
      'not-allowed': 'O navegador bloqueou o microfone. Libere a permissão no cadeado da barra de endereço.',
      'service-not-allowed': 'O navegador bloqueou o microfone. Libere a permissão no cadeado da barra de endereço.',
      'audio-capture': 'Não encontrei um microfone neste dispositivo.',
      'network': 'A transcrição precisa de internet. Verifique a conexão e tente de novo.',
      'language-not-supported': 'O português não está disponível para voz neste navegador.',
      'no-speech': 'Não ouvi nada. Tente de novo, mais perto do microfone.',
    },
    erroGenerico: 'Não consegui transcrever agora. Você pode digitar normalmente.',
    rotuloOuvir: 'Falar em vez de digitar',
    rotuloParar: 'Parar de ouvir',
  };

  function iniciar(op) {
    const win = op.janela || global;
    const SR = win.SpeechRecognition || win.webkitSpeechRecognition;
    if (!SR) return { suportado: false, motivo: 'sem-suporte' };
    if (win.isSecureContext === false) return { suportado: false, motivo: 'inseguro' };   // o microfone exige https ou localhost

    const { botao, campo, status, form } = op;
    const idioma = op.idioma || 'pt-BR';
    // no Chrome do Android o modo contínuo repete palavras; lá, uma frase por toque
    const continuo = !/Android/i.test((win.navigator && win.navigator.userAgent) || '');

    let rec = null;
    let ouvindo = false;
    let base = '';            // o que já estava no campo quando começou a ditar
    let erro = null;
    let sobraTimer = null;
    let descartar = false;    // depois de ENVIAR, a transcrição que ainda chegar é ignorada (senão devolveria o texto à caixa)

    const dizer = (texto) => { if (status) status.textContent = texto; };
    const limite = () => (campo.maxLength > 0 ? campo.maxLength : 0);

    function montar(finais, interim) {
      let texto = [base, finais, interim].map((s) => (s || '').trim()).filter(Boolean).join(' ');
      if (!base && texto) texto = texto.charAt(0).toUpperCase() + texto.slice(1);
      const max = limite();
      return max && texto.length > max ? texto.slice(0, max) : texto;
    }

    function aplicar(finais, interim) {
      campo.value = montar(finais, interim);
      if (win.Event && campo.dispatchEvent) campo.dispatchEvent(new win.Event('input', { bubbles: true }));
    }

    function pintar() {
      botao.setAttribute('aria-pressed', ouvindo ? 'true' : 'false');
      botao.setAttribute('aria-label', ouvindo ? MENSAGENS.rotuloParar : MENSAGENS.rotuloOuvir);
      botao.title = ouvindo ? MENSAGENS.rotuloParar : MENSAGENS.rotuloOuvir;
      if (botao.classList) botao.classList.toggle('ouvindo', ouvindo);
    }

    function encerrar() {
      if (win.clearTimeout) win.clearTimeout(sobraTimer);
      const estavaOuvindo = ouvindo;
      ouvindo = false;
      pintar();
      if (!estavaOuvindo) return;
      if (erro) { erro = null; return; }   // a mensagem de erro já foi mostrada
      if (campo.value.trim() !== base.trim()) { dizer(MENSAGENS.revisar); if (campo.focus) campo.focus(); }
      else dizer(MENSAGENS.nada);
    }

    function comecar() {
      if (ouvindo) return;
      rec = new SR();
      rec.lang = idioma;
      rec.interimResults = true;
      rec.continuous = continuo;
      rec.maxAlternatives = 1;
      base = (campo.value || '').trim();
      erro = null;
      descartar = false;

      rec.onresult = (ev) => {
        if (descartar) return;
        // refaz o texto a partir de TODOS os resultados: evita repetir palavras quando o navegador reenvia o acumulado
        let finais = '';
        let interim = '';
        for (let i = 0; i < ev.results.length; i += 1) {
          const r = ev.results[i];
          const t = (r[0] && r[0].transcript) || '';
          if (r.isFinal) finais += (finais ? ' ' : '') + t.trim();
          else interim += t;
        }
        aplicar(finais, interim);
      };
      rec.onerror = (ev) => {
        if (ev.error === 'aborted') return;   // parada de propósito
        erro = ev.error || 'desconhecido';
        dizer(MENSAGENS.erros[ev.error] || MENSAGENS.erroGenerico);
      };
      rec.onend = encerrar;

      try {
        rec.start();
      } catch (e) {          // por exemplo: já estava ouvindo
        erro = null;
        return;
      }
      ouvindo = true;
      pintar();
      dizer(MENSAGENS.ouvindo);
    }

    function parar() {
      if (!ouvindo || !rec) return;
      dizer(MENSAGENS.finalizando);
      try { rec.stop(); } catch (e) { /* nada */ }
      // alguns navegadores não chamam onend depois do stop: garante que a tela não fique "ouvindo"
      if (win.setTimeout) sobraTimer = win.setTimeout(() => { if (ouvindo) encerrar(); }, 1500);
    }

    function abortar() {
      if (rec && ouvindo) { try { rec.abort(); } catch (e) { /* nada */ } }
      ouvindo = false;
      pintar();
    }

    botao.hidden = false;
    pintar();
    dizer(MENSAGENS.dica);
    botao.addEventListener('click', () => (ouvindo ? parar() : comecar()));
    if (form && form.addEventListener) {
      form.addEventListener('submit', (e) => {      // enviar a mensagem encerra o ditado
        parar();
        // se a página cancelar o envio (por exemplo, mensagem em branco), o ditado continua valendo; senão, resultados atrasados são ignorados
        const marcar = () => { if (!(e && e.defaultPrevented)) descartar = true; };
        if (win.setTimeout) win.setTimeout(marcar, 0); else marcar();
      });
    }
    if (win.document && win.document.addEventListener) {
      win.document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && ouvindo) parar(); });
    }
    if (win.addEventListener) win.addEventListener('pagehide', abortar);

    return { suportado: true, parar, ouvindo: () => ouvindo };
  }

  global.NCVoz = { iniciar, MENSAGENS };
})(typeof window !== 'undefined' ? window : globalThis);
