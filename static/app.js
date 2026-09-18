// NEOCORTEX — pequenas interações da interface (não fala com o banco diretamente)

// Troca entre a aba "Entrar" e "Criar conta" na tela de login, sem recarregar a página
function mostrarAba(aba) {
  const formLogin = document.getElementById("form-login");
  const formCadastro = document.getElementById("form-cadastro");
  if (!formLogin || !formCadastro) return;

  const abas = document.querySelectorAll(".tab");

  if (aba === "cadastro") {
    formLogin.style.display = "none";
    formCadastro.style.display = "block";
    abas[0].classList.remove("active");
    abas[1].classList.add("active");
  } else {
    formLogin.style.display = "block";
    formCadastro.style.display = "none";
    abas[0].classList.add("active");
    abas[1].classList.remove("active");
  }
}

// Deixa os "chips" (faixa etária, ocupação, turno) visualmente marcados ao clicar
document.addEventListener("click", function (evento) {
  const chip = evento.target.closest(".chip");
  if (!chip) return;

  const input = chip.querySelector("input[type=radio]");
  if (!input) return;

  // Desmarca visualmente os outros chips do mesmo grupo (mesmo "name")
  const grupo = document.querySelectorAll(`input[name="${input.name}"]`);
  grupo.forEach((i) => i.closest(".chip").classList.remove("active"));

  chip.classList.add("active");
});

// Fecha o modal de nova tarefa se clicar fora dele
document.addEventListener("click", function (evento) {
  const modal = document.getElementById("modal-tarefa");
  if (modal && evento.target === modal) {
    modal.style.display = "none";
  }
});
