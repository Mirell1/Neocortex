# Auditoria e correção do núcleo de inteligência — NEOCORTEX

Resultado dos arquivos recebidos (`ai.py`, `app.py`, `db.py`, `analise_energia.py`, SQLs,
`requirements.txt`, relatório de segurança). **137 testes automatizados passam**, contra
PostgreSQL 16 real e com um Gemini simulado (ver seção I e os limites no fim).

---

## A. Diagnóstico — como a IA realmente funcionava

Cada problema abaixo foi **reproduzido no código original** antes de ser corrigido.

| # | Problema (original) | Evidência | Gravidade |
|---|---|---|---|
| 1 | `criar_tabelas()` num banco novo montava o schema **antigo**: sem `usuarios.trabalha/estuda` e sem `interacoes_chat.autor` | `cadastrar_usuario` → `UndefinedColumn: trabalha` | P0 |
| 2 | Resposta da IA **nunca era gravada** no fluxo normal (o `registrar_interacao` do assistente estava dentro do `except`) | histórico = só `('usuario','oi')` | P0 |
| 3 | Mensagem vazia → `UnboundLocalError` → HTTP 500 | `id_usuario`/`historico` indefinidos | P0 |
| 4 | Ferramenta `consultar_perfil_usuario` quebrava: variável `padroes` nunca definida (o erro era engolido e devolvido como texto ao modelo) | `NameError: padroes` | P0 |
| 5 | "Quais tarefas eu tenho **hoje**?" devolvia `[]` com a tarefa existindo: `data_fim='2026-10-01'` vira meia-noite e exclui toda tarefa do dia | tool devolveu `[]` | P1 |
| 6 | A IA **não sabia a data/hora atuais** → impossível resolver "amanhã", "agora", "sexta" | prompt sem data | P1 |
| 7 | Rota `/cadastro` (legada) chamava `cadastrar_usuario` com a assinatura antiga (`ocupacao`), gravando `trabalha`/`estuda` trocados | leitura do código | P1 |
| 8 | Desfazer conclusão deixava o evento `concluiu` órfão → contamina qualquer análise de "planejado × realizado" | `status: pendente`, eventos `['concluiu']` | P1 |
| 9 | **Sem aprendizado real**: só `concluiu` era gravado. `decisoes`, `recomendacoes`, `resultados_recomendacoes`, `metricas`, `memorias` nunca recebiam dado; `padroes_comportamentais` só tinha o que o onboarding declarou | grep: nenhuma função escrevia nelas | P1 |
| 10 | Roteamento: as 5 ferramentas (inclusive as de **alteração**) iam em **toda** mensagem, até em "oi" | leitura de `responder()` | P2 |
| 11 | `compromissos`, `restricoes`, `disponibilidades` existem no banco, mas a IA não enxergava nenhuma | `listar_*` sem uso no `ai.py` | P1 |
| 12 | Erros engolidos (`print` + resposta genérica); histórico enviado com até 20 mensagens inteiras, sem truncar | leitura | P2 |

## B. Alterações, arquivo por arquivo

**Corrigidos:**

- **`db.py`** — `criar_tabelas()` roda as 5 migrações em ordem. Todo evento (`criou`, `adiou`,
  `reagendou`, `cancelou`, `concluiu`, `desfez_conclusao`) é gravado **na mesma transação** da
  mudança. Concluir duas vezes (duplo clique) não duplica evento. Reação do usuário a uma
  recomendação (`aceitou`/`recusou`/`adiou`) é registrada na hora. Novas: `listar_tarefas_janela`
  (sobreposição, corrige o bug 5), `substituir_memoria`, `salvar_metrica_unica`,
  `salvar_padrao_observado`, `registrar_decisao_com_recomendacao` e afins. Todas presas ao `id_usuario`.
- **`ai.py`** — bases de conhecimento 01–07 **idênticas ao original** (verificado por código).
  Novo: roteamento por intenção, data/hora no contexto, 10 ferramentas, histórico curto,
  anti-repetição, defesa contra ferramenta fora da intenção, telemetria. Corrige o `NameError`.
- **`app.py`** — resposta da IA gravada sempre; mensagem vazia tratada; causa real do erro
  no log (não ao usuário); `/cadastro` legada redireciona ao fluxo atual; ganchos de aprendizado
  em concluir/desfazer/editar/excluir; `/api/eventos` passa a incluir `compromissos`;
  exportação traz o e-mail (vinha de `session["email"]`, que nunca era definido).

