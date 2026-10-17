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

    <g class="nc-acessorio nc-acessorio-protetor">
      <path class="banda" d="M47 70 Q46 56 58 50"/><path class="banda" d="M153 70 Q154 56 142 50"/>
      <path class="copa" d="M60 52 Q64 24 100 22 Q136 24 140 52 Z"/>
      <rect class="faixa" x="56" y="45" width="88" height="11" rx="5.5"/>
      <circle class="pompom" cx="100" cy="20" r="7"/>
      <ellipse class="concha" cx="44" cy="82" rx="12" ry="17"/><ellipse class="almofada" cx="44" cy="82" rx="6.5" ry="11"/>
      <ellipse class="concha" cx="156" cy="82" rx="12" ry="17"/><ellipse class="almofada" cx="156" cy="82" rx="6.5" ry="11"/>
    </g>
    <g class="nc-acessorio nc-acessorio-oculos3d">
      <rect class="lente-e" x="72" y="65" width="27" height="26" rx="7"/>
      <rect class="lente-d" x="101" y="65" width="27" height="26" rx="7"/>
      <rect class="ponte" x="98" y="71" width="4" height="6" rx="1"/>
      <path class="haste" d="M72 72 L58 68 M128 72 L142 68"/>
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
    <g class="nc-acessorio nc-acessorio-anjo">
      <path class="asa" d="M46 124 Q22 134 6 118 Q18 114 22 106 Q4 100 4 84 Q16 84 22 78 Q8 68 12 52 Q22 56 30 52 Q22 40 28 28 Q42 44 52 70 Z"/>
      <path class="asa" d="M 154 124 Q 178 134 194 118 Q 182 114 178 106 Q 196 100 196 84 Q 184 84 178 78 Q 192 68 188 52 Q 178 56 170 52 Q 178 40 172 28 Q 158 44 148 70 Z"/>
      <path class="pena" d="M46 106 Q28 110 14 112 M46 98 Q26 96 12 90 M48 90 Q30 80 18 66 M50 80 Q38 64 30 46"/>
      <path class="pena" d="M 154 106 Q 172 110 186 112 M 154 98 Q 174 96 188 90 M 152 90 Q 170 80 182 66 M 150 80 Q 162 64 170 46"/>
    </g>
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

    <!-- [PERSONALIZAR] encaixes de acessório: trocar só o desenho, mantendo as classes -->
    <g class="nc-acessorio nc-acessorio-gorro">
      <path class="copa" d="M42 68 Q44 28 100 26 Q156 28 158 68 Z"/>
      <rect class="faixa" x="36" y="62" width="128" height="14" rx="7"/>
      <circle class="pompom" cx="100" cy="24" r="7"/>
    </g>
    <g class="nc-acessorio nc-acessorio-oculos">
      <circle cx="82" cy="102" r="14"/><circle cx="118" cy="102" r="14"/><path d="M96 101 Q100 98 104 101"/>
    </g>
    <g class="nc-acessorio nc-acessorio-cachecol">
      <path d="M43 129 L157 129 L152 147 L48 147 Z"/>
      <path d="M124 145 L138 145 L141 176 L127 176 Z"/>
      <path class="listra" d="M127 157 L138 156"/><path class="listra" d="M128 167 L140 166"/>
      <path class="listra" d="M62 138 L138 138"/>
    </g>

    <g class="nc-acessorio nc-acessorio-anjo">
      <ellipse class="aureola" cx="100" cy="44" rx="31" ry="8"/>
      <ellipse class="aureola-brilho" cx="100" cy="42.5" rx="31" ry="8"/>
    </g>
    <g class="nc-acessorio nc-acessorio-jaqueta">
      <path class="corpo-jaqueta" d="M45.8 126 L154.2 126 L151 148 Q148 168 127 168 L73 168 Q52 168 49 148 Z"/>
      <path class="ziper" d="M100 140 L100 168"/>
      <path class="bolso" d="M58 150 Q66 161 82 159 M142 150 Q134 161 118 159"/>
      <g class="pelo-fundo"><circle cx="159.0" cy="107.0" r="8.4"/><circle cx="157.5" cy="114.3" r="8.4"/><circle cx="153.2" cy="121.3" r="8.4"/><circle cx="146.1" cy="127.6" r="8.4"/><circle cx="136.8" cy="132.8" r="8.4"/><circle cx="125.6" cy="136.7" r="8.4"/><circle cx="113.1" cy="139.2" r="8.4"/><circle cx="100.0" cy="140.0" r="8.4"/><circle cx="86.9" cy="139.2" r="8.4"/><circle cx="74.4" cy="136.7" r="8.4"/><circle cx="63.2" cy="132.8" r="8.4"/><circle cx="53.9" cy="127.6" r="8.4"/><circle cx="46.8" cy="121.3" r="8.4"/><circle cx="42.5" cy="114.3" r="8.4"/><circle cx="41.0" cy="107.0" r="8.4"/><circle cx="42.5" cy="99.7" r="8.4"/><circle cx="46.8" cy="92.7" r="8.4"/><circle cx="53.9" cy="86.4" r="8.4"/><circle cx="63.2" cy="81.2" r="8.4"/><circle cx="74.4" cy="77.3" r="8.4"/><circle cx="86.9" cy="74.8" r="8.4"/><circle cx="100.0" cy="74.0" r="8.4"/><circle cx="113.1" cy="74.8" r="8.4"/><circle cx="125.6" cy="77.3" r="8.4"/><circle cx="136.8" cy="81.2" r="8.4"/><circle cx="146.1" cy="86.4" r="8.4"/><circle cx="153.2" cy="92.7" r="8.4"/><circle cx="157.5" cy="99.7" r="8.4"/></g>
      <g class="pelo"><circle cx="159.0" cy="107.0" r="6.8"/><circle cx="157.5" cy="114.3" r="6.8"/><circle cx="153.2" cy="121.3" r="6.8"/><circle cx="146.1" cy="127.6" r="6.8"/><circle cx="136.8" cy="132.8" r="6.8"/><circle cx="125.6" cy="136.7" r="6.8"/><circle cx="113.1" cy="139.2" r="6.8"/><circle cx="100.0" cy="140.0" r="6.8"/><circle cx="86.9" cy="139.2" r="6.8"/><circle cx="74.4" cy="136.7" r="6.8"/><circle cx="63.2" cy="132.8" r="6.8"/><circle cx="53.9" cy="127.6" r="6.8"/><circle cx="46.8" cy="121.3" r="6.8"/><circle cx="42.5" cy="114.3" r="6.8"/><circle cx="41.0" cy="107.0" r="6.8"/><circle cx="42.5" cy="99.7" r="6.8"/><circle cx="46.8" cy="92.7" r="6.8"/><circle cx="53.9" cy="86.4" r="6.8"/><circle cx="63.2" cy="81.2" r="6.8"/><circle cx="74.4" cy="77.3" r="6.8"/><circle cx="86.9" cy="74.8" r="6.8"/><circle cx="100.0" cy="74.0" r="6.8"/><circle cx="113.1" cy="74.8" r="6.8"/><circle cx="125.6" cy="77.3" r="6.8"/><circle cx="136.8" cy="81.2" r="6.8"/><circle cx="146.1" cy="86.4" r="6.8"/><circle cx="153.2" cy="92.7" r="6.8"/><circle cx="157.5" cy="99.7" r="6.8"/></g>
      <rect class="puxador" x="97.5" y="141" width="5" height="9" rx="2"/>
    </g>

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
  <defs><clipPath id="nc-bola-{{uid}}"><circle cx="100" cy="100" r="60"/></clipPath></defs>
  <ellipse class="nc-sombra" cx="100" cy="194" rx="46" ry="5.5"/>
  <g class="nc-corpo"><g class="nc-giro">
    <g class="nc-pernas">
      <path d="M86 156 L84 172 M114 156 L116 172"/>
      <path class="chuteira" d="M64 188 Q64 173 78 173 L88 173 Q94 173 94 182 L94 188 Z"/>
      <path class="chuteira" d="M136 188 Q136 173 122 173 L112 173 Q106 173 106 182 L106 188 Z"/>
      <path class="sola" d="M66 185 L92 185 M108 185 L134 185"/>
    </g>
    <g class="nc-aletas">
      <path class="aleta" d="M58 62 L44 22 L82 46 Z"/><path class="aleta-luz" d="M58 53 L50 33 L71 46 Z"/>
      <path class="aleta" d="M142 62 L156 22 L118 46 Z"/><path class="aleta-luz" d="M142 53 L150 33 L129 46 Z"/>
    </g>
    <g class="nc-braco nc-braco-esq"><path class="haste" d="M44 116 Q30 124 30 138"/><circle class="luva" cx="30" cy="142" r="8"/></g>
    <g class="nc-braco nc-braco-dir"><path class="haste" d="M156 116 Q170 124 170 138"/><circle class="luva" cx="170" cy="142" r="8"/></g>
    <circle class="nc-bola" cx="100" cy="100" r="60"/>
    <g class="nc-gomos" clip-path="url(#nc-bola-{{uid}})">
      <path d="M100 42 L110 49 L107 61 L93 61 L90 49 Z"/>
      <path d="M44 118 L57 112 L65 124 L59 138 L44 136 Z"/>
      <path d="M156 118 L143 112 L135 124 L141 138 L156 136 Z"/>
      <path d="M100 141 L112 148 L108 161 L92 161 L88 148 Z"/>
    </g>
    <g class="nc-costuras" clip-path="url(#nc-bola-{{uid}})">
      <path d="M90 49 L74 58 M110 49 L126 58 M65 124 L76 131 M135 124 L124 131 M88 148 L80 136 M112 148 L120 136"/>
    </g>
    <circle class="nc-bola-contorno" cx="100" cy="100" r="60"/>
    <g class="nc-fones">
      <circle class="fone" cx="40" cy="100" r="14"/><circle class="fone-luz" cx="40" cy="100" r="7.5"/>
      <circle class="fone" cx="160" cy="100" r="14"/><circle class="fone-luz" cx="160" cy="100" r="7.5"/>
    </g>
    <rect class="nc-visor" x="60" y="66" width="80" height="58" rx="26"/>
    <rect class="nc-costura-luz" x="63.5" y="69.5" width="73" height="51" rx="23"/>
    <path class="nc-visor-reflexo" d="M72 79 Q75 73 83 72"/>
    <g class="nc-bochechas"><circle cx="72" cy="106" r="4.5"/><circle cx="128" cy="106" r="4.5"/></g>

    <g class="nc-olhos nc-olhos-neutra"><ellipse cx="86" cy="92" rx="6.5" ry="8.5"/><ellipse cx="114" cy="92" rx="6.5" ry="8.5"/><circle class="brilho" cx="88.5" cy="88.5" r="2.2"/><circle class="brilho" cx="116.5" cy="88.5" r="2.2"/></g>
    <g class="nc-olhos nc-olhos-feliz"><path d="M78 96 Q86 85 94 96"/><path d="M106 96 Q114 85 122 96"/></g>
    <g class="nc-olhos nc-olhos-fechados"><path d="M78 92 Q86 99 94 92"/><path d="M106 92 Q114 99 122 92"/></g>
    <g class="nc-olhos nc-olhos-estrela"><path class="cheio" d="M86.0 81.0 L88.8 88.2 L96.5 88.6 L90.5 93.5 L92.5 100.9 L86.0 96.7 L79.5 100.9 L81.5 93.5 L75.5 88.6 L83.2 88.2 Z"/><path class="cheio" d="M114.0 81.0 L116.8 88.2 L124.5 88.6 L118.5 93.5 L120.5 100.9 L114.0 96.7 L107.5 100.9 L109.5 93.5 L103.5 88.6 L111.2 88.2 Z"/></g>
    <g class="nc-olhos nc-olhos-pensando"><ellipse cx="90" cy="87" rx="5.5" ry="7.5"/><ellipse cx="118" cy="87" rx="5.5" ry="7.5"/></g>
    <g class="nc-olhos nc-olhos-confuso"><ellipse cx="86" cy="90" rx="7" ry="9.5"/><ellipse cx="114" cy="94" rx="5" ry="5"/></g>
    <g class="nc-olhos nc-olhos-piscadela"><ellipse cx="86" cy="92" rx="6.5" ry="8.5"/><path d="M106 96 Q114 85 122 96"/></g>
    <g class="nc-olhos nc-olhos-surpresa"><ellipse cx="86" cy="91" rx="8" ry="10.5"/><ellipse cx="114" cy="91" rx="8" ry="10.5"/></g>

    <path class="nc-boca nc-boca-neutra" d="M94 106 Q100 111 106 106"/>
    <path class="nc-boca nc-boca-feliz" d="M91 104 Q100 117 109 104 Z"/>
    <path class="nc-boca nc-boca-fechados" d="M95 108 L105 108"/>
    <g class="nc-boca nc-boca-pensando"><circle cx="92" cy="108" r="2.7"/><circle cx="100" cy="108" r="2.7"/><circle cx="108" cy="108" r="2.7"/></g>
    <path class="nc-boca nc-boca-confuso" d="M91 108 Q95.5 103 100 108 Q104.5 113 109 108"/>
    <ellipse class="nc-boca nc-boca-falando" cx="100" cy="107" rx="5.5" ry="4.5"/>
    <ellipse class="nc-boca nc-boca-surpresa" cx="100" cy="109" rx="4.5" ry="6"/>

    <!-- [PERSONALIZAR] encaixes de acessório: trocar só o desenho, mantendo as classes -->
    <g class="nc-acessorio nc-acessorio-gorro">
      <path class="copa" d="M62 62 Q66 30 100 28 Q134 30 138 62 Z"/>
      <rect class="faixa" x="58" y="56" width="84" height="11" rx="5.5"/>
      <circle class="pompom" cx="100" cy="26" r="7"/>
    </g>
    <g class="nc-acessorio nc-acessorio-oculos">
      <circle cx="86" cy="92" r="13"/><circle cx="114" cy="92" r="13"/><path d="M99 91 Q100 88 101 91"/>
    </g>
    <g class="nc-acessorio nc-acessorio-cachecol">
      <path d="M50 132 Q100 148 150 132 L140 146 Q100 160 60 146 Z"/>
      <path d="M116 150 L128 150 L130 174 L118 174 Z"/>
      <path class="listra" d="M118 160 L129 159"/><path class="listra" d="M119 168 L130 167"/>
    </g>

    <g class="nc-acessorio nc-acessorio-chuteira">
      <path class="bota" d="M64 188 Q64 173 78 173 L88 173 Q94 173 94 182 L94 188 Z"/>
      <path class="bota" d="M136 188 Q136 173 122 173 L112 173 Q106 173 106 182 L106 188 Z"/>
      <path class="sola-ouro" d="M65 185 L93 185 M107 185 L135 185"/>
      <path class="cadarco" d="M74 176 L83 179 M73 180 L82 183 M126 176 L117 179 M127 180 L118 183"/>
      <path class="brilho-bota" d="M68 179 Q69 175 74 175 M132 179 Q131 175 126 175"/>
      <g class="travas"><rect x="68" y="188" width="5" height="4" rx="1"/><rect x="78" y="188" width="5" height="4" rx="1"/><rect x="88" y="188" width="5" height="4" rx="1"/><rect x="107" y="188" width="5" height="4" rx="1"/><rect x="117" y="188" width="5" height="4" rx="1"/><rect x="127" y="188" width="5" height="4" rx="1"/></g>
      <path class="faisca-ouro" d="M52 164 L54 170 L60 172 L54 174 L52 180 L50 174 L44 172 L50 170 Z"/>
      <path class="faisca-ouro" d="M150 168 L151.5 172 L156 173.5 L151.5 175 L150 179 L148.5 175 L144 173.5 L148.5 172 Z"/>
    </g>
    <g class="nc-acessorio nc-acessorio-uniforme">
      <path class="camisa" d="M62 126 Q100 136 138 126 L156 134 L148 150 L136 146 L132 160 Q100 168 68 160 L64 146 L52 150 L44 134 Z"/>
      <path class="gola" d="M82 127 Q100 142 118 127"/>
      <path class="barra-manga" d="M47 140 L58 146 M153 140 L142 146"/>
      <path class="numero" d="M91 157 L91 143 L109 157 L109 143"/>
    </g>

    <g class="nc-faiscas">
      <circle cx="100" cy="18" r="5"/><circle cx="58" cy="22" r="4"/><circle cx="142" cy="22" r="4"/><circle cx="20" cy="74" r="4"/>
      <circle cx="180" cy="74" r="4"/><circle cx="16" cy="140" r="4"/><circle cx="184" cy="140" r="4"/><circle cx="100" cy="170" r="4"/>
    </g>
  </g></g>
  <text class="nc-interrogacao" x="160" y="36">?</text>
  <g class="nc-zzz"><text x="150" y="40">z</text><text x="162" y="28">z</text><text x="174" y="16">z</text></g>
