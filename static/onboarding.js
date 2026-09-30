/*
 * NEOCORTEX — onboarding.js
 * Fluxo provisório, orientado a dados.
 *
 * A ideia é manter perguntas e aparência separadas:
 * quando a equipe fechar o questionário oficial, alteramos o objeto
 * onboardingFlow sem precisar reconstruir a interface.
 */

const onboardingFlow = {
  areas_melhoria: {
    type: "multiple",
    title: "O que você gostaria de organizar melhor?",
    description: "Pode escolher mais de uma área.",
    messageTitle: "Vamos começar pelo seu contexto.",
    message: "Não existe rotina perfeita aqui. Quero entender onde sua organização mais pesa hoje.",
    options: [
      { value: "estudos", label: "Estudos", description: "Faculdade, escola, cursos e provas." },
      { value: "trabalho", label: "Trabalho", description: "Expediente, tarefas e compromissos." },
      { value: "vida_pessoal", label: "Vida pessoal", description: "Casa, compromissos e tempo para você." }
    ],
    next: "idade"
  },

  idade: {
    type: "single",
    title: "Qual é a sua faixa etária?",
    description: "Isso ajuda a contextualizar sua rotina.",
    messageTitle: "Agora eu preciso de um pouco de contexto.",
    message: "Só o suficiente para entender o momento de vida em que sua rotina acontece.",
    options: [
      { value: "18_24", label: "18 a 24 anos" },
      { value: "25_34", label: "25 a 34 anos" },
      { value: "35_44", label: "35 a 44 anos" },
      { value: "45_plus", label: "45 anos ou mais" }
    ],
    next: "trabalha"
  },

  trabalha: {
    type: "single",
    title: "Você trabalha atualmente?",
    description: "Se sim, vou entender o turno para que o horário não precise ser digitado manualmente.",
    messageTitle: "Vamos encaixar o trabalho no seu ritmo.",
    message: "Você me diz o turno; eu parto de uma estimativa de horário.",
    options: [
      { value: "sim", label: "Sim", next: "turno_trabalho" },
      { value: "nao", label: "Não", next: "estuda" }
    ]
  },

  turno_trabalho: {
    type: "single",
    title: "Qual é o seu turno de trabalho?",
    description: "Os horários abaixo são estimativas. Se nenhum representar sua rotina, escolha Personalizar.",
    messageTitle: "Uma estimativa já resolve boa parte do trabalho.",
    message: "Assim você não precisa preencher horas de entrada e saída toda vez.",
    options: [
      { value: "manha", label: "Manhã", description: "06:00 às 14:00" },
      { value: "intermediario", label: "Intermediário", description: "10:00 às 18:00" },
      { value: "tarde", label: "Tarde", description: "14:00 às 22:00" },
      { value: "noite", label: "Noite", description: "22:00 às 06:00" },
      { value: "personalizado", label: "Personalizar", description: "Defina seu próprio horário.", next: "horario_trabalho_personalizado" }
    ],
    nextByValue: {
      manha: "dias_trabalho",
      intermediario: "dias_trabalho",
      tarde: "dias_trabalho",
      noite: "dias_trabalho",
      personalizado: "horario_trabalho_personalizado"
    }
  },

  horario_trabalho_personalizado: {
    type: "time",
    title: "Qual é o seu horário de trabalho?",
    description: "Aqui você só precisa informar o horário se escolheu Personalizar.",
    messageTitle: "Tudo bem fugir do padrão.",
    message: "Se o seu turno é diferente, me passe apenas o intervalo.",
    next: "dias_trabalho"
  },

  dias_trabalho: {
    type: "days",
    title: "Em quais dias você trabalha?",
    description: "Selecione todos os dias que fazem parte da sua rotina.",
    messageTitle: "Agora vamos marcar os dias.",
    message: "Isso ajuda a não ocupar com tarefas um período que já está comprometido.",
    next: "estuda"
  },

  estuda: {
    type: "single",
    title: "Você estuda atualmente?",
    description: "Faculdade, escola, curso técnico, idiomas ou outro tipo de estudo.",
    messageTitle: "E o estudo?",
    message: "Quero separar o que é obrigação do que precisa continuar cabendo na sua vida.",
    options: [
      { value: "sim", label: "Sim", next: "tipo_estudo" },
      { value: "nao", label: "Não", next: "possui_hobbies" }
    ]
  },

  tipo_estudo: {
    type: "single",
    title: "Onde você estuda?",
    description: "Escolha o tipo que mais representa sua rotina.",
    messageTitle: "Só mais um pedaço do seu contexto.",
    message: "Não precisa explicar tudo ainda.",
    options: [
      { value: "faculdade", label: "Faculdade / universidade" },
      { value: "escola", label: "Escola" },
      { value: "curso_tecnico", label: "Curso técnico / profissionalizante" },
      { value: "idiomas", label: "Idiomas" },
      { value: "outro", label: "Outro" }
    ],
    next: "horario_estudo"
  },

  horario_estudo: {
    type: "time",
    title: "Em que horário você costuma estudar?",
    description: "Use uma estimativa. Isso é suficiente para o protótipo.",
    messageTitle: "Vamos reservar espaço para aprender.",
    message: "O objetivo é entender quando seu cérebro costuma lidar com essa parte da rotina.",
    next: "dias_estudo"
  },

  dias_estudo: {
    type: "days",
    title: "Em quais dias você estuda?",
    description: "Selecione todos os dias que se aplicam.",
    messageTitle: "Quase fechando o mapa da rotina.",
    message: "Depois disso, quero saber o que você faz quando não está cumprindo obrigação.",
    next: "possui_hobbies"
  },

  possui_hobbies: {
    type: "single",
    title: "Você tem hobbies ou atividades de lazer?",
    description: "Não precisa ser algo produtivo. É justamente o tempo fora das obrigações que importa aqui.",
    messageTitle: "Sua rotina também precisa ter espaço para você.",
    message: "Lazer não entra como prêmio por terminar tudo. Ele faz parte da rotina.",
    options: [
      { value: "sim", label: "Sim", next: "frequencia_hobbies" },
      { value: "nao", label: "Ainda não", next: "pico_energia" }
    ]
  },

  frequencia_hobbies: {
    type: "single",
    title: "Com que frequência você costuma ter esse tempo?",
    description: "Uma estimativa já basta.",
    messageTitle: "Quero entender esse espaço.",
    message: "Assim o NEOCORTEX pode considerar lazer ao montar sugestões de rotina.",
    options: [
      { value: "diariamente", label: "Quase todos os dias" },
      { value: "algumas_vezes", label: "Algumas vezes por semana" },
      { value: "semanalmente", label: "Uma vez por semana" },
      { value: "raramente", label: "Raramente" }
    ],
    next: "hobbies"
  },

  hobbies: {
    type: "multiple",
    title: "Quais atividades você gosta?",
    description: "Pode selecionar várias. Se não encontrar uma, escolha Personalizar.",
    messageTitle: "Agora vem a parte que deixa a rotina mais sua.",
    message: "Não quero preencher seu tempo por preencher. Quero saber o que faz sentido para você.",
    options: [
      { value: "academia", label: "Academia" },
      { value: "ler", label: "Ler" },
      { value: "passear", label: "Passear" },
      { value: "musica", label: "Música" },
      { value: "filmes_series", label: "Filmes e séries" },
      { value: "luta", label: "Luta / artes marciais" },
      { value: "voluntariado", label: "Voluntariado" },
      { value: "cozinhar", label: "Cozinhar" },
      { value: "personalizado", label: "Personalizar", description: "Adicionar outra atividade." }
    ],
    next: "sugestoes_hobbies"
  },

  sugestoes_hobbies: {
    type: "single",
    title: "Você gostaria de receber sugestões de hobbies?",
    description: "O NEOCORTEX poderá considerar seus interesses e seu tempo disponível.",
    messageTitle: "Último detalhe sobre lazer.",
    message: "Você decide se quer descobrir coisas novas ou manter apenas o que já gosta.",
    options: [
      { value: "sim", label: "Sim, quero sugestões" },
      { value: "nao", label: "Não, prefiro escolher sozinho" }
    ],
    next: "pico_energia"
  },

    pico_energia: {
    type: "single",
    title: "Em que período do dia você rende mais?",
    description: "Pense nos momentos em que foco e disposição vêm mais fácil, não em quando você acha que deveria render.",
    messageTitle: "Seu ritmo, não o dos outros.",
    message: "Vou usar isso para sugerir as tarefas mais exigentes quando você tem mais disposição.",
    options: [
      { value: "manha", label: "Manhã", description: "Do começo do dia até o almoço." },
      { value: "tarde", label: "Tarde", description: "Depois do almoço até o fim da tarde." },
      { value: "noite", label: "Noite", description: "Do fim da tarde em diante." },
      { value: "nao_sei", label: "Varia ou ainda não sei", description: "Sem problema, dá para descobrir com o tempo." }
    ],
    next: "tempo_organizacao"
  },

  tempo_organizacao: {
    type: "single",
    title: "Quanto tempo você costuma dedicar à organização?",
    description: "Pense no que realmente acontece hoje, não no que você gostaria que acontecesse.",
    messageTitle: "Sem cobrança.",
    message: "Quero a sua rotina real. É ela que precisa caber no sistema.",
    options: [
      { value: "quase_nunca", label: "Quase nunca" },
      { value: "poucos_minutos", label: "Alguns minutos por dia" },
      { value: "alguns_dias", label: "Alguns dias da semana" },
      { value: "frequente", label: "Todos ou quase todos os dias" }
    ],
    next: "tempo_neocortex"
  },

  tempo_neocortex: {
    type: "single",
    title: "Quanto tempo você gostaria de dedicar ao NEOCORTEX?",
    description: "Isso ajuda a calibrar a quantidade de interação.",
    messageTitle: "E quanto espaço eu posso ocupar?",
    message: "A ideia é ajudar sem virar mais uma tarefa para você administrar.",
    options: [
      { value: "rapido", label: "1 a 3 minutos por dia" },
      { value: "moderado", label: "5 a 10 minutos por dia" },
      { value: "flexivel", label: "Quando eu precisar" },
      { value: "nao_sei", label: "Ainda não sei" }
    ],
    next: "personalizacao"
  },

  personalizacao: {
    type: "textarea",
    title: "Tem algo importante que você gostaria que eu soubesse?",
    description: "Essa etapa é opcional. Pode escrever do seu jeito.",
    messageTitle: "Última pergunta. Prometo.",
    message: "Se existir algo que não coube nas opções, esse é o espaço para colocar.",
    placeholder: "Ex.: tenho horários muito variáveis, faço plantão, cuido de alguém...",
    optional: true,
    next: "fim"
  },

  fim: {
    type: "finish",
    messageTitle: "Agora eu tenho um mapa inicial.",
    message: "A partir daqui, o NEOCORTEX pode começar a transformar suas informações em uma rotina possível — não em mais uma lista impossível."
  }
};

