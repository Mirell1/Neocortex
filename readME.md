# NEOCORTEX

Sistema de inteligência pessoal para organização de rotina: tarefas, agenda,
rotina fixa e um assistente (Gemini) que entende o contexto do usuário e
aprende com o comportamento real dele.

> DESORGANIZAÇÃO → CLAREZA · PROCRASTINAÇÃO → PROGRESSO

## Instalação

```bash
python -m venv venv && venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env                              # e preencha o .env
```

A pasta `PROMPTS IA/` (as bases de conhecimento 02 a 07 que o `ai.py` carrega) precisa
existir ao lado do `ai.py`.

### Banco de dados

**Banco novo e vazio**

```bash
python -c "import db; db.criar_tabelas()"
```

Roda, em ordem: schema → novas tabelas → ajuste de usuários → migração do chat → migração
do aprendizado. (Só funciona em banco vazio; o ajuste de usuários faz `TRUNCATE usuarios`.)

**Banco que já existe (com dados)**: rode **somente** a migração nova. Ela é aditiva,
idempotente e não apaga nada:

```bash
psql -d neocortex -f neocortex_aprendizado_migracao.sql
python aprendizado.py        # opcional: gera o aprendizado do histórico que já existe
```

### Rodar

```bash
python app.py
```

## Como a IA funciona

```
MENSAGEM
  → roteador.py      intenção + ferramentas permitidas   (regras, SEM LLM)
  → ai.py            data/hora atual + histórico curto → Gemini (só as ferramentas da intenção)
  → ferramenta       agenda.py · decisao.py · aprendizado.py · db.py   (determinísticas)
  → Gemini           redige a resposta
  → app.py           grava a resposta; aprendizado.apos_evento() atualiza padrões
```

| Módulo | Papel |
|---|---|
| `db.py` | Único acesso ao PostgreSQL (pool, `id_usuario` em tudo, eventos gravados na mesma transação) |
| `agenda.py` | **Fonte única do calendário** (tarefas + compromissos + rotina + restrições + disponibilidade). Conflitos, janelas livres, "o que está acontecendo agora" |
| `roteador.py` | Decide quais ferramentas existem para cada mensagem |
| `decisao.py` | Sugestão de horário e "o que fazer agora" (regras rastreáveis, registram decisão e recomendação) |
| `aprendizado.py` | Evento → análise → atualização de padrão/métrica/memória, com limiares de evidência |
| `ml_preparacao.py` | Dataset de features, prontidão e comparação modelo × baseline. **Não coloca ML em produção** |
| `analise_energia.py` | Relatório agregado, só leitura: energia declarada × comportamento observado |

## O que é e o que não é "inteligência" aqui

| Camada | O que é | Onde |
|---|---|---|
| LLM | Gemini: entende a mensagem, chama ferramentas, redige a resposta | `ai.py` |
| Regras | Roteamento, conflitos, escolha de horário e de tarefa | `roteador.py`, `agenda.py`, `decisao.py` |
| Análise estatística | Taxas de conclusão, atraso mediano, taxa de adiamento | `aprendizado.py`, `analise_energia.py` |
| Aprendizado paramétrico | Período observado de conclusão, com confiança e troca controlada | `aprendizado.py` |
| **Machine Learning preditivo** | **Ainda não existe.** Só a preparação e o critério objetivo para ligar | `ml_preparacao.py` |

## Testes

```bash
pip install -r requirements-dev.txt
pytest tests
```

Os testes **derrubam e recriam o schema** do banco configurado no `.env`: use um banco **só
de teste** (o nome precisa conter `test`, por exemplo `neocortex_test`). O Gemini nunca é
chamado de verdade.

Diagnóstico completo, o que foi alterado e os limites conhecidos: **AUDITORIA_NUCLEO_IA.md**.
