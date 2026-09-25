# Relatório de Segurança — Back-end NEOCORTEX

**Data:** Setembro de 2026
**Escopo:** Revisão do back-end (Flask + PostgreSQL) gerado com apoio de ferramenta de IA, antes da adição de novas funcionalidades.
**Responsável pela revisão e correções:** Ay (com apoio de IA para diagnóstico e implementação)

---

## 1. Contexto

O back-end do NEOCORTEX foi estruturado com apoio de ferramentas de IA, sem
supervisão direta durante sua criação. Como parte da preparação para a
próxima fase do projeto (novas funcionalidades e integração com os demais
módulos), foi feita uma revisão completa do código em busca de
vulnerabilidades, antes de qualquer nova feature ser construída em cima
dele.

A metodologia foi: leitura linha a linha do `app.py` e `db.py`, teste
prático de cada falha identificada em ambiente local, implementação da
correção, e reteste confirmando que a falha foi eliminada sem quebrar o
funcionamento normal do sistema.

---

## 2. Vulnerabilidades encontradas e status

| # | Vulnerabilidade | Severidade | Status |
|---|---|---|---|
| 1 | Controle de acesso quebrado entre usuários (IDOR) | 🔴 Crítica | ✅ Corrigida e testada |
| 2 | Chave de sessão (`secret_key`) com valor padrão inseguro | 🔴 Crítica | ✅ Corrigida e testada |
| 3 | Risco de injeção de SQL nos nomes de coluna (`atualizar_*`) | 🟠 Alta | ✅ Corrigida (junto com o item 1) |
| 4 | Ausência de proteção CSRF | 🟠 Alta | ✅ Corrigida e testada |
| 5 | Ausência de tratamento de erros nos formulários | 🟡 Média | ⏳ Pendente |
| 6 | Uma conexão nova por chamada ao banco (sem pool) | 🟡 Média | ⏳ Pendente |
| 7 | Nenhum limite de tentativas de login | 🟡 Média | ⏳ Pendente |
| 8 | Projeto sem `requirements.txt` / README | 🟢 Organização | ✅ Corrigida |

---

## 3. Detalhamento das correções aplicadas

### 3.1 — Controle de acesso quebrado entre usuários (IDOR)

**O que era:** as funções que alteravam ou apagavam uma tarefa ou um item de
rotina fixa (`marcar_tarefa_concluida`, `atualizar_tarefa`, `deletar_tarefa`,
`desfazer_conclusao_tarefa`, `buscar_tarefa`, `atualizar_rotina`,
`deletar_rotina`) filtravam a operação apenas pelo ID do registro, sem
verificar se ele pertencia ao usuário autenticado na sessão.

**Risco real:** qualquer usuário logado no sistema podia concluir, editar
ou apagar tarefas de **qualquer outra pessoa**, apenas testando números de
ID sequenciais na URL. Isso é uma falha classificada como **IDOR
(Insecure Direct Object Reference)**, uma das vulnerabilidades mais comuns
em aplicações web, e configura também um problema de proteção de dados
pessoais, já que dados de um usuário ficavam acessíveis e modificáveis por
outro sem autorização.

**Correção:** todas as funções passaram a exigir também o `id_usuario` da
sessão ativa, filtrando por `WHERE id_da_coisa = %s AND id_usuario = %s`.
A rota correspondente (`/tarefas/<id>/concluir`) agora responde com erro
**404** quando a tarefa não pertence ao usuário logado — sem diferenciar
esse caso de "a tarefa não existe", para não revelar informação a quem
está tentando adivinhar IDs de outras contas.

**Teste realizado:** duas contas de teste distintas, logadas
simultaneamente em janelas separadas do navegador. A Conta B tentou
concluir uma tarefa pertencente à Conta A via requisição direta
(`fetch` no console do navegador). Confirmado retorno **404** e nenhuma
alteração no banco de dados.

### 3.2 — Chave de sessão (`secret_key`) insegura

**O que era:** o código usava
`app.secret_key = os.getenv("FLASK_SECRET_KEY", "troque-essa-chave-em-producao")`.
Como o arquivo `.env` do projeto não define essa variável, a aplicação
rodava sempre com a string fixa, que está gravada no código-fonte —
publicado no repositório GitHub.

**Risco real:** a `secret_key` é o que garante que o cookie de sessão do
Flask não pode ser falsificado. Com essa chave em mãos (disponível
publicamente no histórico do repositório), qualquer pessoa poderia forjar
um cookie de sessão válido dizendo "sou o usuário X" e acessar qualquer
conta do sistema sem precisar de senha.