Object.keys(onboardingFlow).forEach((id) => {
  onboardingFlow[id].id = id;
});

const state = {
  currentQuestionId: "areas_melhoria",
  history: [],
  answers: {}
};

const progressSequence = [
  "areas_melhoria",
  "idade",
  "trabalha",
  "turno_trabalho",
  "horario_trabalho_personalizado",
  "dias_trabalho",
  "estuda",
  "tipo_estudo",
  "horario_estudo",
  "dias_estudo",
  "possui_hobbies",
  "frequencia_hobbies",
  "hobbies",
  "sugestoes_hobbies",
  "pico_energia",
  "tempo_organizacao",
  "tempo_neocortex",
  "personalizacao"
];

const els = {
  back: document.getElementById("backButton"),
  progress: document.getElementById("progressBar"),
  number: document.getElementById("questionNumber"),
  total: document.getElementById("questionTotal"),
  title: document.getElementById("questionTitle"),
  description: document.getElementById("questionDescription"),
  options: document.getElementById("optionsContainer"),
  custom: document.getElementById("customInputContainer"),
  validation: document.getElementById("validationMessage"),
  continue: document.getElementById("continueButton"),
  footerHint: document.getElementById("footerHint"),
  messageTitle: document.getElementById("messageTitle"),
  messageText: document.getElementById("messageText")
};