**Novos:**

- **`agenda.py`** — fonte única do calendário (UI e IA). **`roteador.py`** — só separa saudação pura (sem ferramenta) do resto; quem entende a frase é o modelo.
  **`decisao.py`** — sugerir horário / o que fazer agora. **`aprendizado.py`** — o circuito de aprendizado.
  **`ml_preparacao.py`** — preparação para ML. **`neocortex_aprendizado_migracao.sql`** — migração aditiva e idempotente.
- `.env.example`, `requirements-dev.txt`, `readME.md` (estava vazio), `tests/`.

**Sem alteração:** `analise_energia.py` (testado contra o banco real: funciona, é só leitura e
não imprime dado pessoal), os 4 SQLs originais, `requirements.txt`.
`RELATORIO_SEGURANCA.md`: removi a pendência de CSRF, que já estava resolvida.

## C. Fluxo final

```
MENSAGEM
 → roteador.classificar          saudação pura? sem ferramentas. Qualquer outra coisa: TODAS as ferramentas  [0 tokens]
 → contexto mínimo               "[CONTEXTO DO SISTEMA] agora=… (quinta-feira)" + até 6 mensagens (600 caracteres cada)
 → Gemini (1ª chamada)           ENTENDE a frase (formal ou informal) e decide se consulta, cria, altera ou só conversa
 → ferramenta determinística     agenda / decisao / aprendizado / db   (id_usuario preso na closure)
 → Gemini (2ª chamada)           redige a resposta, no tom do usuário
 → app.py                        acrescenta a linha 📅 do que foi REALMENTE registrado, grava, e apos_evento() recalcula
 EVENTO → ANÁLISE → ATUALIZAÇÃO → EFEITO FUTURO (sugerir_horarios usa o padrão aprendido)
```

## D. Ferramentas

> **Decisão de desenho que mudou (04/10).** A versão anterior liberava as ferramentas por palavras-chave
> ("coloca", "agenda"...). Isso falhava com qualquer jeito de falar que a lista não previa ("bota aí",
> "tenho dentista amanhã 15h") e fazia o modelo **dizer que agendou sem ter criado**. Agora quem entende
> a frase é o modelo; o código garante só o que é verificável.

| Mensagem | Ferramentas | Quem decide o que fazer |
|---|---|---|
| saudação/agradecimento **puro** ("oi", "eae", "valeu") | nenhuma | — |
| **qualquer outra** (inclusive "sim", "tarde", "show" após uma pergunta da IA) | as 10 | o modelo |

As 10: `consultar_tarefas`, `consultar_agenda`, `consultar_perfil_usuario`, `consultar_aprendizado`, `sugerir_horarios`,
`recomendar_tarefa_agora`, `criar_tarefa`, `atualizar_tarefa`, `concluir_tarefa`, `cancelar_tarefa`.

**O que o código garante (não depende do modelo acertar):**

- **Linha 📅 de confirmação:** após criar/alterar/concluir/cancelar com sucesso, o código acrescenta uma linha factual
  (ex.: `📅 Registrado: Casa do amigo — qua 07/10 · 17:00–18:00 (duração assumida: 1h)`). **Se a linha 📅 apareceu, foi
  registrado; se não apareceu, não foi**, mesmo que o texto da IA diga "fechou".
- **Aviso de "não registrei":** se o usuário pediu para registrar (ex.: "bota aí que amanhã tenho dentista 15h") e o modelo
  respondeu sem fazer nada e sem perguntar, a resposta ganha "⚠️ eu ainda NÃO registrei isso". Também vale para "criei"/"foi agendado" sem ferramenta.
- **Conflito de agenda:** `criar_tarefa` e `atualizar_tarefa` recusam e devolvem os conflitos; só executam com `confirmar_conflito=true`.
- **Fim não informado:** assume **1 hora** e o modelo é instruído a avisar ("botei 1h, ajusta se precisar"). Só pergunta se faltar dia ou hora de início, ou se houver ambiguidade ("às 5": manhã ou tarde?).
- **Título ambíguo:** se mais de uma tarefa corresponde, a ferramenta devolve as candidatas e o modelo pergunta qual.
- **As linhas 📅/⚠️ não voltam ao modelo no histórico**, para ele não aprender a escrevê-las sozinho.

