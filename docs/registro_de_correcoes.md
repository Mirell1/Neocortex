# Registro de correções — relatório de avaliação de 18/10/2026

Este registro segue a regra do próprio relatório: **um item só é marcado como corrigido quando há teste que prove**, e o que continua
aberto fica escrito como limite. "Corrigido em ambiente de teste" quer dizer: a mudança existe num script que ainda **não foi
aplicado ao repositório**; passa a valer quando o script for rodado e o `verificar_pacote.py` e o teste manual confirmarem.

Ordem de aplicação dos pacotes pendentes: **1.** segurança → **2.** caixa do assistente → **3.** objetivo no onboarding (v2) → **4.** este lote 1.

## Lote 1 (`corrigir_lote1.py`)

| Item | O que mudou | Evidência (antes → depois) | Limite que sobra |
|---|---|---|---|
| 32 Conta parcial no cadastro | O cadastro confere horários e listas **antes** de criar a conta | Horário sem início: HTTP 500 com 1 conta criada → HTTP 400, 0 contas. Também: hora 25, texto, número, lista no lugar de objeto | Se o **banco** falhar no meio (depois de criar a conta), ainda não há transação: exigiria mudar o `db.py` |
| 35 "Livre" | O dia sem tarefas diz "sem tarefas" | Texto e sintaxe do JS conferidos | Não calcula disponibilidade real (rotina, compromissos) |
| 36 Filtro de categoria | A rota lê `categoria`, valida e filtra; o seletor mostra a escolha | `?categoria=estudo` mostrava tarefa de trabalho → só estudo; categoria inventada vira "todas" | — |
| 37 Hoje × Agenda | "Hoje" inclui tarefas que começaram antes e seguem ativas | Plantão que atravessa a meia-noite: sumia → aparece. Terminou à meia-noite exata: não aparece | Olha até 7 dias para trás; tarefa mais longa que isso não entra no "Hoje" |
| 48 Passos passavam do prazo | Passos distribuídos entre amanhã e o prazo | Prazo amanhã: propunha semanas depois → propõe amanhã. **Prazo de ~8 anos (o carro de 2035): os 12 passos ficavam no primeiro mês → agora vão até o prazo, em ordem e espaçados** | O conteúdo dos passos (tarefas de 30 a 60 min geradas pela IA) foi pensado para prazos curtos; em prazos de anos o ideal seria propor **marcos**. Isso depende do `ai.py` atual |
| 49 Ritmos iguais | O ritmo define o espaçamento mínimo (1, 2 ou 3 dias) | Prazo em 6 dias, 5 passos: curto e frequente = 5, longo e espaçado = 2 (de 60 min) | O espaçamento é uma meta: com a agenda apertada, passos podem ficar mais próximos |
| (achado ao aplicar, **não está no relatório**) Opções de foco e ritmo não marcavam nada | Clicar marca só a opção clicada em cada grupo; "Geral" e "Moderado" já vêm marcados, com ✓ além da cor; a janela volta ao padrão ao reabrir | Antes: nada ficava marcado e o servidor **sempre** recebia `foco=geral&ritmo=moderado`. Agora: marca o que se clica e recebe `foco=teoria&ritmo=curto_frequente` (conferido no navegador e na chamada à IA) | Isso também tornava o item 49 (ritmos) inalcançável pela tela: só passa a valer com este ajuste |
| 50 Horário das 9h inventado | Sem janela livre não há proposta; a tela explica | Agenda lotada: 9h inventado → erro 409 "libere espaço na agenda". Parcial: "só encontrei horário para 2 de 4" | **Não revalida na confirmação** se o horário continua livre (exige a API de conflitos do `agenda.py`/`servicos.py` atual) |
| 51 Apóstrofo no botão | O título vai como JSON seguro no atributo | `d'Artagnan "x" </script>`: o clique não abria nada → abre a janela para o objetivo certo | — |
| 52 HTML da IA na prévia | A prévia escapa os textos; mostra aviso; mostra erro de confirmação | Título `<img onerror>`: entrava como HTML → aparece como texto, nada executa. Confirmação com erro: botão preso → mensagem e botão liberado | A prévia **ainda não é editável** (título, data, duração) |
| 53 Confirmação parcial | Confere a lista **inteira** antes de gravar; confere o dono do objetivo; objetivo novo só é criado se todos os passos forem válidos | Item ruim no fim: HTTP 500 com 1 passo gravado → HTTP 400, 0 gravados. Objetivo de outra pessoa: 404 | Sem transação no banco: uma falha do **banco** no meio ainda pode deixar parte gravada |
| 72 Datas e senha | Prazo de objetivo (criar e editar) validado: 400 em vez de 500 | `31/02`, `abc`, mês 13, mais de 10 anos: 500 → 400 | A parte da **senha longa** está no pacote de segurança (ainda não aplicado) |

Testes: `teste_lote1_servidor.py` (73 verificações), `teste_lote1_navegador.py` (Chromium), `teste_lote1_script.py` (script).

## Já resolvido em pacotes entregues e ainda não aplicados

| Item | Onde | Estado |
|---|---|---|
| 72 (senha com 73 bytes → 500) | pacote de segurança | corrigido em ambiente de teste (8 a 72 bytes; login não consulta o banco acima de 72) |
| 74 (tentativas de login, cabeçalhos) | pacote de segurança | **parcial**: limite de tentativas, cabeçalhos e páginas de erro. Falta validar a qualidade da `FLASK_SECRET_KEY` |
| 51/52 | este lote | ver acima |

## Precisam de arquivos atuais do projeto (os que tenho são de 13/10)

| Item | Por que não dá para corrigir às cegas |
|---|---|
| 01 SQL com aspa extra | No meu exemplar de 13/10 não há aspa extra. O relatório viu outra versão. **Confira o seu:** `Select-String -Path neocortex_aprendizado_migracao.sql -Pattern "^'"` |
| 02 Reagendamento diz "não encontrada" | O defeito está em `db.atualizar_tarefa`/`servicos.atualizar_tarefa` (rowcount); o `db.py` que tenho nem tem `criar_objetivo` |
| 47 Fragmento manual sem conflito/evento | Depende do serviço de tarefas atual (`servicos.py`) |
| 08–23 Aprendizado (validade, coortes, idempotência, ocupação) | `aprendizado.py`, `decisao.py`, `ml_preparacao.py` atuais |
| 43 Falha de carregamento da agenda parece vazia | `calendario.html` atual |
| 03, 27, 44, 45 | `servicos.py`, `agenda.py` e rotas atuais |

## Decisões do grupo (não são código)

56 a 60 (o que os pontos significam, desfazer retirar conquista, chat × tela), 62 a 65 e 68 (loja, progressão, modo discreto, ativação automática da interface).
O relatório recomenda decidir **antes** de alterar a regra.

## Evolução (fora da primeira entrega)

6, 17, 21, 33, 38, 46, 62, 64, 76 e os demais marcados "Evolução" no relatório.