function getQuestion() {
  return onboardingFlow[state.currentQuestionId];
}

function saveState() {
  try {
    localStorage.setItem("neocortex_onboarding_progresso", JSON.stringify(state.answers));
  } catch (e) {}
}

function resolveNext(question, answer) {
  if (question.nextByValue && question.nextByValue[answer]) {
    return question.nextByValue[answer];
  }

  const selected = question.options?.find(option => option.value === answer);
  if (selected?.next) return selected.next;

  return question.next;
}

function getPathSoFar() {
  const ids = [];
  let id = "areas_melhoria";
  const seen = new Set();

  while (id && onboardingFlow[id] && !seen.has(id) && id !== "fim") {
    seen.add(id);
    ids.push(id);

    const question = onboardingFlow[id];
    const answer = state.answers[id];

    if (question.type === "multiple") {
      id = question.next;
    } else if (answer !== undefined) {
      id = resolveNext(question, answer);
    } else {
      id = question.next;
    }
  }

  return ids;
}

function getProgress() {
  const path = getPathSoFar();
  const currentIndex = Math.max(path.indexOf(state.currentQuestionId), 0);
  const estimatedTotal = Math.max(path.length, progressSequence.length);
  return {
    current: Math.min(currentIndex + 1, estimatedTotal),
    total: estimatedTotal
  };
}

