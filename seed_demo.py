"""
NEOCORTEX - seed_demo.py

Cria (ou recria) UMA conta fictícia com cerca de 4 semanas de uso realista:
3 semanas passadas, hoje e a próxima semana. Serve para testar a plataforma
"cheia" e para gravar a apresentação.

Segurança:
- Só roda com NEOCORTEX_DEMO=1 (banco local de desenvolvimento).
- Mexe apenas na conta demo@neocortex.local; nenhum outro usuário é tocado.
- A senha é pedida na hora (ou lida de NEOCORTEX_DEMO_SENHA). Nada fica escrito aqui.

Uso (venv ativa, na pasta do projeto, ao lado do app.py):
    python seed_demo.py            # cria a conta demo (apaga e recria se já existir)
    python seed_demo.py --apagar   # só apaga a conta demo

Usa as mesmas funções do app (servicos.criar_tarefa, db.criar_objetivo...), então
as regras de validação do sistema continuam valendo. A única escrita direta no
banco é corrigir concluido_em das tarefas passadas: o servicos.concluir_tarefa
grava "agora", e a demo precisa da hora em que a tarefa teria sido concluída.
"""

import argparse
import getpass
import os
import random
import sys
from datetime import date, datetime, timedelta

try:  # se o projeto usa .env, carrega antes de importar o db
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

EMAIL_DEMO = "demo@neocortex.local"
NOME_DEMO = "Ana"
SEMENTE = 42                 # mesma semente = mesmos dados toda vez (bom para regravar)
DIAS_PASSADOS = 21
DIAS_FUTUROS = 7

# ------------------------------------------------------------
# PERFIL FICTÍCIO: estuda de manhã, estágio ter/qui à tarde, rende mais à tarde
# ------------------------------------------------------------
ROTINA = [
    (["segunda", "terca", "quarta", "quinta", "sexta"], "Faculdade", "08:00", "12:00"),
    (["terca", "quinta"], "Estágio", "14:00", "18:00"),
]
ENERGIA_DECLARADA = "tarde"

TAREFAS_POR_CATEGORIA = {
    "estudo": ["Revisar anotações de estatística", "Lista de exercícios de Python",
               "Ler capítulo sobre regressão linear", "Resumo da aula de banco de dados",
               "Praticar pandas com dados reais", "Reunião do projeto em grupo",
               "Estudar para a prova de cálculo"],
    "trabalho": ["Relatório semanal do estágio", "Responder e-mails do estágio",
                 "Organizar planilha de indicadores"],
    "saude": ["Academia", "Caminhada no parque", "Alongamento"],
    "pessoal": ["Mercado da semana", "Pagar contas do mês", "Ligar para a família", "Arrumar o quarto"],
    "hobby": ["Praticar violão", "Ler um livro", "Desenhar"],
}
PESOS_DIA_UTIL = {"estudo": 40, "trabalho": 12, "saude": 20, "pessoal": 16, "hobby": 12}
PESOS_FIM_DE_SEMANA = {"estudo": 15, "saude": 25, "pessoal": 30, "hobby": 30}

# horários livres (fora da rotina), por dia da semana (0 = segunda)
HORARIOS_DIA_UTIL = [(12, 30), (14, 0), (16, 0), (19, 0), (21, 0)]
HORARIOS_ESTAGIO = [(12, 30), (19, 0), (21, 0)]          # terça e quinta
HORARIOS_FIM_DE_SEMANA = [(9, 0), (11, 0), (15, 0), (18, 0)]

OBJETIVOS = [
    {"titulo": "Aprender Python para análise de dados", "prazo_semanas": 6, "concluir": False,
     "fragmentos": ["Variáveis e tipos", "Listas e dicionários", "Funções", "Introdução ao pandas",
                    "Gráficos com matplotlib", "Mini projeto com dados abertos"], "feitos": 2},
    {"titulo": "Correr 5 km sem parar", "prazo_semanas": 8, "concluir": False,
     "fragmentos": ["Caminhada e trote: 20 min", "Correr 1 km", "Correr 2 km", "Correr 3 km"], "feitos": 1},
    {"titulo": "Ler 3 livros no semestre", "prazo_semanas": 10, "concluir": False,
     "fragmentos": [], "feitos": 0},
    {"titulo": "Organizar a rotina de estudos", "prazo_semanas": -1, "concluir": True,
     "fragmentos": [], "feitos": 0},
]

CONVERSA = [
    ("usuario", "Organiza minha semana?"),
    ("assistente", "Claro! Você tem faculdade de manhã e estágio na terça e na quinta. "
                   "Sugiro deixar os estudos mais pesados para as tardes livres de segunda, quarta e sexta."),
    ("usuario", "O que ficou para depois?"),
    ("assistente", "Ficaram duas tarefas atrasadas: **Mercado da semana** e **Lista de exercícios de Python**. "
                   "Quer que eu sugira novos horários para elas?"),
]