**O que passou a depender do modelo (custo da mudança):** distinguir "consulta" de "ordem" e resistir a instruções
maliciosas. Hoje o único autor das mensagens é o próprio dono da agenda (o sistema não lê e-mail nem páginas
de terceiros), então o risco é baixo; as ações são reversíveis (cancelar não apaga; concluir tem "desfazer").

## E. Calendário

A IA e a tela leem a agenda pela mesma função (`agenda.py`) — mesmas tarefas, mesma rotina e agora
também `compromissos` (a tela recebe a chave nova em `/api/eventos`). A IA também considera
`restricoes` e `disponibilidades`. Turnos que viram a meia-noite funcionam. Tarefa de *trabalho*
dentro do bloco de rotina *Trabalho* não conta como conflito.
**Consulta/criação/edição/conclusão/adiamento/reagendamento/cancelamento: todos implementados e testados.**

## F. Aprendizado — o que é medido e o que muda

| Evento | Registrado em | Alimenta |
|---|---|---|
| tarefa criada / concluída / desfeita | `eventos_execucao` | período observado, atraso mediano |
| horário movido (`adiou`/`reagendou`) | `eventos_execucao.detalhe` (antes/depois) | taxa de adiamento |
| cancelada / excluída | evento + reação | resultado da recomendação |
| recomendação aceita/recusada/adiada/ignorada | `resultados_recomendacoes` | taxa de aceitação |

**Parâmetros atualizados** (`padroes_comportamentais` com `fonte='observado'`, `metricas`, `memorias`):
período em que a pessoa de fato conclui, taxa de conclusão por período agendado, atraso mediano,
taxa de adiamento, taxa de aceitação. O que a pessoa **disse** fica separado do que ela **faz**
(`fonte='declarado'` × `'observado'`) e a divergência é exposta à IA.

**Regras de segurança, todas testadas:** mínimo de 5 eventos para existir um padrão; conclusões em
lote (< 10 min) contam como um evento; empate não gera padrão; só vale a janela de 60 dias;
**uma ocorrência isolada não derruba um padrão forte** (para trocar um padrão de confiança média/alta, o novo precisa de ≥ 8 eventos e ≥ 60% de domínio; um de confiança baixa troca com o mínimo de 5 eventos e 50%);
a confiança desce no máximo um nível por recálculo; um padrão recém-trocado nasce com confiança no máximo
*média*; memória superada fica inativa (histórico preservado). Métrica com amostra pequena **não é gravada**.

**Demonstração do circuito (teste `test_08`):** declara render de manhã → conclui 17 vezes à noite →
padrão `noite/alta/17 evidências`, memória única e rastreável, divergência sinalizada → a próxima sugestão de
horário passa a priorizar a noite e diz que a base é "período observado".

## G. Machine Learning

| | Situação |
|---|---|
| Gemini | LLM. **Não é** o "ML do projeto" |
| Regras, estatística, aprendizado paramétrico | **Existem e funcionam** (seções D–F) |
| **ML preditivo** | **Não existe ainda — e hoje não deveria.** Há só a preparação |

Coletado hoje: hora, dia da semana, categoria, duração planejada, antecedência, energia declarada,
conclusão, atraso, adiamentos, reação a recomendações. **Primeiro modelo útil:** probabilidade de
concluir a tarefa dado como foi agendada (regressão logística). **Duração real não é prevista**: o app
não gera `iniciou/pausou/retomou`.

Critério para ligar (`ml_preparacao.py`): ≥ 300 tarefas encerradas, ≥ 20 usuários, ≥ 50 por classe; treino no
passado e teste no futuro; o modelo só é aprovado se reduzir o log-loss em ≥ 2% sobre o baseline (a regra atual);
o fallback é sempre a regra. Nada é salvo nem entra em produção. **Com dados sintéticos de teste, o modelo perdeu
do baseline (0,71 × 0,66) e o sistema decidiu `manter_regras`** — o comportamento esperado. `n_adiamentos` fica
fora do modelo (vazamento de informação).

## H. Tokens