function clearValidation() {
  els.validation.textContent = "";
}

function setMessage(question) {
  els.messageTitle.textContent = question.messageTitle || "Vamos por partes.";
  els.messageText.textContent = question.message || "Uma pergunta de cada vez.";
}

function renderQuestion() {
  const question = getQuestion();
  if (!question) return;

  const progress = getProgress();

  els.number.textContent = progress.current;
  els.total.textContent = progress.total;
  els.progress.style.width = `${Math.min(100, (progress.current / progress.total) * 100)}%`;

  els.title.textContent = question.title || "";
  els.description.textContent = question.description || "";
  setMessage(question);

  els.options.innerHTML = "";
  els.custom.innerHTML = "";
  clearValidation();

  if (question.type === "finish") {
    renderFinish();
    return;
  }

  if (question.type === "single" || question.type === "multiple") {
    renderOptions(question);
  } else if (question.type === "days") {
    renderDays(question);
  } else if (question.type === "time") {
    renderTime(question);
  } else if (question.type === "textarea") {
    renderTextarea(question);
  }

  updateContinueButton();
}

const ICON_MAP = {
  estudos: "📚", trabalho: "💼", vida_pessoal: "🏡",
  "18_24": "🎓", "25_34": "💻", "35_44": "🧑‍💼", "45_plus": "🌿",
  sim: "✅", nao: "➡️",
  manha: "🌅", intermediario: "🌤️", tarde: "🌇", noite: "🌙", personalizado: "⚙️",
  faculdade: "🎓", escola: "🏫", curso_tecnico: "🛠️", idiomas: "🗣️", outro: "✨",
  diariamente: "🔥", algumas_vezes: "📅", semanalmente: "🗓️", raramente: "🌾",
  academia: "🏋️", ler: "📖", passear: "🚶", musica: "🎵", filmes_series: "🎬",
  luta: "🥋", voluntariado: "🤝", cozinhar: "🍳",
  quase_nunca: "😅", poucos_minutos: "⏱️", alguns_dias: "📆", frequente: "✅",
  rapido: "⚡", moderado: "🕐", flexivel: "🌊", nao_sei: "🤔",
};