**Correção:** a linha foi alterada para
`app.secret_key = os.environ["FLASK_SECRET_KEY"]`. Sem valor padrão: se a
variável não estiver definida no ambiente, a aplicação se recusa a
iniciar, em vez de rodar silenciosamente de forma insegura.

**Teste realizado:** confirmado que a aplicação roda normalmente com a
chave presente no `.env`, e que falha de forma explícita (`KeyError`) ao
remover a variável, sem subir o servidor nesse cenário.

### 3.3 — Risco de injeção de SQL nos nomes de coluna

**O que era:** as funções `atualizar_tarefa` e `atualizar_rotina`
construíam a lista de colunas do `UPDATE` diretamente a partir das chaves
recebidas via `**campos`, usando f-string. Os *valores* já eram protegidos
contra injeção (via `%s`), mas os *nomes das colunas* não — o que criaria
uma brecha de injeção de SQL no momento em que alguém implementasse uma
rota que repassasse `request.form` diretamente para essas funções.

**Correção:** adicionada uma lista branca explícita de colunas permitidas
(`COLUNAS_TAREFA_PERMITIDAS` e `COLUNAS_ROTINA_PERMITIDAS`) em cada
função, filtrando qualquer campo fora dessa lista antes de montar a
consulta.

### 3.4 — Ausência de proteção CSRF

**O que era:** os formulários de login, cadastro, criação e conclusão de
tarefa aceitavam requisições POST vindas de qualquer origem, não apenas do
próprio site. Isso permitiria que um site malicioso, visitado pelo usuário
em outra aba enquanto ele estivesse logado no NEOCORTEX, disparasse ações
em nome dele (criar ou concluir tarefas, por exemplo) sem seu
conhecimento — um ataque conhecido como CSRF (Cross-Site Request
Forgery).

**Correção:** ativado `flask_wtf.CSRFProtect` no `app.py`, e adicionado um
campo oculto com token (`{{ csrf_token() }}`) em todos os quatro
formulários POST existentes no projeto (login, cadastro, criar tarefa,
concluir tarefa). Qualquer POST que chegue sem esse token é
automaticamente rejeitado pelo Flask antes de alcançar a lógica da rota.

**Teste realizado:** confirmado que (1) o fluxo normal do sistema
continua funcionando integralmente com o token presente, e (2) uma
requisição simulando um ataque, enviada sem o token via console do
navegador, foi rejeitada com status 400.

### 3.5 — Documentação e reprodutibilidade do ambiente

Foram criados os arquivos `requirements.txt` (dependências com versões
travadas), `.env.example` (modelo das variáveis de ambiente necessárias,
sem valores reais) e o `readME.md` foi preenchido com instruções completas
de instalação e o estado atual do projeto. Isso permite que qualquer
integrante do grupo — ou avaliador do projeto — configure e rode o
sistema do zero sem precisar de conhecimento prévio da configuração.

---

## 4. Pendências recomendadas (não bloqueantes)

Estes itens não impedem o uso atual do sistema, mas são recomendados antes
de uma eventual publicação em produção ou exposição fora da rede local:

- **Proteção CSRF** nos formulários (`flask-wtf` já está no
  `requirements.txt`, falta ativar `CSRFProtect` e adicionar o token nos
  formulários).
- **Tratamento de erros de formulário** (campos ausentes, datas
  inválidas) para evitar telas de erro 500 expostas ao usuário final.
- **Pool de conexões** com o banco, para melhorar performance e garantir
  atomicidade em operações que hoje usam múltiplas conexões separadas
  (ex.: cadastro de usuário com hobbies).
- **Limite de tentativas de login**, para mitigar ataques de força bruta.
- **Senha em texto puro na `session` do Flask durante o fluxo de cadastro em
  4 etapas** (nova interface). A `session` padrão do Flask é assinada, não
  criptografada — alguém com acesso ao cookie consegue ler o conteúdo
  (não adulterar, mas ler). O ideal é fazer o hash da senha assim que ela
  é recebida (na etapa 2) e guardar só o hash na sessão até a etapa final,
  em vez da senha original.

---

## 5. Observação importante à parte

Durante a configuração do ambiente local para esta revisão, foi
identificado que o arquivo `.env` — contendo a senha do banco de dados
usada na criação original do projeto — está presente no **histórico do
Git** do repositório, mesmo após um commit posterior removendo o arquivo.
Remover um arquivo do repositório não apaga seu conteúdo do histórico;
qualquer pessoa que clone o repositório consegue recuperar essa senha.

Essa senha já foi comunicada à pessoa responsável pelo banco de dados para
troca. Recomenda-se, adicionalmente, reescrever o histórico do
repositório (via `git filter-repo` ou BFG Repo-Cleaner) para remover essa
informação de forma definitiva antes de qualquer divulgação mais ampla do
repositório.