# ------------------------------------------------------------
# AUXILIARES
# ------------------------------------------------------------
def parar(msg):
    print(f"\nPARADO: {msg}")
    sys.exit(1)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


def sortear(pesos):
    cats = list(pesos)
    return random.choices(cats, weights=[pesos[c] for c in cats], k=1)[0]


def id_da_conta_demo(db):
    with db.conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_usuario FROM usuarios WHERE email = %s", (EMAIL_DEMO,))
            linha = cur.fetchone()
    if not linha:
        return None
    return linha["id_usuario"] if isinstance(linha, dict) else linha[0]


def apagar_conta_demo(db):
    id_demo = id_da_conta_demo(db)
    if id_demo is None:
        print("Nenhuma conta demo encontrada.")
        return
    db.excluir_usuario(id_demo)
    print(f"Conta demo apagada ({EMAIL_DEMO}).")


def planejar_tarefas(hoje):
    """Lista de tarefas a criar: (titulo, inicio, fim, categoria, destino)."""
    plano = []
    for desloc in range(-DIAS_PASSADOS, DIAS_FUTUROS + 1):
        dia = hoje + timedelta(days=desloc)
        semana = dia.weekday()
        if semana >= 5:
            horarios, pesos, qtd = HORARIOS_FIM_DE_SEMANA, PESOS_FIM_DE_SEMANA, random.randint(1, 3)
        elif semana in (1, 3):
            horarios, pesos, qtd = HORARIOS_ESTAGIO, PESOS_DIA_UTIL, random.randint(2, 3)
        else:
            horarios, pesos, qtd = HORARIOS_DIA_UTIL, PESOS_DIA_UTIL, random.randint(2, 4)

        usados = set()
        for (h, m) in sorted(random.sample(horarios, k=min(qtd, len(horarios)))):
            cat = sortear(pesos)
            opcoes = [t for t in TAREFAS_POR_CATEGORIA[cat] if t not in usados]
            if not opcoes:
                continue
            titulo = random.choice(opcoes)
            usados.add(titulo)
            inicio = datetime.combine(dia, datetime.min.time()).replace(hour=h, minute=m)
            fim = inicio + timedelta(minutes=random.choice([30, 45, 60, 90]))
            plano.append((titulo, inicio, fim, cat, desloc))
    return plano


def decidir_destino(inicio, fim, desloc, agora):
    """
    'concluida' (com hora realista), 'cancelada' ou 'pendente'.
    Rende mais à tarde (combina com a energia declarada), às vezes marca em lote
    à noite (o analise_energia.py sabe lidar com isso).
    """
    if inicio > agora:
        return "pendente", None
    chance = 0.72 + (0.12 if 12 <= inicio.hour < 18 else 0)
    if random.random() < chance:
        if random.random() < 0.2:   # marcou depois, junto com outras
            quando = datetime.combine(inicio.date(), datetime.min.time()).replace(
                hour=22, minute=30) + timedelta(minutes=random.randint(0, 6))
            quando = max(quando, fim)
        else:
            quando = fim - timedelta(minutes=random.randint(0, 20))
        return "concluida", min(quando, agora)
    if desloc < -5 and random.random() < 0.6:   # tarefas antigas abandonadas foram canceladas
        return "cancelada", None
    return "pendente", None                      # vira "atrasada" na tela