function renderOptions(question) {
  els.options.innerHTML = "";
  const previous = state.answers[question.id];

  question.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `onboarding-option ${question.type === "multiple" ? "multiple" : ""}`;

    const isSelected = question.type === "multiple"
      ? Array.isArray(previous) && previous.includes(option.value)
      : previous === option.value;

    if (isSelected) button.classList.add("selected");

    const icone = ICON_MAP[option.value] || "•";

    button.innerHTML = `
      <span class="option-index">${icone}</span>
      <span class="option-copy">
        <span class="option-label"></span>
        ${option.description ? '<span class="option-description"></span>' : ""}
      </span>
      <span class="option-check" aria-hidden="true">✓</span>
    `;

    button.querySelector(".option-label").textContent = option.label;
    if (option.description) {
      button.querySelector(".option-description").textContent = option.description;
    }

    button.addEventListener("click", () => {
      if (question.type === "multiple") {
        const current = Array.isArray(state.answers[question.id])
          ? [...state.answers[question.id]]
          : [];

        const indexOfValue = current.indexOf(option.value);
        if (indexOfValue >= 0) current.splice(indexOfValue, 1);
        else current.push(option.value);

        state.answers[question.id] = current;

        if (option.value === "personalizado" && current.includes("personalizado")) {
          renderCustomHobbyInput();
        } else if (question.id === "hobbies") {
          removeCustomHobbyInput();
        }

        renderOptions(question);
      } else {
        state.answers[question.id] = option.value;

        if (question.id === "turno_trabalho" && option.value !== "personalizado") {
          state.answers.horario_trabalho_estimado = getEstimatedWorkHours(option.value);
        }

        renderOptions(question);
      }

      clearValidation();
      updateContinueButton();
    });

    els.options.appendChild(button);
  });

  if (question.id === "hobbies" && Array.isArray(previous) && previous.includes("personalizado")) {
    renderCustomHobbyInput();
  }
}

function renderCustomHobbyInput() {
  const value = state.answers.hobby_personalizado || "";

  els.custom.innerHTML = `
    <label class="custom-label" for="customHobby">Qual hobby você quer adicionar?</label>
    <input
      id="customHobby"
      class="custom-text-input"
      type="text"
      maxlength="80"
      placeholder="Ex.: desenhar, jogar, fotografia..."
      value="${escapeHtml(value)}"
    >
  `;

  const input = document.getElementById("customHobby");
  input.addEventListener("input", () => {
    state.answers.hobby_personalizado = input.value;
    updateContinueButton();
  });
}

function removeCustomHobbyInput() {
  delete state.answers.hobby_personalizado;
  els.custom.innerHTML = "";
}