</svg>`;

  const SVG_RABISCO = `
<svg class="nc-mascote-svg" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <ellipse class="nc-sombra" cx="100" cy="192" rx="56" ry="5.5"/>
  <g class="nc-acessorio nc-acessorio-caminha nc-cama-fundo">
    <ellipse class="borda-fundo" cx="100" cy="173" rx="80" ry="19"/>
    <ellipse class="miolo" cx="100" cy="176" rx="62" ry="11"/>
  </g>
  <g class="nc-corpo"><g class="nc-giro">
    <g class="nc-rabo"><path class="rabo-fora" d="M140 168 Q182 166 176 132 Q172 116 160 122"/><path class="rabo-dentro" d="M140 168 Q182 166 176 132 Q172 116 160 122"/></g>
    <ellipse class="nc-gato-pelo" cx="100" cy="152" rx="46" ry="30"/>
    <ellipse class="nc-gato-pata" cx="80" cy="178" rx="13" ry="7"/><ellipse class="nc-gato-pata" cx="120" cy="178" rx="13" ry="7"/>
    <g class="nc-orelhas">
      <path class="nc-gato-pelo" d="M44 66 L50 18 L84 46 Z"/><path class="orelha-dentro" d="M54 56 L57 32 L74 46 Z"/>
      <path class="nc-gato-pelo" d="M156 66 L150 18 L116 46 Z"/><path class="orelha-dentro" d="M146 56 L143 32 L126 46 Z"/>
    </g>
    <g class="nc-lapis" transform="rotate(-36 150 34)">
      <rect class="madeira" x="132" y="29" width="38" height="10" rx="2"/>
      <path class="ponta" d="M170 29 L181 34 L170 39 Z"/>
      <rect class="borracha" x="126" y="29" width="7" height="10" rx="1.5"/>
    </g>
    <ellipse class="nc-gato-pelo" cx="100" cy="84" rx="62" ry="50"/>
    <path class="nc-gato-listra" d="M88 40 Q100 36 112 40 M84 48 Q100 44 116 48"/>
    <g class="nc-bochechas"><circle cx="64" cy="98" r="8"/><circle cx="136" cy="98" r="8"/></g>
    <path class="nc-bigodes" d="M36 90 L58 93 M36 101 L58 99 M164 90 L142 93 M164 101 L142 99"/>
    <path class="nc-focinho" d="M96 92 L104 92 L100 97 Z"/>

    <g class="nc-olhos nc-olhos-neutra"><ellipse cx="80" cy="80" rx="6.5" ry="8.5"/><ellipse cx="120" cy="80" rx="6.5" ry="8.5"/><circle class="brilho" cx="82.5" cy="76.5" r="2.2"/><circle class="brilho" cx="122.5" cy="76.5" r="2.2"/></g>
    <g class="nc-olhos nc-olhos-feliz"><path d="M72 84 Q80 73 88 84"/><path d="M112 84 Q120 73 128 84"/></g>
    <g class="nc-olhos nc-olhos-fechados"><path d="M72 80 Q80 87 88 80"/><path d="M112 80 Q120 87 128 80"/></g>
    <g class="nc-olhos nc-olhos-estrela"><path class="cheio" d="M80.0 69.0 L82.8 76.2 L90.5 76.6 L84.5 81.5 L86.5 88.9 L80.0 84.7 L73.5 88.9 L75.5 81.5 L69.5 76.6 L77.2 76.2 Z"/><path class="cheio" d="M120.0 69.0 L122.8 76.2 L130.5 76.6 L124.5 81.5 L126.5 88.9 L120.0 84.7 L113.5 88.9 L115.5 81.5 L109.5 76.6 L117.2 76.2 Z"/></g>
    <g class="nc-olhos nc-olhos-pensando"><ellipse cx="84" cy="75" rx="5.5" ry="7.5"/><ellipse cx="124" cy="75" rx="5.5" ry="7.5"/></g>
    <g class="nc-olhos nc-olhos-confuso"><ellipse cx="80" cy="78" rx="7" ry="9.5"/><ellipse cx="120" cy="82" rx="5" ry="5"/></g>
    <g class="nc-olhos nc-olhos-piscadela"><ellipse cx="80" cy="80" rx="6.5" ry="8.5"/><path d="M112 84 Q120 73 128 84"/></g>
    <g class="nc-olhos nc-olhos-surpresa"><ellipse cx="80" cy="79" rx="8" ry="10.5"/><ellipse cx="120" cy="79" rx="8" ry="10.5"/></g>

    <path class="nc-boca nc-boca-neutra" d="M94 102 Q100 107 106 102"/>
    <path class="nc-boca nc-boca-feliz" d="M91 100 Q100 113 109 100 Z"/>
    <path class="nc-boca nc-boca-fechados" d="M95 104 L105 104"/>
    <g class="nc-boca nc-boca-pensando"><circle cx="92" cy="104" r="2.7"/><circle cx="100" cy="104" r="2.7"/><circle cx="108" cy="104" r="2.7"/></g>
    <path class="nc-boca nc-boca-confuso" d="M91 104 Q95.5 99 100 104 Q104.5 109 109 104"/>
    <ellipse class="nc-boca nc-boca-falando" cx="100" cy="103" rx="5.5" ry="4.5"/>
    <ellipse class="nc-boca nc-boca-surpresa" cx="100" cy="105" rx="4.5" ry="6"/>

    <!-- [PERSONALIZAR] encaixes de acessório -->
    <g class="nc-acessorio nc-acessorio-gorro">
      <path class="copa" d="M60 54 Q66 22 100 20 Q134 22 140 54 Z"/>
      <rect class="faixa" x="56" y="48" width="88" height="11" rx="5.5"/>
      <circle class="pompom" cx="100" cy="18" r="7"/>
    </g>
    <g class="nc-acessorio nc-acessorio-oculos">
      <circle cx="80" cy="80" r="13"/><circle cx="120" cy="80" r="13"/><path d="M93 79 Q100 75 107 79"/>
    </g>
    <g class="nc-acessorio nc-acessorio-cachecol">
      <path d="M56 124 Q100 140 144 124 L142 136 Q100 152 58 136 Z"/>
      <path d="M118 140 L130 140 L132 166 L120 166 Z"/>
      <path class="listra" d="M120 150 L131 149"/><path class="listra" d="M121 158 L132 157"/>
    </g>

    <g class="nc-acessorio nc-acessorio-capacete">
      <path class="casco" d="M58 56 Q60 18 100 16 Q140 18 142 56 Z"/>
      <rect class="nervura" x="93" y="16" width="14" height="40" rx="4"/>
      <rect class="aba" x="50" y="50" width="100" height="10" rx="5"/>
      <path class="brilho-capacete" d="M68 44 Q70 28 84 22"/>
    </g>
    <g class="nc-acessorio nc-acessorio-prancheta">
      <rect class="prancha" x="70" y="128" width="60" height="56" rx="5"/>
      <rect class="folha" x="75" y="138" width="50" height="41" rx="2"/>
      <rect class="presilha" x="88" y="123" width="24" height="11" rx="3"/>
      <path class="linhas" d="M81 147 L119 147 M81 155 L119 155 M81 163 L106 163"/>
      <path class="check" d="M82 172 L87 177 L96 168"/>
      <ellipse class="pata-segura" cx="68" cy="152" rx="9" ry="7"/><ellipse class="pata-segura" cx="132" cy="152" rx="9" ry="7"/>
    </g>

    <g class="nc-faiscas">
      <circle cx="100" cy="12" r="5"/><circle cx="40" cy="18" r="4"/><circle cx="168" cy="12" r="4"/><circle cx="20" cy="80" r="4"/>
      <circle cx="182" cy="84" r="4"/><circle cx="24" cy="150" r="4"/><circle cx="186" cy="160" r="4"/><circle cx="100" cy="186" r="4"/>
    </g>
  </g></g>
  <g class="nc-acessorio nc-acessorio-caminha nc-cama-frente">
    <path class="borda-frente" d="M20 174 Q100 202 180 174 Q188 183 172 188 Q100 206 28 188 Q12 183 20 174 Z"/>
    <path class="costura-cama" d="M34 182 Q100 203 166 182"/>
  </g>
  <text class="nc-interrogacao" x="156" y="30">?</text>
  <g class="nc-zzz"><text x="150" y="40">z</text><text x="162" y="28">z</text><text x="174" y="16">z</text></g>
