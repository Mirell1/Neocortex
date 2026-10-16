/* ============================================================
   NEOCORTEX - Mascote (robô assistente)  ->  static/mascote_robo.js

   Uso no template:
     <div data-nc-mascote></div>                                modo normal (balão, tocável)
     <div data-nc-mascote data-modo="avatar"></div>             avatar do chat (vivo)
     <div data-nc-mascote data-modo="avatar" data-estatico></div>  avatar parado (histórico)

   Eventos vindos do servidor (após redirect): o base_app_novo.html define
     window.NC_EVENTOS_INICIAIS = [{tipo, dados}, ...]  (ver _mascote_evento no app.py)

   Disparar reações de qualquer página:
     document.dispatchEvent(new CustomEvent('nc:evento', {
       detail: { tipo: 'meta_concluida', dados: { objetivo: 'Aprender Python', feitas: 4, total: 8 } }
     }));

   Regras de design (combinadas com o grupo):
   - reage a AÇÕES, nunca à ausência; não tem necessidades próprias
   - elogia a ação, não fala de sentimentos sobre o usuário
   - frases fixas e revisáveis neste arquivo, não geradas pela IA
   - conclusões em lote não geram festa extra
   ============================================================ */
(function () {
  'use strict';

  // ------------------------------------------------------------
  // VISUAL
  // ------------------------------------------------------------
  const SVG_ROBO = `
<svg class="nc-mascote-svg" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <ellipse class="nc-sombra" cx="100" cy="192" rx="34" ry="5"/>
  <g class="nc-corpo"><g class="nc-giro">
    <path class="nc-propulsor" d="M93 168 Q100 190 107 168 Z"/>
    <g class="nc-dendritos">
      <path class="principal" d="M100 42 L100 26"/>
      <path class="ramo" d="M100 31 C95 25 91 21 85 17"/>
      <path class="ramo" d="M100 29 C105 23 109 19 115 15"/>
      <circle class="no" cx="100" cy="24" r="4"/><circle class="no" cx="85" cy="17" r="3.5"/><circle class="no" cx="115" cy="15" r="3.5"/>
    </g>
    <ellipse class="nc-casco nc-tronco" cx="100" cy="140" rx="33" ry="29"/>
    <g class="nc-nucleo">
      <circle class="anel" cx="100" cy="143" r="14"/>
      <circle class="centro" cx="100" cy="143" r="8"/>
    </g>
    <g class="nc-braco nc-braco-esq"><ellipse class="nc-casco" cx="58" cy="140" rx="9" ry="15" transform="rotate(18 58 140)"/></g>
    <g class="nc-braco nc-braco-dir"><ellipse class="nc-casco" cx="142" cy="140" rx="9" ry="15" transform="rotate(-18 142 140)"/></g>

    <rect class="nc-casco" x="50" y="40" width="100" height="80" rx="36"/>
    <circle class="nc-luz-lateral" cx="50" cy="80" r="5"/><circle class="nc-luz-lateral" cx="150" cy="80" r="5"/>
    <rect class="nc-tela" x="61" y="51" width="78" height="56" rx="24"/>
    <path class="nc-tela-reflexo" d="M70 62 Q74 56 82 55"/>
    <g class="nc-bochechas"><circle cx="76" cy="90" r="5"/><circle cx="124" cy="90" r="5"/></g>

    <g class="nc-olhos nc-olhos-neutra"><ellipse cx="87" cy="77" rx="5" ry="7.5"/><ellipse cx="113" cy="77" rx="5" ry="7.5"/></g>
    <g class="nc-olhos nc-olhos-feliz"><path d="M81 80 Q87 71 93 80"/><path d="M107 80 Q113 71 119 80"/></g>
    <g class="nc-olhos nc-olhos-fechados"><path d="M81 77 Q87 82 93 77"/><path d="M107 77 Q113 82 119 77"/></g>
    <g class="nc-olhos nc-olhos-estrela">
      <path class="cheio" d="M87.0 68.5 L89.1 74.1 L95.1 74.4 L90.4 78.1 L92.0 83.9 L87.0 80.6 L82.0 83.9 L83.6 78.1 L78.9 74.4 L84.9 74.1 Z"/>
      <path class="cheio" d="M113.0 68.5 L115.1 74.1 L121.1 74.4 L116.4 78.1 L118.0 83.9 L113.0 80.6 L108.0 83.9 L109.6 78.1 L104.9 74.4 L110.9 74.1 Z"/>
    </g>
    <g class="nc-olhos nc-olhos-pensando"><ellipse cx="91" cy="73" rx="4.5" ry="6.5"/><ellipse cx="117" cy="73" rx="4.5" ry="6.5"/></g>
    <g class="nc-olhos nc-olhos-confuso"><ellipse cx="87" cy="76" rx="5.5" ry="8"/><ellipse cx="113" cy="79" rx="4" ry="4"/></g>
    <g class="nc-olhos nc-olhos-piscadela"><ellipse cx="87" cy="77" rx="5" ry="7.5"/><path d="M107 80 Q113 71 119 80"/></g>
    <g class="nc-olhos nc-olhos-surpresa"><ellipse cx="87" cy="76" rx="6.5" ry="9"/><ellipse cx="113" cy="76" rx="6.5" ry="9"/></g>

    <path class="nc-boca nc-boca-neutra" d="M95 92 Q100 96 105 92"/>
    <path class="nc-boca nc-boca-feliz" d="M92 90 Q100 101 108 90 Z"/>
    <path class="nc-boca nc-boca-fechados" d="M96 94 L104 94"/>
    <g class="nc-boca nc-boca-pensando"><circle cx="93" cy="94" r="2.3"/><circle cx="100" cy="94" r="2.3"/><circle cx="107" cy="94" r="2.3"/></g>
    <path class="nc-boca nc-boca-confuso" d="M93 94 Q96.5 90 100 94 Q103.5 98 107 94"/>
    <ellipse class="nc-boca nc-boca-falando" cx="100" cy="93" rx="4.5" ry="3.5"/>
    <ellipse class="nc-boca nc-boca-surpresa" cx="100" cy="94" rx="3.5" ry="4.5"/>

    <g class="nc-acessorio nc-acessorio-gorro">
      <path class="copa" d="M60 52 Q64 24 100 22 Q136 24 140 52 Z"/>
      <rect class="faixa" x="56" y="45" width="88" height="11" rx="5.5"/>
      <circle class="pompom" cx="100" cy="20" r="7"/>
    </g>
    <g class="nc-acessorio nc-acessorio-oculos">
      <circle cx="87" cy="77" r="12"/><circle cx="113" cy="77" r="12"/><path d="M99 76 Q100 74 101 76"/>
    </g>
    <g class="nc-acessorio nc-acessorio-cachecol">
      <path d="M64 112 Q100 128 136 112 L134 124 Q100 140 66 124 Z"/>
      <path d="M116 126 L126 152 L114 154 L108 130 Z"/>
      <path class="listra" d="M118 136 L124 135"/><path class="listra" d="M120 144 L126 143"/>
    </g>

    <g class="nc-faiscas">
      <circle cx="100" cy="22" r="5"/><circle cx="85" cy="17" r="4"/><circle cx="115" cy="15" r="4"/>
      <circle cx="44" cy="70" r="4"/><circle cx="156" cy="70" r="4"/>
      <circle cx="40" cy="118" r="4"/><circle cx="160" cy="118" r="4"/><circle cx="100" cy="143" r="5"/>
    </g>
  </g></g>
  <text class="nc-interrogacao" x="128" y="30">?</text>
  <g class="nc-zzz"><text x="146" y="46">z</text><text x="156" y="34">z</text><text x="166" y="22">z</text></g>
</svg>`;

  const SVG_GRAO = `
<svg class="nc-mascote-svg" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <ellipse class="nc-sombra" cx="100" cy="192" rx="62" ry="6"/>
  <g class="nc-corpo"><g class="nc-giro">
    <g class="nc-vapor">
      <path d="M78 58 Q70 47 78 37 Q86 27 78 16"/>
      <path d="M100 54 Q92 42 100 31 Q108 20 100 8"/>
      <path d="M122 58 Q114 47 122 37 Q130 27 122 16"/>
    </g>
    <g class="nc-vapor-estrela">
      <path d="M100 58 Q94 50 100 42"/>
      <path class="estrela" d="M100.0 7.0 L104.3 18.1 L116.2 18.7 L106.9 26.3 L110.0 37.8 L100.0 31.3 L90.0 37.8 L93.1 26.3 L83.8 18.7 L95.7 18.1 Z"/>
      <path class="estrela-mini" d="M66.0 27.0 L67.8 31.6 L72.7 31.8 L68.9 34.9 L70.1 39.7 L66.0 37.0 L61.9 39.7 L63.1 34.9 L59.3 31.8 L64.2 31.6 Z"/>
      <path class="estrela-mini" d="M136.0 23.0 L137.8 27.6 L142.7 27.8 L138.9 30.9 L140.1 35.7 L136.0 33.0 L131.9 35.7 L133.1 30.9 L129.3 27.8 L134.2 27.6 Z"/>
    </g>
    <ellipse class="nc-pires" cx="100" cy="174" rx="74" ry="13"/>
    <path class="nc-alca-fora" d="M150 92 Q182 92 175 124 Q168 150 140 146"/>
    <path class="nc-alca-dentro" d="M150 92 Q182 92 175 124 Q168 150 140 146"/>
    <path class="nc-xicara" d="M38 72 L162 72 L151 148 Q148 168 127 168 L73 168 Q52 168 49 148 Z"/>
    <path class="nc-faixa" d="M45.4 132 L154.6 132 L152.8 145 L47.2 145 Z"/>
    <ellipse class="nc-cafe" cx="100" cy="72" rx="62" ry="13"/>
    <ellipse class="nc-crema" cx="88" cy="70.5" rx="18" ry="4.5"/>
    <g class="nc-bochechas"><circle cx="66" cy="120" r="8"/><circle cx="134" cy="120" r="8"/></g>

    <g class="nc-olhos nc-olhos-neutra"><ellipse cx="82" cy="102" rx="6.5" ry="8.5"/><ellipse cx="118" cy="102" rx="6.5" ry="8.5"/><circle class="brilho" cx="84.5" cy="98.5" r="2.2"/><circle class="brilho" cx="120.5" cy="98.5" r="2.2"/></g>
    <g class="nc-olhos nc-olhos-feliz"><path d="M74 106 Q82 95 90 106"/><path d="M110 106 Q118 95 126 106"/></g>
    <g class="nc-olhos nc-olhos-fechados"><path d="M74 102 Q82 109 90 102"/><path d="M110 102 Q118 109 126 102"/></g>
    <g class="nc-olhos nc-olhos-estrela"><path class="cheio" d="M82.0 91.0 L84.8 98.2 L92.5 98.6 L86.5 103.5 L88.5 110.9 L82.0 106.7 L75.5 110.9 L77.5 103.5 L71.5 98.6 L79.2 98.2 Z"/><path class="cheio" d="M118.0 91.0 L120.8 98.2 L128.5 98.6 L122.5 103.5 L124.5 110.9 L118.0 106.7 L111.5 110.9 L113.5 103.5 L107.5 98.6 L115.2 98.2 Z"/></g>
    <g class="nc-olhos nc-olhos-pensando"><ellipse cx="86" cy="97" rx="5.5" ry="7.5"/><ellipse cx="122" cy="97" rx="5.5" ry="7.5"/></g>
    <g class="nc-olhos nc-olhos-confuso"><ellipse cx="82" cy="100" rx="7" ry="9.5"/><ellipse cx="118" cy="104" rx="5" ry="5"/></g>
    <g class="nc-olhos nc-olhos-piscadela"><ellipse cx="82" cy="102" rx="6.5" ry="8.5"/><path d="M110 106 Q118 95 126 106"/></g>
    <g class="nc-olhos nc-olhos-surpresa"><ellipse cx="82" cy="101" rx="8" ry="10.5"/><ellipse cx="118" cy="101" rx="8" ry="10.5"/></g>

    <path class="nc-boca nc-boca-neutra" d="M92 119 Q100 126 108 119"/>
    <path class="nc-boca nc-boca-feliz" d="M89 117 Q100 134 111 117 Z"/>
    <path class="nc-boca nc-boca-fechados" d="M94 122 L106 122"/>
    <g class="nc-boca nc-boca-pensando"><circle cx="91" cy="122" r="3"/><circle cx="100" cy="122" r="3"/><circle cx="109" cy="122" r="3"/></g>
    <path class="nc-boca nc-boca-confuso" d="M90 122 Q95 116 100 122 Q105 128 110 122"/>
    <ellipse class="nc-boca nc-boca-falando" cx="100" cy="121" rx="6" ry="5"/>
    <ellipse class="nc-boca nc-boca-surpresa" cx="100" cy="123" rx="5" ry="6.5"/>

    <g class="nc-faiscas">
      <circle cx="56" cy="40" r="5"/><circle cx="144" cy="40" r="5"/><circle cx="30" cy="96" r="4"/><circle cx="178" cy="70" r="4"/>
      <circle cx="26" cy="146" r="4"/><circle cx="180" cy="150" r="4"/><circle cx="100" cy="6" r="5"/><circle cx="70" cy="14" r="4"/>
    </g>
  </g></g>
  <text class="nc-interrogacao" x="150" y="40">?</text>
  <g class="nc-zzz"><text x="148" y="46">z</text><text x="160" y="34">z</text><text x="172" y="22">z</text></g>
</svg>`;

  // um visual por tema: o mascote segue o tema escolhido pela pessoa
  const SVG_BOLTZ = `
<svg class="nc-mascote-svg" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs><clipPath id="nc-bola-{{uid}}"><circle cx="100" cy="90" r="60"/></clipPath></defs>
  <ellipse class="nc-sombra" cx="100" cy="192" rx="48" ry="5.5"/>
  <g class="nc-corpo"><g class="nc-giro">
    <g class="nc-pernas">
      <path d="M84 146 L82 168 M116 146 L118 168"/>
      <path class="chuteira" d="M62 182 Q62 168 76 168 L86 168 Q92 168 92 177 L92 182 Z"/>
      <path class="chuteira" d="M138 182 Q138 168 124 168 L114 168 Q108 168 108 177 L108 182 Z"/>
      <circle class="trava" cx="70" cy="184" r="2"/><circle class="trava" cx="84" cy="184" r="2"/>
      <circle class="trava" cx="116" cy="184" r="2"/><circle class="trava" cx="130" cy="184" r="2"/>
    </g>
    <g class="nc-braco nc-braco-esq"><path class="haste" d="M42 98 Q26 104 26 120"/><circle class="luva" cx="26" cy="124" r="8"/></g>
    <g class="nc-braco nc-braco-dir"><path class="haste" d="M158 98 Q174 104 174 120"/><circle class="luva" cx="174" cy="124" r="8"/></g>
    <circle class="nc-bola" cx="100" cy="90" r="60"/>
    <g class="nc-gomos" clip-path="url(#nc-bola-{{uid}})">
      <path d="M100 26 L118 38 L112 56 L88 56 L82 38 Z"/>
      <path d="M36 70 L54 64 L62 82 L50 100 L34 96 Z"/>
      <path d="M164 70 L146 64 L138 82 L150 100 L166 96 Z"/>
      <path d="M58 138 L68 124 L86 132 L84 150 L64 152 Z"/>
      <path d="M142 138 L132 124 L114 132 L116 150 L136 152 Z"/>
    </g>
    <g class="nc-costuras" clip-path="url(#nc-bola-{{uid}})">
      <path d="M88 56 L72 70 M112 56 L128 70 M62 82 L72 70 M138 82 L128 70 M50 100 L58 118 M150 100 L142 118 M68 124 L58 118 M132 124 L142 118"/>
    </g>
    <path class="nc-costura-luz" d="M82 38 Q100 30 118 38"/>
    <circle class="nc-bola-contorno" cx="100" cy="90" r="60"/>
    <g class="nc-bochechas"><circle cx="66" cy="110" r="7"/><circle cx="134" cy="110" r="7"/></g>

    <g class="nc-olhos nc-olhos-neutra"><ellipse cx="84" cy="90" rx="6.5" ry="8.5"/><ellipse cx="116" cy="90" rx="6.5" ry="8.5"/><circle class="brilho" cx="86.5" cy="86.5" r="2.2"/><circle class="brilho" cx="118.5" cy="86.5" r="2.2"/></g>
    <g class="nc-olhos nc-olhos-feliz"><path d="M76 94 Q84 83 92 94"/><path d="M108 94 Q116 83 124 94"/></g>
    <g class="nc-olhos nc-olhos-fechados"><path d="M76 90 Q84 97 92 90"/><path d="M108 90 Q116 97 124 90"/></g>
    <g class="nc-olhos nc-olhos-estrela"><path class="cheio" d="M84.0 79.0 L86.8 86.2 L94.5 86.6 L88.5 91.5 L90.5 98.9 L84.0 94.7 L77.5 98.9 L79.5 91.5 L73.5 86.6 L81.2 86.2 Z"/><path class="cheio" d="M116.0 79.0 L118.8 86.2 L126.5 86.6 L120.5 91.5 L122.5 98.9 L116.0 94.7 L109.5 98.9 L111.5 91.5 L105.5 86.6 L113.2 86.2 Z"/></g>
    <g class="nc-olhos nc-olhos-pensando"><ellipse cx="88" cy="85" rx="5.5" ry="7.5"/><ellipse cx="120" cy="85" rx="5.5" ry="7.5"/></g>
    <g class="nc-olhos nc-olhos-confuso"><ellipse cx="84" cy="88" rx="7" ry="9.5"/><ellipse cx="116" cy="92" rx="5" ry="5"/></g>
    <g class="nc-olhos nc-olhos-piscadela"><ellipse cx="84" cy="90" rx="6.5" ry="8.5"/><path d="M108 94 Q116 83 124 94"/></g>
    <g class="nc-olhos nc-olhos-surpresa"><ellipse cx="84" cy="89" rx="8" ry="10.5"/><ellipse cx="116" cy="89" rx="8" ry="10.5"/></g>

    <path class="nc-boca nc-boca-neutra" d="M93 108 Q100 114 107 108"/>
    <path class="nc-boca nc-boca-feliz" d="M89 106 Q100 123 111 106 Z"/>
    <path class="nc-boca nc-boca-fechados" d="M94 111 L106 111"/>
    <g class="nc-boca nc-boca-pensando"><circle cx="91" cy="111" r="3"/><circle cx="100" cy="111" r="3"/><circle cx="109" cy="111" r="3"/></g>
    <path class="nc-boca nc-boca-confuso" d="M90 111 Q95 105 100 111 Q105 117 110 111"/>
    <ellipse class="nc-boca nc-boca-falando" cx="100" cy="110" rx="6" ry="5"/>
    <ellipse class="nc-boca nc-boca-surpresa" cx="100" cy="112" rx="5" ry="6.5"/>

    <g class="nc-faiscas">
      <circle cx="100" cy="20" r="5"/><circle cx="60" cy="30" r="4"/><circle cx="140" cy="30" r="4"/><circle cx="26" cy="70" r="4"/>
      <circle cx="174" cy="70" r="4"/><circle cx="18" cy="140" r="4"/><circle cx="182" cy="140" r="4"/><circle cx="100" cy="160" r="4"/>
    </g>
  </g></g>
  <text class="nc-interrogacao" x="156" y="36">?</text>
  <g class="nc-zzz"><text x="150" y="40">z</text><text x="162" y="28">z</text><text x="174" y="16">z</text></g>
</svg>`;

  const SKINS = { robo: SVG_ROBO, grao: SVG_GRAO, boltz: SVG_BOLTZ };

  // expressão -> [olhos, boca]
  const EXPRESSOES = {
    neutra:    ['neutra', 'neutra'],
    feliz:     ['feliz', 'feliz'],
    radiante:  ['estrela', 'feliz'],
    fechados:  ['fechados', 'fechados'],
    pensando:  ['pensando', 'pensando'],
    confuso:   ['confuso', 'confuso'],
    falando:   ['neutra', 'falando'],
    piscadela: ['piscadela', 'feliz'],
    surpresa:  ['surpresa', 'surpresa'],
  };

  // ------------------------------------------------------------
  // FALAS
  // {campo} só é usado se o dado vier no evento. Sem saudade, sem culpa,
  // sem "estou orgulhoso de você": o elogio é sobre a ação.
  // ------------------------------------------------------------
  const FRASES = {
    saudacao_manha: [
      'Bom dia! Vamos ver o que tem pra hoje?',
      'Bom dia! {pendentes} tarefas no plano de hoje.',
      'Bom dia. Uma coisa de cada vez.',
    ],
    saudacao_tarde: [
      'Boa tarde! Como está o plano de hoje?',
      'Boa tarde! Ainda há {pendentes} tarefas pra hoje.',
      'Boa tarde. Que tal escolher a próxima tarefa?',
    ],
    saudacao_noite: [
      'Boa noite! Hora de revisar o dia?',
      'Boa noite. O que ficou pra amanhã pode ser replanejado.',
      'Boa noite! {pendentes} tarefas ainda abertas hoje, sem pressa.',
    ],
    saudacao_madrugada: [
      'Já é bem tarde. O que faltar pode esperar até amanhã.',
      'Bip... modo noturno. Descanso também conta.',
    ],
    saudacao_livre: [
      'Nada pendente pra hoje. Bom momento pra planejar ou descansar.',
      'Agenda de hoje livre. Quer adiantar algum objetivo?',
    ],

    // ao tocar no mascote: sai como um baralho, sem repetir até acabar
    toque: [
      'Dica: objetivos ficam mais fáceis divididos em fragmentos.',
      'Dica: na tela de Objetivos, a IA pode sugerir os fragmentos pra você.',
      'Dica: remarcar uma tarefa atrasada é melhor do que deixá-la pra trás.',
      'Dica: posso criar tarefas pra você direto no chat do assistente.',
      'Dica: as animações podem ser reduzidas em Configurações.',
      'Curiosidade: o cérebro humano tem cerca de 86 bilhões de neurônios.',
      'Curiosidade: o neocórtex é a camada mais externa do cérebro, ligada a planejamento e linguagem.',
      'Curiosidade: neurônios se comunicam por sinapses. Minha antena é uma homenagem.',
      'Curiosidade: dormir bem ajuda o cérebro a consolidar memórias.',
      'Curiosidade: anotar uma tarefa ajuda a tirá-la da cabeça.',
      'Bip! Sistemas funcionando.',
      'Antena calibrada e pronta.',
    ],
    toque_insistente: [
      'Bip bop! Tudo funcionando por aqui.',
      'Opa, quanto toque! Antena intacta.',
    ],

    tarefa_concluida: ['Feito!', 'Uma a menos.', 'Tarefa concluída.', 'Pronto, essa já foi.'],
    tarefa_criada: ['Anotado.', 'Tarefa adicionada ao plano.', 'Registrado.'],
    dia_concluido: ['Tudo de hoje concluído!', 'Plano do dia completo. O resto do dia é seu.'],
    meta_concluida: [
      'Fragmento concluído.',
      'Mais um fragmento de {objetivo} pronto.',
      '{objetivo}: {feitas} de {total} fragmentos.',
      'Fragmento concluído. {objetivo} avançou.',
    ],
    meta_metade: ['Metade do caminho de {objetivo}!'],
    objetivo_criado: ['Objetivo criado. Que tal dividir em fragmentos?', 'Novo objetivo no plano: {objetivo}.'],
    objetivo_concluido: [
      'Objetivo concluído!',
      'Objetivo concluído: {objetivo}.',
      '{objetivo} concluído. Foram {semanas} semanas de constância.',
    ],
    tarefa_replanejada: [
      'Replanejar também é progresso.',
      'Nova data definida. Ajustar faz parte.',
      'Tarefa remarcada pra um horário que ainda dá.',
      'Remarcada. Um plano realista vale mais.',
    ],
    objetivo_pausado: [
      'Pausado. Ele fica aqui quando fizer sentido retomar.',
      'Objetivo pausado. Dá pra retomar quando quiser.',
    ],
    descanso: ['Dia de descanso conta como parte da rotina.', 'Descanso também faz parte do plano.'],
    conquista: ['Item desbloqueado!', 'Novo item desbloqueado: {item}.', 'Conquista: {item}.'],
  };

  // falas próprias de cada visual; o que faltar aqui cai nas FRASES gerais
  const DICAS_E_CURIOSIDADES = FRASES.toque.filter((f) => !/antena|Bip|Minha antena/i.test(f));
  const FRASES_SKIN = {
    grao: {
      saudacao_manha: [
        'Bom dia! O cardápio de hoje tem {pendentes} tarefas.',
        'Bom dia! Café passado, vamos ao dia?',
        'Bom dia. Um pedido de cada vez.',
      ],
      saudacao_tarde: [
        'Boa tarde! Hora do cafezinho e da próxima tarefa?',
        'Boa tarde! Ainda há {pendentes} pedidos pra hoje.',
      ],
      saudacao_noite: [
        'Boa noite! Que tal revisar o dia com calma?',
        'Boa noite. O que ficou pra amanhã pode ser replanejado.',
      ],
      saudacao_madrugada: ['Já é bem tarde. A cafeteria reabre amanhã.', 'Hora de descansar. O resto pode esperar.'],
      saudacao_livre: ['Nenhum pedido pra hoje. Bom momento pra planejar ou descansar.'],
      toque: DICAS_E_CURIOSIDADES.concat(['Plim! Café fresquinho por aqui.', 'Mexendo o açúcar... pronto!']),
      toque_insistente: ['Opa, quase derramou! Tudo certo por aqui.', 'Calma, o pires tá firme!'],
      tarefa_concluida: ['Pedido servido!', 'Mais um pedido pronto.', 'Servido. Uma a menos.', 'Saindo do balcão!'],
      tarefa_criada: ['Anotado no pedido.', 'Pedido anotado.', 'Entrou no cardápio.'],
      dia_concluido: ['Todos os pedidos de hoje servidos!', 'Cardápio do dia completo. O resto do dia é seu.'],
      objetivo_concluido: [
        'Especial da casa: objetivo concluído!',
        'Objetivo concluído: {objetivo}. Isso merece um brinde.',
      ],
      tarefa_replanejada: ['Pedido remarcado. Melhor servir na hora certa.', 'Nova data definida. Ajustar faz parte.'],
      descanso: ['Hoje a cafeteria fecha mais cedo.', 'Pausa pro café. Descanso também conta.'],
    },
    // Campeonato: o vocabulário é de futebol, mas sem adversário, derrota ou placar contra
    boltz: {
      saudacao_manha: [
        'Bom dia! A escalação de hoje tem {pendentes} tarefas.',
        'Bom dia! Bora aquecer pro dia?',
        'Bom dia. Uma jogada de cada vez.',
      ],
      saudacao_tarde: [
        'Boa tarde! Segundo tempo começando.',
        'Boa tarde! Ainda há {pendentes} tarefas em campo.',
      ],
      saudacao_noite: [
        'Boa noite! Que tal revisar o dia com calma?',
        'Boa noite. O que ficou pra amanhã entra na próxima escalação.',
      ],
      saudacao_madrugada: ['Já é tarde. Até o craque precisa descansar.', 'Hora do vestiário. O resto pode esperar.'],
      saudacao_livre: ['Nenhuma tarefa escalada pra hoje. Bom momento pra planejar ou descansar.'],
      toque: DICAS_E_CURIOSIDADES.concat(['Embaixadinha número um... dois... opa!', 'Quer ver um drible? Brincadeira, bora organizar.']),
      toque_insistente: ['Ei, eu sou a bola, mas não precisa chutar tanto!', 'Opa, quase saí de campo! Tudo certo.'],
      tarefa_concluida: ['GOOOL! Mais uma tarefa concluída.', 'Golaço!', 'Bola na rede. Uma a menos.', 'Mais uma pra conta do dia.'],
      tarefa_criada: ['Tarefa escalada.', 'Entrou na escalação.'],
      dia_concluido: ['Todas as tarefas de hoje concluídas!', 'Dia completo. Agora é descanso no vestiário.'],
      objetivo_concluido: ['É campeão! Objetivo concluído.', 'Objetivo concluído: {objetivo}. Troféu merecido.'],
      tarefa_replanejada: ['Sem problema, ajustei a escalação.', 'Mudança tática: tarefa remarcada.'],
      descanso: ['Intervalo também faz parte do jogo.', 'Hoje é dia de descanso no vestiário.'],
    },
  };

  // ------------------------------------------------------------
  // REAÇÕES
  // etapas: [estado, expressão, ms]. ms = 0 na última etapa = fica até o próximo evento.
  // Efeitos (partículas/onda) saem no início da última etapa.
  // ------------------------------------------------------------
  const REACOES = {
    tarefa_concluida:   { etapas: [['comemora_p', 'feliz', 1300]], particulas: 8 },
    tarefa_criada:      { etapas: [['toque', 'piscadela', 1100]] },
    dia_concluido:      { etapas: [['surpresa', 'surpresa', 420], ['comemora_m', 'radiante', 2400]], particulas: 22, onda: true },
    meta_concluida:     { etapas: [['comemora_m', 'feliz', 2200]], particulas: 16 },
    objetivo_criado:    { etapas: [['incentivo', 'feliz', 1600]] },
    objetivo_concluido: { etapas: [['surpresa', 'surpresa', 450], ['comemora_g', 'radiante', 3200]], particulas: 40, onda: true },
    tarefa_replanejada: { etapas: [['incentivo', 'feliz', 1800]] },
    objetivo_pausado:   { etapas: [['incentivo', 'neutra', 1800]] },
    conquista:          { etapas: [['surpresa', 'surpresa', 500], ['comemora_m', 'radiante', 2400]], particulas: 24, onda: true },
    // assistente (sem frase: no chat, a fala é a própria resposta da IA)
    ia_pensando:        { etapas: [['pensando', 'pensando', 0]] },
    ia_respondeu:       { etapas: [['falando', 'falando', 1600]] },
    ia_erro:            { etapas: [['confuso', 'confuso', 2400]] },
  };

  const INTENSIDADES = ['completa', 'reduzida', 'desligada'];
  const ACOES_OCIOSAS = ['olhar', 'antena', 'piscar2', 'espreguicar'];
  const CORES_EXTRAS = ['#FF8FB1', '#5FD3C6'];
  const JANELA_LOTE_MS = 12000;   // maior que no protótipo: cada conclusão recarrega a página
  const TEMPO_BALAO_MS = 4200;
  const ESPERA_TOQUE_MS = 1200;
  let contadorInstancias = 0;   // ids únicos dentro dos SVGs (ex.: clipPath do Boltz)

  const camposDe = (m) => [...m.matchAll(/\{(\w+)\}/g)].map((x) => x[1]);
  const temValor = (v) => v !== undefined && v !== null && String(v).trim() !== '';
  const preencher = (m, d) => m.replace(/\{(\w+)\}/g, (_, k) => String(d[k]));
  const sorteio = (lista) => lista[Math.floor(Math.random() * lista.length)];
  const entre = (a, b) => a + Math.random() * (b - a);

  function lerLote() {
    try { return JSON.parse(sessionStorage.getItem('nc_mascote_lote')) || { n: 0, ate: 0 }; }
    catch (e) { return { n: 0, ate: 0 }; }
  }
  function salvarLote(lote) {
    try { sessionStorage.setItem('nc_mascote_lote', JSON.stringify(lote)); } catch (e) { /* sem storage */ }
  }

  function periodoAtual(hora) {
    if (hora >= 23 || hora < 5) return 'madrugada';
    if (hora < 12) return 'manha';
    if (hora < 18) return 'tarde';
    return 'noite';
  }

  // ------------------------------------------------------------
  class Mascote {
    constructor(raiz, opcoes = {}) {
      this.raiz = raiz;
      this.modo = (opcoes.modo || raiz.dataset.modo) === 'avatar' ? 'avatar' : 'normal';
      this.estatico = Boolean(opcoes.estatico ?? ('estatico' in raiz.dataset));
      this.skin = SKINS[opcoes.skin || raiz.dataset.skin] ? (opcoes.skin || raiz.dataset.skin) : 'robo';
      const svg = SKINS[this.skin].replaceAll('{{uid}}', `m${++contadorInstancias}`);

      raiz.classList.add('nc-mascote');
      raiz.dataset.modo = this.modo;
      raiz.dataset.skin = this.skin;
      const figura = this.modo === 'normal' && !this.estatico
        ? `<button type="button" class="nc-mascote-botao" aria-label="Mascote do NEOCORTEX. Toque para uma dica.">${svg}</button>`
        : svg;
      raiz.innerHTML =
        `<div class="nc-mascote-palco">${figura}<div class="nc-particulas" aria-hidden="true"></div></div>` +
        (this.modo === 'normal' ? '<p class="nc-mascote-balao" role="status" aria-live="polite"></p>' : '');

      this.palco = raiz.querySelector('.nc-mascote-palco');
      this.camadaParticulas = raiz.querySelector('.nc-particulas');
      this.balao = raiz.querySelector('.nc-mascote-balao');
      this.ultimaFrase = {};
      this.baralhos = {};
      this.timers = [];
      this.timerBalao = null;
      this.timerOcioso = null;
      this.lote = { n: 0, ate: 0 };
      this.toques = [];
      this.toqueLiberadoEm = 0;
      this.emDescanso = false;

      const reduzirMovimento = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.setIntensidade(this.estatico ? 'desligada'
        : (opcoes.intensidade || raiz.dataset.intensidade || (reduzirMovimento ? 'reduzida' : 'completa')));
      this.personalizar(opcoes.visual || { acessorio: raiz.dataset.acessorio });
      this._aplicar('neutro', 'neutra');

      const botao = raiz.querySelector('.nc-mascote-botao');
      if (botao) botao.addEventListener('click', () => this._aoTocar());
      if (!this.estatico) this._agendarOcioso();
    }

    // ---------- configuração ----------
    setIntensidade(valor) {
      this.raiz.dataset.intensidade = INTENSIDADES.includes(valor) ? valor : 'completa';
    }

    personalizar({ cor, brilho, acessorio } = {}) {
      if (cor) this.raiz.style.setProperty('--nc-mascote-cor', cor);
      if (brilho) this.raiz.style.setProperty('--nc-mascote-brilho', brilho);
      this.raiz.dataset.acessorio = acessorio || 'nenhum';
    }

    // ---------- eventos ----------
    reage(tipo, dados = {}) {
      if (this.estatico) return;
      if (tipo === 'descanso') return this.setDescanso(true);
      if (tipo === 'fim_descanso') return this.setDescanso(false);
      if (tipo === 'saudacao') return this.saudar(dados);
      const reacao = REACOES[tipo];
      if (!reacao) return;

      let frase = null;
      let particulas = reacao.particulas || 0;

      if (tipo === 'tarefa_concluida') {
        const agora = Date.now();
        this.lote = lerLote();
        this.lote.n = agora < this.lote.ate ? this.lote.n + 1 : 1;
        this.lote.ate = agora + JANELA_LOTE_MS;
        salvarLote(this.lote);
        if (this.lote.n > 1) {
          frase = `${this.lote.n} tarefas concluídas.`;
          particulas = 0; // lote não ganha festa extra
        }
      }
      if (tipo === 'meta_concluida' && Number(dados.total) >= 4 && Number(dados.feitas) * 2 === Number(dados.total)) {
        frase = this._escolherFrase('meta_metade', dados);
        particulas += 6;
      }

      this._executar(reacao.etapas, particulas, reacao.onda);
      this._falar(frase || this._escolherFrase(tipo, dados));
    }

    saudar(dados = {}) {
      if (!dados.forcar) {
        try {
          if (sessionStorage.getItem('nc_mascote_saudou')) return;
          sessionStorage.setItem('nc_mascote_saudou', '1');
        } catch (e) { /* sem storage: cumprimenta mesmo assim */ }
      }
      const periodo = periodoAtual(dados.hora ?? new Date().getHours());
      const livre = periodo !== 'madrugada' && Number(dados.pendentes) === 0 && temValor(dados.pendentes);
      const chave = livre ? 'saudacao_livre' : `saudacao_${periodo}`;
      const expressao = periodo === 'madrugada' ? 'neutra' : 'feliz';
      this._executar([['toque', expressao, 1500]], 0, false);
      this._falar(this._escolherFrase(chave, dados));
    }

    setDescanso(ativo) {
      this.emDescanso = Boolean(ativo);
      this._limparTimers();
      if (this.emDescanso) {
        this._aplicar('descanso', 'fechados');
        this._falar(this._escolherFrase('descanso', {}), true);
      } else {
        this._aplicar('neutro', 'neutra');
        this._calar();
      }
    }

    // ---------- toque ----------
    _aoTocar() {
      const agora = Date.now();
      if (agora < this.toqueLiberadoEm) return;
      this.toqueLiberadoEm = agora + ESPERA_TOQUE_MS;
      this.toques = this.toques.filter((t) => agora - t < 8000).concat(agora);

      if (this.toques.length >= 5) {
        this.toques = [];
        this._executar([['surpresa', 'surpresa', 500], ['toque', 'feliz', 900]], 0, false);
        this._falar(this._escolherFrase('toque_insistente', {}));
      } else {
        this._executar([['toque', 'piscadela', 1400]], 3, false);
        this._falar(this._doBaralho('toque'));
      }
    }

    // ---------- máquina de estados ----------
    _executar(etapas, particulas, onda) {
      this._limparTimers();
      let t = 0;
      etapas.forEach(([estado, expressao, ms], i) => {
        const ultima = i === etapas.length - 1;
        this.timers.push(setTimeout(() => {
          this._aplicar(estado, expressao);
          if (ultima) this._efeitos(particulas, onda);
        }, t));
        t += ms;
        if (ultima && ms > 0) this.timers.push(setTimeout(() => this._voltarAoRepouso(), t));
      });
    }

    _limparTimers() {
      this.timers.forEach(clearTimeout);
      this.timers = [];
    }

    _voltarAoRepouso() {
      if (this.emDescanso) this._aplicar('descanso', 'fechados');
      else this._aplicar('neutro', 'neutra');
    }

    _aplicar(estado, expressao) {
      const r = this.raiz;
      const [olhos, boca] = EXPRESSOES[expressao] || EXPRESSOES.neutra;
      delete r.dataset.estado;
      delete r.dataset.ocioso;
      void r.offsetWidth; // reinicia a animação mesmo se o estado se repetir
      r.dataset.estado = estado;
      r.dataset.olhos = olhos;
      r.dataset.boca = boca;
    }

    _agendarOcioso() {
      clearTimeout(this.timerOcioso);
      this.timerOcioso = setTimeout(() => {
        const r = this.raiz;
        if (r.dataset.estado === 'neutro' && r.dataset.intensidade === 'completa' && !document.hidden) {
          const acao = sorteio(ACOES_OCIOSAS);
          r.dataset.ocioso = acao;
          setTimeout(() => { if (r.dataset.ocioso === acao) delete r.dataset.ocioso; }, 1900);
        }
        this._agendarOcioso();
      }, entre(9000, 16000));
    }

    // ---------- efeitos ----------
    _efeitos(quantidade, onda) {
      if (this.raiz.dataset.intensidade !== 'completa') return;
      const escala = this.modo === 'avatar' ? 0.55 : 1;
      if (this.modo === 'avatar') quantidade = Math.min(quantidade, 6);
      if (onda) this._onda(escala);
      if (!quantidade) return;

      const estilo = getComputedStyle(this.raiz);
      const cores = [
        estilo.getPropertyValue('--nc-mascote-cor').trim(),
        estilo.getPropertyValue('--nc-mascote-brilho').trim(),
        estilo.getPropertyValue('--nc-sinal').trim(),
        ...CORES_EXTRAS,
      ].filter(Boolean);
      const tamanho = this.palco.getBoundingClientRect().width || 160;

      for (let i = 0; i < quantidade; i++) {
        const p = document.createElement('span');
        const forma = sorteio(['bolinha', 'retangulo', 'estrela', 'anel']);
        const cor = sorteio(cores);
        p.className = `nc-particula ${forma}`;
        if (forma === 'anel') p.style.borderColor = cor;
        else p.style.background = cor;
        this.camadaParticulas.appendChild(p);

        const angulo = (entre(-200, 20) * Math.PI) / 180; // mais pra cima que pra baixo
        const dist = tamanho * entre(0.35, 0.8) * escala;
        const dx = Math.cos(angulo) * dist;
        const dy = Math.sin(angulo) * dist;
        const queda = tamanho * 0.3 * escala;
        const giro = entre(-360, 360);
        const base = 'translate(-50%, -50%)';

        const anim = p.animate([
          { transform: `${base} translate(0, 0) scale(0.3) rotate(0deg)`, opacity: 1 },
          { transform: `${base} translate(${dx}px, ${dy}px) scale(1) rotate(${giro / 2}deg)`, opacity: 1, offset: 0.5 },
          { transform: `${base} translate(${dx * 1.15}px, ${dy + queda}px) scale(0.7) rotate(${giro}deg)`, opacity: 0 },
        ], { duration: entre(900, 1500), delay: entre(0, 140), easing: 'cubic-bezier(.2,.75,.35,1)', fill: 'both' });
        anim.onfinish = () => p.remove();
      }
    }

    _onda(escala) {
      [0, 220].forEach((atraso) => {
        const o = document.createElement('span');
        o.className = 'nc-onda';
        this.camadaParticulas.appendChild(o);
        const anim = o.animate([
          { transform: 'translate(-50%, -50%) scale(0.3)', opacity: 0.7 },
          { transform: `translate(-50%, -50%) scale(${2.3 * escala + 0.4})`, opacity: 0 },
        ], { duration: 950, delay: atraso, easing: 'ease-out', fill: 'both' });
        anim.onfinish = () => o.remove();
      });
    }

    // ---------- falas ----------
    _frasesDe(tipo) {
      const proprias = FRASES_SKIN[this.skin] && FRASES_SKIN[this.skin][tipo];
      return proprias || FRASES[tipo] || [];
    }

    _escolherFrase(tipo, dados) {
      const todas = this._frasesDe(tipo);
      let possiveis = todas.filter((m) => camposDe(m).every((c) => temValor(dados[c])));
      if (possiveis.length > 1) possiveis = possiveis.filter((m) => m !== this.ultimaFrase[tipo]);
      if (!possiveis.length) return '';
      const modelo = sorteio(possiveis);
      this.ultimaFrase[tipo] = modelo;
      return preencher(modelo, dados);
    }

    _doBaralho(tipo) {
      let pilha = this.baralhos[tipo];
      if (!pilha || !pilha.length) {
        pilha = [...this._frasesDe(tipo)].sort(() => Math.random() - 0.5);
        if (pilha.length > 1 && pilha[pilha.length - 1] === this.ultimaFrase[tipo]) pilha.unshift(pilha.pop());
        this.baralhos[tipo] = pilha;
      }
      const frase = pilha.pop() || '';
      this.ultimaFrase[tipo] = frase;
      return frase;
    }

    _falar(texto, fixo = false) {
      if (!texto || !this.balao) return;
      clearTimeout(this.timerBalao);
      this.balao.textContent = texto;
      this.balao.classList.add('visivel');
      if (!fixo) this.timerBalao = setTimeout(() => this._calar(), TEMPO_BALAO_MS);
    }

    _calar() {
      clearTimeout(this.timerBalao);
      if (this.balao) this.balao.classList.remove('visivel');
    }
  }

  Mascote.SKINS = SKINS;
  Mascote.FRASES = FRASES;
  Mascote.FRASES_SKIN = FRASES_SKIN;
  Mascote.REACOES = REACOES;
  window.NCMascote = Mascote;

  // ------------------------------------------------------------
  // inicialização automática
  // ------------------------------------------------------------
  function iniciar() {
    const instancias = [...document.querySelectorAll('[data-nc-mascote]')].map((el) => new Mascote(el));
    const vivos = instancias.filter((m) => !m.estatico);
    window.ncMascotes = instancias;
    window.ncMascote = vivos.find((m) => m.modo === 'normal') || vivos[0] || null;

    const despachar = (tipo, dados) => {
      // eventos do assistente vão só para o avatar do chat, se houver um na página
      const avatares = vivos.filter((m) => m.modo === 'avatar');
      const alvos = String(tipo).startsWith('ia_') && avatares.length ? avatares : vivos;
      alvos.forEach((m) => m.reage(tipo, dados || {}));
    };
    document.addEventListener('nc:evento', (e) => {
      const { tipo, dados } = e.detail || {};
      despachar(tipo, dados);
    });

    // eventos que o servidor guardou antes do redirect (concluir tarefa, criar objetivo...)
    const iniciais = Array.isArray(window.NC_EVENTOS_INICIAIS) ? window.NC_EVENTOS_INICIAIS : [];
    setTimeout(() => {
      if (iniciais.length) {
        iniciais.forEach((ev, i) => setTimeout(() => despachar(ev.tipo, ev.dados), i * 1800));
      } else {
        const principal = vivos.find((m) => m.modo === 'normal');
        if (principal) principal.saudar(window.NC_SAUDACAO_DADOS || {});
      }
    }, 450);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();