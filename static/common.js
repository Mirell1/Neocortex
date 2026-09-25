/* ===================== common.js ===================== */
/* Compartilhado por TODAS as páginas: persistência de dados (localStorage), */
/* modo escuro, e helpers usados em mais de uma página.                     */

const STORAGE_KEY = 'neocortex_data_v1';

const DEFAULT_TASKS = [
  { id: 1, title: 'Reunião de alinhamento', time: '09:00', done: true, status: 'concluída', color: '#22C55E' },
  { id: 2, title: 'Revisar relatório trimestral', time: '11:00', done: true, status: 'concluída', color: '#22C55E' },
  { id: 3, title: 'Almoço com equipe de produto', time: '12:30', done: true, status: 'concluída', color: '#22C55E' },
  { id: 4, title: 'Sessão de planejamento semanal', time: '14:00', done: true, status: 'concluída', color: '#22C55E' },
  { id: 5, title: 'Code review — PR #247', time: '15:30', done: true, status: 'concluída', color: '#22C55E' },
  { id: 6, title: 'Academia — musculação', time: '18:00', done: false, status: 'agendada', color: '#2563EB' },
  { id: 7, title: 'Leitura — 30 minutos', time: '21:00', done: false, status: 'lembrete ativo', color: '#F59E0B' },
  { id: 8, title: 'Revisar amanhã', time: '22:00', done: false, status: 'agendada', color: '#2563EB' },
];

const DEFAULT_ACTIVITIES = [
  { id: 1, title: 'Revisar TCC — cap. 3', time: '09:00', cat: 'Estudos', done: true, status: 'concluída', color: '#22C55E' },
  { id: 2, title: 'Reunião com equipe de design', time: '14:00', cat: 'Trabalho', done: false, status: 'agendada', color: '#2563EB' },
  { id: 3, title: 'Academia', time: '18:30', cat: 'Saúde', done: false, status: 'lembrete ativo', color: '#F59E0B' },
  { id: 4, title: 'Responder e-mails pendentes', time: '', cat: 'Trabalho', done: false, status: 'agendada', color: '#2563EB' },
];

function ncDefaultData() {
  return {
    dark: false,
    username: 'Ana',
    userPassword: '123456',
    tasks: DEFAULT_TASKS,
    activityTasks: DEFAULT_ACTIVITIES,
    settingsState: { notifications: true, reminder: '15 min antes' },
    loggedIn: false,
  };
}

function ncLoad() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return ncDefaultData();
    const data = JSON.parse(raw);
    return Object.assign(ncDefaultData(), data);
  } catch (e) {
    return ncDefaultData();
  }
}

function ncSave(data) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch (e) { /* localStorage indisponível */ }
}

/* Aplica o modo escuro salvo assim que a página carrega (evita "flash" de tema errado) */
(function ncApplyDarkOnLoad() {
  const data = ncLoad();
  if (data.dark) document.documentElement.classList.add('dark');
})();

function ncToggleDark() {
  const data = ncLoad();
  data.dark = !data.dark;
  ncSave(data);
  document.documentElement.classList.toggle('dark', data.dark);
  document.querySelectorAll('[data-dark-toggle]').forEach(el => el.classList.toggle('on', data.dark));
}

function ncInitials(name) {
  return (name || '?').charAt(0).toUpperCase();
}

function ncNowTime() {
  return new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

/* Protege páginas internas: se a pessoa não passou pelo login nessa sessão, manda pro index. */
function ncRequireLogin() {
  const data = ncLoad();
  if (!data.loggedIn) window.location.href = 'index.html';
}

function ncLogout() {
  const data = ncLoad();
  data.loggedIn = false;
  ncSave(data);
  window.location.href = 'index.html';
}

/* Preenche nome/avatar em qualquer elemento marcado com data-username / data-avatar-initial */
function ncFillUserBits() {
  const data = ncLoad();
  document.querySelectorAll('[data-username]').forEach(el => el.textContent = data.username);
  document.querySelectorAll('[data-avatar-initial]').forEach(el => el.textContent = ncInitials(data.username));
}
document.addEventListener('DOMContentLoaded', ncFillUserBits);