# ------------------------------------------------------------
# PRINCIPAL
# ------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apagar", action="store_true", help="só apaga a conta demo")
    args = parser.parse_args()

    if os.getenv("NEOCORTEX_DEMO", "0") != "1":
        parar("defina NEOCORTEX_DEMO=1 no .env (só no seu computador) para rodar este script.")

    import bcrypt
    import db
    import servicos

    if args.apagar:
        apagar_conta_demo(db)
        return

    senha = os.getenv("NEOCORTEX_DEMO_SENHA") or getpass.getpass("Senha para a conta demo (mín. 6 caracteres): ")
    if len(senha) < 6:
        parar("a senha precisa ter pelo menos 6 caracteres.")

    random.seed(SEMENTE)
    agora = datetime.now()
    hoje = agora.date()

    # 1. conta
    apagar_conta_demo(db)
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        uid = db.cadastrar_usuario(NOME_DEMO, EMAIL_DEMO, None, "18-24", True, True, "tarde", senha_hash=senha_hash)
    except Exception as e:
        parar(f"db.cadastrar_usuario falhou: {e}")
    print(f"Conta criada: {EMAIL_DEMO} (id {uid})")

    # 2. perfil: rotina fixa e energia declarada
    for dias, descricao, ini, fim in ROTINA:
        for dia in dias:
            db.adicionar_rotina(uid, dia, descricao, ini, fim)
    db.salvar_padrao(uid, "energia", ENERGIA_DECLARADA)
    print("Rotina fixa e energia declarada salvas.")

    # 3. tarefas (criadas pelo mesmo serviço que a tela usa)
    plano = planejar_tarefas(hoje)
    falhas = []
    for titulo, inicio, fim, cat, _ in plano:
        try:
            r = servicos.criar_tarefa(uid, titulo, iso(inicio), iso(fim), categoria=cat,
                                      origem="manual", confirmar_conflito=True)
        except ValueError as e:
            r = {"erro": str(e)}
        if not (r.get("sucesso") or r.get("sem_mudanca")):
            falhas.append((titulo, inicio, r.get("erro") or r))
    if falhas:
        print(f"  Atenção: {len(falhas)} de {len(plano)} tarefas não foram criadas. Primeiro motivo: {falhas[0][2]}")
        if len(falhas) > len(plano) / 2:
            parar("a maioria falhou; provavelmente o servicos.criar_tarefa não aceita datas no passado. "
                  "Me mande o servicos.py para ajustar o script.")

    # localiza os ids criados por (título, início)
    por_chave = {(t["titulo"], t["data_inicio"].replace(second=0, microsecond=0)): t["id_tarefa"]
                 for t in db.listar_tarefas(uid)}

    # 4. destino de cada tarefa: concluída (com hora realista), cancelada ou pendente
    horas_reais, cont = {}, {"concluida": 0, "cancelada": 0, "pendente": 0}
    for titulo, inicio, fim, cat, desloc in plano:
        id_tarefa = por_chave.get((titulo, inicio))
        if id_tarefa is None:
            continue
        destino, quando = decidir_destino(inicio, fim, desloc, agora)
        cont[destino] += 1
        if destino == "concluida":
            servicos.concluir_tarefa(uid, id_tarefa)
            horas_reais[id_tarefa] = quando
        elif destino == "cancelada":
            servicos.cancelar_tarefa(uid, id_tarefa)

    # 5. objetivos e fragmentos
    for obj in OBJETIVOS:
        prazo = (hoje + timedelta(weeks=obj["prazo_semanas"])).isoformat()
        db.criar_objetivo(uid, obj["titulo"], prazo=prazo)
    objetivos = {o["titulo"]: o["id_objetivo"] for o in db.listar_objetivos(uid)}

    fragmentos_feitos = []
    for obj in OBJETIVOS:
        id_obj = objetivos.get(obj["titulo"])
        if id_obj is None:
            print(f"  Atenção: objetivo não encontrado depois de criado: {obj['titulo']}")
            continue
        for i, frag in enumerate(obj["fragmentos"]):
            # fragmentos semanais: os primeiros ficam no passado (e alguns concluídos)
            dia = hoje + timedelta(weeks=i - obj["feitos"], days=1)
            inicio = datetime.combine(dia, datetime.min.time()).replace(hour=16)
            db.criar_fragmento_objetivo(uid, id_obj, frag, inicio, inicio + timedelta(minutes=30))
            if i < obj["feitos"]:
                fragmentos_feitos.append((frag, inicio))
        if obj["concluir"]:
            db.atualizar_objetivo(id_obj, uid, status="concluido")

    # fragmentos viram tarefas? se sim, conclui os do passado
    tarefas_agora = {(t["titulo"], t["data_inicio"].replace(second=0, microsecond=0)): t["id_tarefa"]
                     for t in db.listar_tarefas(uid)}
    fragmentos_concluidos = 0
    for frag, inicio in fragmentos_feitos:
        id_tarefa = tarefas_agora.get((frag, inicio))
        if id_tarefa is not None:
            servicos.concluir_tarefa(uid, id_tarefa)
            horas_reais[id_tarefa] = inicio + timedelta(minutes=35)
            fragmentos_concluidos += 1
    if fragmentos_feitos and not fragmentos_concluidos:
        print("  Aviso: os fragmentos não aparecem como tarefas, então nenhum foi marcado como concluído.")

    # 6. corrige concluido_em para a hora "real" (o serviço grava o momento do script)
    if horas_reais:
        with db.conectar() as conn:
            with conn.cursor() as cur:
                for id_tarefa, quando in horas_reais.items():
                    cur.execute("UPDATE tarefas SET concluido_em = %s WHERE id_tarefa = %s AND id_usuario = %s",
                                (quando, id_tarefa, uid))
            conn.commit()

    # 7. um pouco de histórico no assistente
    for autor, texto in CONVERSA:
        db.registrar_interacao(uid, texto, autor=autor)

    # resumo (sem dados sensíveis)
    print("\nPronto! Resumo da conta demo:")
    print(f"  tarefas criadas ......... {len(plano) - len(falhas)}")
    print(f"    concluídas ............ {cont['concluida']}")
    print(f"    canceladas ............ {cont['cancelada']}")
    print(f"    pendentes ............. {cont['pendente']} (as do passado aparecem como atrasadas)")
    print(f"  objetivos ............... {len(objetivos)} ({fragmentos_concluidos} fragmentos concluídos)")
    print(f"  mensagens no assistente . {len(CONVERSA)}")
    print(f"\nEntre com {EMAIL_DEMO} e a senha que você digitou.")
    print("Para apagar depois: python seed_demo.py --apagar")


if __name__ == "__main__":
    main()