function renderDays(question) {
  const days = [
    ["seg", "Seg"],
    ["ter", "Ter"],
    ["qua", "Qua"],
    ["qui", "Qui"],
    ["sex", "Sex"],
    ["sab", "Sáb"],
    ["dom", "Dom"]
  ];

  const previous = Array.isArray(state.answers[question.id])
    ? state.answers[question.id]
    : [];

  const grid = document.createElement("div");
  grid.className = "day-grid";

  days.forEach(([value, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "day-button";
    button.textContent = label;

    if (previous.includes(value)) button.classList.add("selected");

    button.addEventListener("click", () => {
      const current = Array.isArray(state.answers[question.id])
        ? [...state.answers[question.id]]
        : [];

      const index = current.indexOf(value);
      if (index >= 0) current.splice(index, 1);
      else current.push(value);

      state.answers[question.id] = current;
      button.classList.toggle("selected", current.includes(value));
      clearValidation();
      updateContinueButton();
    });

    grid.appendChild(button);
  });

  els.options.appendChild(grid);
}

function renderTime(question) {
  const previous = state.answers[question.id] || {};
  const [prevStartH, prevStartM] = (previous.start || "").split(":");
  const [prevEndH, prevEndM] = (previous.end || "").split(":");

  const horas = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0"));
  const minutos = ["00", "10", "20", "30", "40", "50"];

  const opcoesHora = (selecionada) =>
    horas.map((h) => `<option value="${h}" ${h === selecionada ? "selected" : ""}>${h}h</option>`).join("");
  const opcoesMinuto = (selecionado) =>
    minutos.map((m) => `<option value="${m}" ${m === selecionado ? "selected" : ""}>${m}</option>`).join("");

  els.custom.innerHTML = `
    <div class="time-range">
      <div style="display:flex;gap:6px;">
        <select class="time-field" id="timeStartH">${opcoesHora(prevStartH)}</select>
        <select class="time-field" id="timeStartM">${opcoesMinuto(prevStartM)}</select>
      </div>
      <div class="time-separator">até</div>
      <div style="display:flex;gap:6px;">
        <select class="time-field" id="timeEndH">${opcoesHora(prevEndH)}</select>
        <select class="time-field" id="timeEndM">${opcoesMinuto(prevEndM)}</select>
      </div>
    </div>
  `;

  const startH = document.getElementById("timeStartH");
  const startM = document.getElementById("timeStartM");
  const endH = document.getElementById("timeEndH");
  const endM = document.getElementById("timeEndM");

  const sync = () => {
    state.answers[question.id] = {
      start: `${startH.value}:${startM.value}`,
      end: `${endH.value}:${endM.value}`
    };
    clearValidation();
    updateContinueButton();
  };

  [startH, startM, endH, endM].forEach((el) => el.addEventListener("change", sync));
}

function renderTextarea(question) {
  const value = state.answers[question.id] || "";

  els.custom.innerHTML = `
    <textarea
      id="personalizationText"
      class="custom-textarea"
      maxlength="500"
      placeholder="${question.placeholder || ""}"
    >${escapeHtml(value)}</textarea>
  `;

  const textarea = document.getElementById("personalizationText");
  textarea.addEventListener("input", () => {
    state.answers[question.id] = textarea.value;
    clearValidation();
    updateContinueButton();
  });
}

function getEstimatedWorkHours(value) {
  const estimates = {
    manha: { start: "06:00", end: "14:00" },
    intermediario: { start: "10:00", end: "18:00" },
    tarde: { start: "14:00", end: "22:00" },
    noite: { start: "22:00", end: "06:00" }
  };

  return estimates[value] || null;
}

function isValid(question) {
  const answer = state.answers[question.id];

  if (question.optional) return true;

  if (question.type === "multiple" || question.type === "days") {
    return Array.isArray(answer) && answer.length > 0;
  }

  if (question.type === "time") {
    return Boolean(answer?.start && answer?.end);
  }

  return Boolean(answer);
}

function validateSpecialCases(question) {
  if (question.id === "hobbies") {
    const selected = state.answers.hobbies || [];
    if (selected.includes("personalizado") && !String(state.answers.hobby_personalizado || "").trim()) {
      els.validation.textContent = "Digite o nome do hobby personalizado para continuar.";
      return false;
    }
  }

  return true;
}

function updateContinueButton() {
  const question = getQuestion();
  if (!question || question.type === "finish") return;

  const valid = isValid(question) && validateSpecialCases(question);
  els.continue.disabled = !valid;

  els.footerHint.textContent = valid
    ? "Pronto. Você pode continuar."
    : question.optional
      ? "Essa etapa é opcional."
      : "Escolha uma opção para continuar.";
}

function goNext() {
  const question = getQuestion();

  if (!isValid(question)) {
    els.validation.textContent = question.optional
      ? ""
      : "Selecione uma resposta antes de continuar.";
    return;
  }

  if (!validateSpecialCases(question)) return;

  const answer = state.answers[question.id];
  const nextId = resolveNext(question, Array.isArray(answer) ? answer[0] : answer);

  if (!nextId) return;

  state.history.push(state.currentQuestionId);
  state.currentQuestionId = nextId;
  saveState();
  renderQuestion();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function goBack() {
  if (state.history.length === 0) {
    window.history.back();
    return;
  }

  const previousId = state.history.pop();
  state.currentQuestionId = previousId;
  renderQuestion();
}

function renderFinish() {
  els.options.innerHTML = `
    <div class="finish-card">
      <div class="finish-mark">✓</div>
      <h2>Seu mapa inicial está pronto.</h2>
      <p>Vamos criar sua conta com essas informações.</p>
    </div>
  `;
  els.custom.innerHTML = "";
  els.continue.disabled = false;
  els.continue.textContent = "Criar minha conta →";
  els.footerHint.textContent = "Última etapa.";

  els.continue.onclick = async () => {
    els.continue.disabled = true;
    els.continue.textContent = "Criando conta...";

    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    try {
      const resposta = await fetch(window.location.pathname, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify(state.answers),
      });
      const resultado = await resposta.json();

      if (!resposta.ok) {
        els.footerHint.textContent = resultado.erro || "Algo deu errado. Tente novamente.";
        els.continue.disabled = false;
        els.continue.textContent = "Criar minha conta →";
        return;
      }

      localStorage.removeItem("neocortex_onboarding_progresso");
      window.location.href = resultado.redirect;
    } catch (e) {
      els.footerHint.textContent = "Não foi possível conectar ao servidor.";
      els.continue.disabled = false;
      els.continue.textContent = "Criar minha conta →";
    }
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

els.continue.addEventListener("click", goNext);
els.back.addEventListener("click", goBack);

renderQuestion();