| | Original | Agora |
|---|---|---|
| Declarações de ferramentas por mensagem | 2.449 caracteres (5 ferramentas) | **~5.200** caracteres (10 ferramentas) em toda mensagem com conteúdo; **0** em saudação pura |
| Histórico por chamada | até 20 mensagens inteiras | 6, truncadas em 600 caracteres |
| Rodadas de ferramenta | até 5 | até 4; chamada idêntica no mesmo turno roda **uma** vez |
| Consulta antes de criar/alterar | modelo precisava pedir | conflito checado dentro da própria ferramenta (−1 rodada) |
| Achar a tarefa-alvo | consultar e depois agir (2 rodadas) | por título, dentro da ferramenta (1 rodada) |

**Honestidade sobre o custo:** ao deixar o modelo decidir, o custo fixo das ferramentas **subiu** (de ~2,4 mil para ~5,2 mil
caracteres por mensagem, cerca de 1,3 mil tokens). Em contrapartida, o custo dominante continua sendo o `SYSTEM_INSTRUCTION`
(as 7 bases a cada chamada; só a `BASE_01` tem ~12 mil caracteres) e os 6 arquivos de `PROMPTS IA/` **não foram enviados**.
A telemetria (`tokens_prompt_por_chamada`) mede o custo real. Maior retorno: *context caching* do Gemini para o trecho fixo.

## I. Testes (137 aprovados)

| Área | Cobertura |
|---|---|
| Cenários 1–7 e 10 do prompt | consulta, criação (dado faltante, conflito, data inválida), reagendamento (e título ambíguo), agenda agora, recomendação, aceitar, rejeitar sem destruir padrão, fora de escopo |
| Cenários 8 e 9 | repetição eleva confiança e adapta a próxima sugestão; mudança é detectada sem ficar preso ao padrão antigo |
| Linguagem natural | informal/formal, "bota aí", "tarde" como resposta a pergunta, linha 📅 só com sucesso, aviso de "não registrei", histórico sem linhas do sistema |
| Tokens | repetição, limite de rodadas, histórico |
| Integridade (seção 27) | usuário B não lê/altera/conclui/cancela nada do A, nem por id nem por título; recomendações, resultados e eventos isolados |
| Rotas Flask | resposta gravada, mensagem vazia, falha da IA, ponta a ponta com histórico user/model, IDOR, CSRF ativo, onboarding |
| Banco | bootstrap novo; migração sobre banco com dados, 2×, sem perda |
| Scripts | `analise_energia.py` (demo, dados reais, amostra pequena, só leitura), ML (sem dados e pipeline completo) |

## Limites e o que depende de você

1. **Gemini real não foi chamado** (sem rede/chave aqui). O cliente simulado devolve objetos reais do `google-genai`,
   então o formato é o mesmo, mas o *comportamento* do modelo (escolher a ferramenta certa) só se confirma com um
   teste real. Faça um smoke test com as 10 mensagens da seção D e olhe a telemetria no log (`neocortex.ia`).
2. **`calendario.html` não foi enviado.** `/api/eventos` já devolve `compromissos`, mas a tela só mostra se o JS
   desenhar essa chave.
3. **Nada cria `compromissos`, `restricoes`, `disponibilidades`, `tarefa_planejamento`, hábitos ou objetivos** — não
   há tela para isso. A IA já lê as três primeiras; estarão vazias até existir a tela.
4. Sem botão "iniciar/pausar", não há **duração real**; o "realizado" é o horário em que a pessoa clicou em concluir.
5. O modelo decide o que fazer com a frase: um modelo menor/mais barato erra mais (escolhe ferramenta errada, pergunta demais). Para avaliar a qualidade real, teste com um modelo maior. As travas (linha 📅, aviso, conflito) limitam o estrago, mas não substituem um bom modelo.
6. **Fuso:** `concluido_em` usa o relógio do banco; `datetime.now()` usa o do servidor. Mantenha os dois no mesmo fuso.
7. `metricas.valor` é `NUMERIC(10,2)`: taxas ficam com 2 casas.
8. Segurança (inalterada, ver `RELATORIO_SEGURANCA.md`): senha em texto na sessão durante o cadastro, sem limite de
   tentativas de login, e a senha do `.env` ainda no histórico do Git.
9. `GEMINI_MODEL` mantém o padrão do seu código (`gemini-3.8-flash`); confirme o nome na sua conta.
10. Banco existente: rode `neocortex_aprendizado_migracao.sql` e depois `python aprendizado.py`.