</svg>`;

  const SKINS = { robo: SVG_ROBO, grao: SVG_GRAO, boltz: SVG_BOLTZ, rabisco: SVG_RABISCO };

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
    acessorio: ['Visual atualizado.', 'Acessório equipado.', 'Novo visual, mesmas funções.'],
  };

  // falas próprias de cada visual; o que faltar aqui cai nas FRASES gerais
  const DICAS_E_CURIOSIDADES = FRASES.toque.filter((f) => !/antena|Bip|Minha antena/i.test(f));
  const FRASES_SKIN = {
    // Papelaria: vocabulário de caderno e caneta
    rabisco: {
      saudacao_manha: ['Bom dia! A página de hoje tem {pendentes} tarefas.', 'Bom dia! Caneta na mão?', 'Bom dia. Um item de cada vez.'],
      saudacao_tarde: ['Boa tarde! Vamos riscar mais um item?', 'Boa tarde! Ainda há {pendentes} itens na lista de hoje.'],
      saudacao_noite: ['Boa noite! Que tal revisar a página de hoje?', 'Boa noite. O que ficou pode ir pra página de amanhã.'],
      saudacao_madrugada: ['Já é bem tarde. A página de amanhã espera.', 'Hora de fechar o caderno. O resto pode esperar.'],
      saudacao_livre: ['Página de hoje em branco. Bom momento pra planejar ou descansar.'],
      toque: DICAS_E_CURIOSIDADES.concat(['Miau... quer dizer, anotado!', 'Meu lápis está sempre apontado.']),
      toque_insistente: ['Ei, assim você amassa a página!', 'Prrr... tudo certo por aqui.'],
      tarefa_concluida: ['Riscada! Uma a menos.', 'Mais um item riscado da lista.', 'Feito! Marquei com caneta.'],
      tarefa_criada: ['Anotado!', 'Escrevi na lista.', 'Entrou na página.'],
      dia_concluido: ['Página de hoje completa!', 'Lista do dia toda riscada. O resto do dia é seu.'],
      objetivo_concluido: ['Página especial: objetivo concluído!', 'Objetivo concluído: {objetivo}. Merece um adesivo dourado.'],
      tarefa_replanejada: ['Passei pra outra página. Sem problema.', 'Nova data anotada. Ajustar faz parte.'],
      descanso: ['Hoje a página é de pausa.', 'Caderno fechado. Descanso também conta.'],
    },
    // robô (tema padrão): vocabulário leve de conexões, combinando com a rede da semana.
    // Só os tipos listados mudam; o resto continua com as FRASES gerais.
    robo: {
      tarefa_concluida: ['Feito!', 'Uma a menos.', 'Mais uma conexão feita.', 'Tarefa concluída.'],
      dia_concluido: ['Dia conectado! Todas as tarefas de hoje concluídas.', 'Todas as conexões de hoje acesas!'],
      saudacao_manha: [
        'Bom dia! Bora fortalecer umas conexões?',
        'Bom dia! {pendentes} tarefas na rede de hoje.',
        'Bom dia. Uma coisa de cada vez.',
      ],
    },
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
  // [ACESSÓRIOS] Falas ACRESCENTADAS por mascote. São somadas às de FRASES_SKIN (e às de FRASES, no robô).
  // Onde o mascote não tinha fala própria do tipo, passa a usar estas (em vez das do robô).
  // acessorio_<id> = fala ao equipar aquele acessório; descanso_caminha = Rabisco dormindo na caminha.
  // Frases fixas e revisáveis aqui. Marcadores aceitos: {item} {objetivo} {pendentes} {feitas} {total}.
  // ------------------------------------------------------------
  const FRASES_EXTRA = {
    robo: {
      acessorio_oculos: ['Óculos ajustados. Tudo em foco.', 'Agora vejo as tarefas com mais nitidez.', 'Lentes limpas, pronto pra ler a agenda.'],
      acessorio_gorro: ['Gorro colocado. Pompom incluso.', 'Estilo aquecido, circuitos tranquilos.', 'Gorro laranja: combina com o impulso elétrico.'],
      acessorio_oculos3d: ['Óculos 3D: a agenda agora tem profundidade.', 'Sessão de cinema iniciada. Pipoca não inclusa.', 'Em 3D, até a lista de hoje parece épica.'],
      acessorio_protetor: ['Protetor de orelha térmico ligado. Zero ruído por aqui.', 'Orelhas aquecidas e gorro novo: pronto pro inverno.', 'Modo foco silencioso: protetor de orelha ativado.'],
      acessorio_cachecol: ['Cachecol no lugar. Pronto pra qualquer clima.', 'Cachecol equipado. Estilo em dia.'],
      tarefa_concluida: ['Check! Registrado.', 'Tarefa fechada com sucesso.'],
      tarefa_criada: ['Tarefa adicionada ao plano.', 'Registrado: mais uma no radar.'],
      dia_concluido: ['Dia concluído: todos os circuitos em verde.'],
      toque_insistente: ['Cócegas na antena! Hihi... digo, bip.'],
      descanso: ['Modo descanso: energia economizada.'],
    },
    grao: {
      conquista: ['Cardápio novo: {item}.', 'Especial da casa liberado: {item}!', 'Novo item no cardápio: {item}.'],
      meta_concluida: ['Mais uma porção de {objetivo} servida.', '{objetivo}: {feitas} de {total} porções.', 'Porção servida! {objetivo} avançou.'],
      meta_metade: ['Metade das porções de {objetivo} já saiu da cozinha!', '{objetivo}: metade servida. O café está no ponto.'],
      objetivo_criado: ['Novo pedido no cardápio: {objetivo}. Que tal dividir em porções?', 'Pedido anotado: {objetivo}. Dá pra fragmentar, se ajudar.'],
      objetivo_pausado: ['Pedido em banho-maria. Retoma quando fizer sentido.', 'Objetivo pausado: o café fica quentinho na garrafa.'],
      tarefa_concluida: ['Servida! Mais uma xícara cheia.', 'Pedido entregue na mesa.', 'Uma a menos na fila do balcão.'],
      tarefa_criada: ['Pedido anotado!', 'Entrou no cardápio de hoje.'],
      dia_concluido: ['Balcão fechado: todos os pedidos de hoje foram servidos.'],
      tarefa_replanejada: ['Pedido remarcado: o café sai no horário certo.', 'Nova hora na comanda. Planejar também é servir bem.'],
      toque: ['Cuidado: conteúdo quente.', 'Quer coar um plano novo?'],
      toque_insistente: ['Calma, vai derramar!', 'Cuidado, tô quente!'],
      descanso: ['Café esfriando em paz. Descanso faz parte do cardápio.'],
      acessorio_gorro: ['Gorro de lã: o café esfria mais devagar.', 'Pompom no topo. Chique pra um expresso.'],
      acessorio_anjo: ['Asas e auréola: hoje o café é divino.', 'Anjo da guarda do cardápio, às ordens.', 'Um café celestial, a caminho.'],
      acessorio_jaqueta: ['Jaqueta com capuz felpudo: aguento qualquer inverno de máquina.', 'Quentinha por fora, quentinha por dentro.', 'Capuz felpudo ajustado. Café sem frio.'],
      acessorio_cachecol: ['Cachecol no lugar. Café agasalhado.', 'Cachecol de barista equipado.'],
    },
    boltz: {
      conquista: ['Troféu novo: {item}!', 'Direto pro vestiário: {item} desbloqueado.', 'Novo lance liberado: {item}.'],
      meta_concluida: ['Mais um fragmento de {objetivo} na rede.', '{objetivo}: {feitas} de {total} lances.', 'Fragmento concluído: {objetivo} avançou no placar.'],
      meta_metade: ['Fim do primeiro tempo de {objetivo}: metade cumprida!', 'Intervalo: metade de {objetivo} já está no placar.'],
      objetivo_criado: ['Novo jogo marcado: {objetivo}. Que tal montar a escalação em fragmentos?', 'Objetivo escalado: {objetivo}.'],
      objetivo_pausado: ['Jogo adiado. A tabela espera.', 'Objetivo no banco de reservas até você chamar.'],
      tarefa_concluida: ['Gol! Mais uma tarefa na rede.', 'Passe certeiro: tarefa concluída.', 'Essa entrou no placar.'],
      tarefa_criada: ['Jogada anotada na prancheta.', 'Tarefa escalada pro dia.'],
      dia_concluido: ['Apito final: todas as tarefas de hoje no placar!'],
      tarefa_replanejada: ['Mudança tática: tarefa remarcada pro melhor horário.', 'Substituição feita: nova data na escalação.'],
      toque: ['Bora aquecer? Alongamento antes do jogo.', 'Cabeceio, drible e planejamento: nessa ordem.'],
      toque_insistente: ['Cartão amarelo pra tanto toque!', 'Calma, juiz! Ainda tô no jogo.'],
      descanso: ['Intervalo no vestiário. Descanso também é tática.'],
      acessorio_gorro: ['Gorro de torcida na cabeça. Pompom e tudo.', 'Touca de inverno: jogo em campo gelado.'],
      acessorio_chuteira: ['Chuteira de ouro calçada. Aqui é craque.', 'Travas novas, brilho dourado.', 'Pisada de campeão: pronto pro jogo.'],
      acessorio_uniforme: ['Uniforme do time NEOCORTEX vestido!', 'Camisa do NEOCORTEX no corpo: time em campo.', 'Manto do NEOCORTEX vestido. Hora do jogo.'],
      acessorio_cachecol: ['Cachecol de torcedor no pescoço.', 'Cachecol erguido: a torcida tá presente.'],
    },
    rabisco: {
      conquista: ['Adesivo novo na página: {item}!', 'Item desbloqueado: {item}. Já colei no caderno.', 'Miau! {item} desbloqueado.'],
      meta_concluida: ['Mais uma tarefinha de {objetivo} riscada.', '{objetivo}: {feitas} de {total} riscadas.', 'Fragmento riscado! {objetivo} avançou.'],
      meta_metade: ['Metade de {objetivo} já está riscada!', 'Virei a página no meio de {objetivo}: metade feita.'],
      objetivo_criado: ['Capítulo novo: {objetivo}. Que tal dividir em páginas?', 'Anotei o objetivo: {objetivo}.'],
      objetivo_pausado: ['Marcador na página. Retomamos quando fizer sentido.', 'Objetivo guardado na gaveta do caderno.'],
      tarefa_concluida: ['Riscado com capricho!', 'Mais um item pro histórico do caderno.'],
      tarefa_criada: ['Rabisquei na lista.', 'Mais uma linha na página.'],
      dia_concluido: ['Caderno do dia fechado: tudo riscado!'],
      tarefa_replanejada: ['Apaguei e escrevi de novo: tarefa remarcada.', 'Nova data a lápis. Ajustar é normal.'],
      toque: ['Lápis atrás da orelha, prontidão total.', 'Quer que eu apague algo? Só se for a lápis.'],
      toque_insistente: ['Prrr! Cócegas no bigode!', 'Miau! Assim eu borro a página.'],
      descanso: ['Zzz... soneca de gato. A lista espera.'],
      descanso_caminha: ['Zzz... cochilo na caminha.', 'Prrr... soneca curta. A lista espera.', 'Caminha quentinha. Volto a anotar já já.'],
      acessorio_gorro: ['Gorrinho de gato: tá quentinho!', 'Pompom pra caçar? Só em pensamento.'],
      acessorio_capacete: ['Capacete de pedreiro: obra de planejamento em andamento!', 'Segurança em primeiro lugar, inclusive na lista.', 'Hora de construir a semana, tijolo por tijolo.'],
      acessorio_prancheta: ['Prancheta na pata: vistoria da lista de hoje.', 'Checklist em mãos. Item por item.', 'Anotando tudo na prancheta!'],
      acessorio_caminha: ['Caminha montada! Cochilo com estilo liberado.', 'Minha caminha. Em dia livre, eu tiro uma soneca aqui.', 'Caminha instalada. Soneca com vista pra lista.'],
      acessorio_cachecol: ['Cachecol de gato: elegância felina.', 'Cachecol no lugar. Prrr.'],
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
    acessorio:          { etapas: [['toque', 'feliz', 1600]], particulas: 8 },   // ao equipar um acessório na Loja
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
      this.personalizar(opcoes.visual || { acessorio: raiz.dataset.acessorio, cor: raiz.dataset.cor, brilho: raiz.dataset.brilho });   // [PERSONALIZAR]
      this._aplicar('neutro', 'neutra');

      const botao = raiz.querySelector('.nc-mascote-botao');
      // [ATALHO] com mouse: passar por cima mostra a dica e clicar abre o Assistente.
      // Em tela de toque (sem hover) tocar continua mostrando a dica; no teclado, a dica aparece ao focar e Enter abre o Assistente.
      if (botao) {
        const semHover = () => !!(window.matchMedia && window.matchMedia('(hover: none)').matches);
        botao.addEventListener('mouseenter', () => { if (!semHover()) this._aoTocar(); });
        botao.addEventListener('focus', () => { if (botao.matches(':focus-visible')) this._aoTocar(); });
        botao.addEventListener('click', () => {
          const destino = raiz.dataset.assistenteUrl;
          if (semHover() || !destino) this._aoTocar();
          else window.location.href = destino;
        });
      }
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
      if (tipo === 'acessorio') {   // fala própria do item (do mascote atual); se não houver, a genérica
        frase = this._escolherFrase(`acessorio_${dados.id || ''}`, dados) || this._escolherFrase('acessorio', dados);
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
        const tipoFala = this.raiz.dataset.acessorio === 'caminha' && this._frasesDe('descanso_caminha').length ? 'descanso_caminha' : 'descanso';
        this._falar(this._escolherFrase(tipoFala, {}), true);
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
      // próprias do mascote + acrescentadas (FRASES_EXTRA). Sem nenhuma das duas, cai nas falas do robô.
      const proprias = FRASES_SKIN[this.skin] && FRASES_SKIN[this.skin][tipo];
      const extras = FRASES_EXTRA[this.skin] && FRASES_EXTRA[this.skin][tipo];
      const base = proprias || (this.skin === 'robo' || !extras ? FRASES[tipo] : null) || [];
      return extras ? base.concat(extras) : base;
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

    // [CAMINHA] com a caminha equipada, num dia SEM nenhuma tarefa planejada o gato tira uma soneca nela.
    // Reage ao plano do dia (não à ausência da pessoa). Um toque o acorda por um instante.
    const gato = vivos.find((m) => m.modo === 'normal');
    const dia = window.NC_SAUDACAO_DADOS || {};
    if (gato && !iniciais.length && gato.raiz.dataset.acessorio === 'caminha' && temValor(dia.total) && Number(dia.total) === 0) {
      setTimeout(() => gato.setDescanso(true), 3800);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();