"""
NEOCORTEX - atualizar_aprendizado_aplicado.py

Faz o aprendizado MUDAR o que o sistema sugere, em quatro frentes (a ideia original do projeto: aprender com a pessoa e readaptar):

  1. FOLGA PELO ATRASO: o atraso mediano e a taxa de adiamento já eram calculados e gravados, mas NADA os usava. Agora, ao sugerir
     horários, o sistema reserva uma folga DEPOIS da tarefa (de 15 em 15 min, no máximo 60) e explica:
     "reservei 45 min de folga depois (você costuma terminar ~41 min depois do previsto)". Se a folga não couber, oferece o
     horário sem ela e avisa. Observação: o app não registra quando a pessoa COMEÇA uma tarefa, só quando conclui; por isso
     o atraso aprendido é o de CONCLUSÃO.
  2. POR CATEGORIA: o horário em que a pessoa rende pode ser outro para estudo, trabalho ou hobby. O aprendizado agora guarda,
     por categoria, o período em que ela conclui e a taxa de conclusão por período (com as mesmas regras de evidência mínima do
     geral). Ao sugerir horário PARA uma categoria, o que se aprendeu sobre ela pesa mais que o geral. O assistente pode pedir
     horários de uma categoria (argumento 'categoria' de sugerir_horarios).
  3. HOBBY NO TEMPO LIVRE: quando não há nada urgente e há 30 min ou mais livres, "o que devo fazer agora?" convida para um dos
     hobbies do perfil (só um convite: nada é criado).
  4. BASE PARA REORGANIZAR: sugerir_horarios aceita 'reservas' (intervalos já tomados por outras propostas).

Sem dados suficientes nada muda: o comportamento anterior é exatamente o mesmo (as métricas só existem com evidência mínima).

Mexe em decisao.py, aprendizado.py e ai.py. É TUDO OU NADA: se qualquer trecho de qualquer arquivo não for reconhecido, nada é gravado.
Por padrão só MOSTRA o que mudaria. Rode na pasta do projeto (a do app.py):

    python atualizar_aprendizado_aplicado.py            # só mostra
    python atualizar_aprendizado_aplicado.py --aplicar  # grava (cópia .bak de cada arquivo; confere a sintaxe antes)

Rodar de novo é seguro.
"""
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(".").resolve()

ALVOS = (
    ('decisao.py', '[APRENDIZADO-APLICADO]', (
        ('folga, categoria e reservas: constantes',
         r'''HORIZONTE_PROXIMA_H = 3         # "começa já, já" = próximas 3 horas
''',
         r'''HORIZONTE_PROXIMA_H = 3         # "começa já, já" = próximas 3 horas
# [APRENDIZADO-APLICADO] folga reservada DEPOIS da tarefa, pelo atraso e pelo adiamento que a própria pessoa tem
FOLGA_ATRASO_ACIONA_MIN = 10    # só reserva folga se o atraso mediano for de pelo menos 10 min
FOLGA_PASSO_MIN = 15            # a folga é arredondada para cima de 15 em 15 min
FOLGA_MAX_MIN = 60              # teto: nunca reserva mais que 1 hora
ADIAMENTO_ALTO = 0.4            # adiou 40% ou mais das tarefas recentes
FOLGA_EXTRA_ADIAMENTO_MIN = 15  # folga a mais para quem adia muito
DESCANSO_MIN_LIVRE = 30         # só convida para um hobby se houver pelo menos 30 min livres
'''),
        ('contexto aprendido por categoria',
         r'''def _contexto_aprendido(id_usuario):
    """Padrões e taxas relevantes para escolher horário (cada item diz de onde vem)."""
    padroes = {p["tipo_padrao"]: p for p in db.listar_padroes(id_usuario)}
    metricas = {m["nome_metrica"]: float(m["valor"]) for m in db.listar_metricas(id_usuario)}
    return {
        "observado": padroes.get(aprendizado.PADRAO_PERIODO_OBSERVADO),
        "declarado": agenda.normalizar_periodo((padroes.get("energia") or {}).get("valor")),
        "metricas": metricas,
    }''',
         r'''def _contexto_aprendido(id_usuario, categoria=None):
    """Padrões e taxas relevantes para escolher horário (cada item diz de onde vem).
    [APRENDIZADO-APLICADO] Com categoria, traz também o que se aprendeu SOBRE ela (ex.: estudo)."""
    padroes = {p["tipo_padrao"]: p for p in db.listar_padroes(id_usuario)}
    metricas = {m["nome_metrica"]: float(m["valor"]) for m in db.listar_metricas(id_usuario)}
    return {
        "observado": padroes.get(aprendizado.PADRAO_PERIODO_OBSERVADO),
        "declarado": agenda.normalizar_periodo((padroes.get("energia") or {}).get("valor")),
        "metricas": metricas,
        "categoria": categoria,
        "observado_categoria": padroes.get(f"{aprendizado.PADRAO_PERIODO_OBSERVADO}:{categoria}") if categoria else None,
    }'''),
        ('pontuação com o aprendizado da categoria',
         r'''def _pontuar(periodo, ctx):
    """Pontuação de um período do dia + as razões, na ordem em que pesam."""
    pontos, base = 0.0, []
    obs = ctx["observado"]
    if obs and obs.get("valor") == periodo:
        if obs.get("confianca") in ("media", "alta"):
            pontos += 2
            base.append(f"período em que você mais conclui (observado, confiança {obs['confianca']})")
        else:
            pontos += 1
            base.append("período em que você tende a concluir (observado, confiança baixa)")
    if ctx["declarado"] == periodo:
        pontos += 1
        base.append("período de energia que você declarou")
    taxa = ctx["metricas"].get(f"taxa_conclusao_{periodo}")
    if taxa is not None:
        pontos += taxa
        base.append(f"você concluiu {taxa:.0%} das tarefas agendadas nesse período")
    return pontos, base''',
         r'''def _pontuar(periodo, ctx):
    """Pontuação de um período do dia + as razões, na ordem em que pesam.
    [APRENDIZADO-APLICADO] Para uma categoria, o que se aprendeu sobre ELA vale mais que o geral."""
    pontos, base = 0.0, []
    categoria = ctx.get("categoria")
    obs_cat = ctx.get("observado_categoria")
    obs = obs_cat or ctx["observado"]
    escopo = f" nas suas tarefas de {categoria}" if obs_cat and categoria else ""
    if obs and obs.get("valor") == periodo:
        if obs.get("confianca") in ("media", "alta"):
            pontos += 2
            base.append(f"período em que você mais conclui{escopo} (observado, confiança {obs['confianca']})")
        else:
            pontos += 1
            base.append(f"período em que você tende a concluir{escopo} (observado, confiança baixa)")
    if ctx["declarado"] == periodo:
        pontos += 1
        base.append("período de energia que você declarou")
    taxa_cat = ctx["metricas"].get(f"taxa_conclusao_{categoria}_{periodo}") if categoria else None
    taxa = taxa_cat if taxa_cat is not None else ctx["metricas"].get(f"taxa_conclusao_{periodo}")
    if taxa is not None:
        pontos += taxa
        de = f" de {categoria}" if taxa_cat is not None else ""
        base.append(f"você concluiu {taxa:.0%} das tarefas{de} agendadas nesse período")
    return pontos, base'''),
        ('sugerir horários: folga pelo atraso, categoria e reservas',
         r'''def sugerir_horarios(id_usuario, dia, duracao_min=60, agora=None, max_sugestoes=3):
    """
    Janelas livres do dia (descontando tarefas, compromissos, rotina,
    restrições e disponibilidade), ordenadas pelo que se SABE do usuário.
    Cada sugestão diz em que se baseia. Sem dados, só ordena por horário.
    """
    agora = agora or datetime.now()
    duracao = timedelta(minutes=duracao_min)
    blocos = agenda.blocos_ocupados(id_usuario, dia)
    apos = agenda.arredondar_para_cima(agora) if dia == agora.date() else None
    livres = agenda.janelas_livres(blocos, dia, apos)

    ctx = _contexto_aprendido(id_usuario)
    candidatos = []
    for ini, fim in livres:
        t = agenda.arredondar_para_cima(ini)
        while t + duracao <= fim:
            pontos, base = _pontuar(agenda.periodo_da_hora(t.hour), ctx)
            candidatos.append((pontos, t, base))
            t += timedelta(minutes=agenda.PASSO_MIN)

    candidatos.sort(key=lambda c: (-c[0], c[1]))
    escolhidas = []
    for pontos, t, base in candidatos:
        if all(t >= e["_fim"] or t + duracao <= e["_ini"] for e in escolhidas):
            escolhidas.append({"_ini": t, "_fim": t + duracao, "periodo": agenda.periodo_da_hora(t.hour), "base": base})
        if len(escolhidas) == max_sugestoes:
            break

    sugestoes = [
        {"inicio": e["_ini"].isoformat(timespec="minutes"), "fim": e["_fim"].isoformat(timespec="minutes"),
         "periodo": e["periodo"], "base": e["base"] or ["horário livre (ainda sem histórico para personalizar)"]}
        for e in escolhidas
    ]
    saida = {"dia": dia.isoformat(), "duracao_min": duracao_min, "sugestoes": sugestoes}
    if not sugestoes:
        saida["observacao"] = "Não há janela livre desse tamanho nesse dia."
        return saida

    # registra a decisão: se o usuário criar uma tarefa num desses horários, a ligação é feita depois
    db.salvar_decisao(
        id_usuario,
        f"sugestão de horário para {dia.isoformat()} ({duracao_min} min)",
        "janelas livres; padrão observado; energia declarada; taxa de conclusão por período",
        "SUGESTOES:" + ";".join(s["inicio"] for s in sugestoes),
    )
    return saida''',
         r'''def _descontar(livres, reservas):
    """[REORGANIZAR] Tira das janelas livres os intervalos já reservados por outras propostas (pares (ini, fim) de datetime)."""
    for r_ini, r_fim in reservas:
        novas = []
        for ini, fim in livres:
            if r_fim <= ini or r_ini >= fim:
                novas.append((ini, fim))
                continue
            if ini < r_ini:
                novas.append((ini, r_ini))
            if r_fim < fim:
                novas.append((r_fim, fim))
        livres = novas
    return livres


def _folga_aprendida(ctx):
    """[APRENDIZADO-APLICADO] Folga (min) a reservar DEPOIS da tarefa, pelo que a pessoa costuma atrasar e adiar.
    Devolve (folga, motivos). Sem evidência suficiente (as métricas só existem com dados), devolve (0, [])."""
    m = ctx["metricas"]
    folga, motivos = 0, []
    atraso = m.get("atraso_mediano_min")
    if atraso is not None and atraso >= FOLGA_ATRASO_ACIONA_MIN:
        folga += -(-int(round(atraso)) // FOLGA_PASSO_MIN) * FOLGA_PASSO_MIN
        motivos.append(f"você costuma terminar ~{atraso:.0f} min depois do previsto")
    adiamento = m.get("taxa_adiamento")
    if adiamento is not None and adiamento >= ADIAMENTO_ALTO:
        folga += FOLGA_EXTRA_ADIAMENTO_MIN
        motivos.append(f"você adiou {adiamento:.0%} das tarefas recentes")
    return min(folga, FOLGA_MAX_MIN), motivos


def _candidatos(livres, duracao, ctx, folga_min):
    """Todos os inícios possíveis (a cada PASSO_MIN) em que a tarefa E a folga cabem na janela livre."""
    total = duracao + timedelta(minutes=folga_min)
    candidatos = []
    for ini, fim in livres:
        t = agenda.arredondar_para_cima(ini)
        while t + total <= fim:
            pontos, base = _pontuar(agenda.periodo_da_hora(t.hour), ctx)
            candidatos.append((pontos, t, base))
            t += timedelta(minutes=agenda.PASSO_MIN)
    return candidatos


def sugerir_horarios(id_usuario, dia, duracao_min=60, agora=None, max_sugestoes=3, categoria=None, reservas=None, usar_folga=True):
    """
    Janelas livres do dia (descontando tarefas, compromissos, rotina,
    restrições e disponibilidade), ordenadas pelo que se SABE do usuário.
    Cada sugestão diz em que se baseia. Sem dados, só ordena por horário.

    [APRENDIZADO-APLICADO]
      categoria  : usa o que se aprendeu SOBRE aquela categoria (ex.: estudo), quando houver.
      reservas   : intervalos (ini, fim) já tomados por outras propostas; não são oferecidos de novo.
      usar_folga : reserva uma folga DEPOIS da tarefa quando o atraso e o adiamento da pessoa pedem
                   (se não couber, oferece sem a folga e avisa).
    """
    agora = agora or datetime.now()
    duracao = timedelta(minutes=duracao_min)
    blocos = agenda.blocos_ocupados(id_usuario, dia)
    apos = agenda.arredondar_para_cima(agora) if dia == agora.date() else None
    livres = agenda.janelas_livres(blocos, dia, apos)
    if reservas:
        livres = _descontar(livres, reservas)

    ctx = _contexto_aprendido(id_usuario, categoria)
    folga, motivos_folga = _folga_aprendida(ctx) if usar_folga else (0, [])
    folga_desejada = folga
    candidatos = _candidatos(livres, duracao, ctx, folga)
    sem_folga = False
    if folga and not candidatos:       # não coube com a folga: oferece sem ela e avisa
        candidatos, folga, sem_folga = _candidatos(livres, duracao, ctx, 0), 0, True

    candidatos.sort(key=lambda c: (-c[0], c[1]))
    folga_td = timedelta(minutes=folga)
    escolhidas = []
    for pontos, t, base in candidatos:
        if all(t >= e["_fim"] or t + duracao + folga_td <= e["_ini"] for e in escolhidas):
            escolhidas.append({"_ini": t, "_fim": t + duracao + folga_td, "_fim_tarefa": t + duracao,
                               "periodo": agenda.periodo_da_hora(t.hour), "base": base})
        if len(escolhidas) == max_sugestoes:
            break

    sugestoes = []
    for e in escolhidas:
        base = list(e["base"]) or (["horário livre"] if (folga or sem_folga) else ["horário livre (ainda sem histórico para personalizar)"])
        item = {"inicio": e["_ini"].isoformat(timespec="minutes"), "fim": e["_fim_tarefa"].isoformat(timespec="minutes"),
                "periodo": e["periodo"], "base": base}
        if folga:
            item["folga_min"] = folga
            base.append(f"reservei {folga} min de folga depois ({' e '.join(motivos_folga)})")
        elif sem_folga:
            base.append(f"não coube a folga de {folga_desejada} min que você costuma precisar")
        sugestoes.append(item)
    saida = {"dia": dia.isoformat(), "duracao_min": duracao_min, "sugestoes": sugestoes}
    if categoria:
        saida["categoria"] = categoria
    if not sugestoes:
        saida["observacao"] = "Não há janela livre desse tamanho nesse dia."
        return saida

    # registra a decisão: se o usuário criar uma tarefa num desses horários, a ligação é feita depois
    db.salvar_decisao(
        id_usuario,
        f"sugestão de horário para {dia.isoformat()} ({duracao_min} min)",
        "janelas livres; padrão observado; energia declarada; taxa de conclusão por período"
        + ("; folga pelo atraso típico" if folga else "") + (f"; aprendizado da categoria {categoria}" if categoria else ""),
        "SUGESTOES:" + ";".join(s["inicio"] for s in sugestoes),
    )
    return saida'''),
        ('sugestão de hobby no tempo livre (função)',
         r'''def recomendar_tarefa_agora(id_usuario, agora=None):''',
         r'''def _sugestao_descanso(id_usuario, agora, situacao):
    """[BEM-ESTAR] Sem nada urgente e com tempo livre, convida para um hobby do perfil.
    É só um convite (nunca cria nada) e nunca atrapalha a recomendação: qualquer falha aqui devolve None."""
    try:
        if situacao.get("atual") or not (agenda.INICIO_DIA <= agora.time() < agenda.FIM_DIA):
            return None
        livres = situacao.get("minutos_livres_ate_proximo")
        if livres is not None and livres < DESCANSO_MIN_LIVRE:
            return None
        hobbies = [h["nome"] for h in db.listar_hobbies_usuario(id_usuario) if h.get("nome")]
        if not hobbies:
            return None
        hobby = hobbies[(agora.toordinal() + id_usuario) % len(hobbies)]      # varia de um dia para o outro
        tempo = f"{livres} min livres" if livres is not None else "o resto do dia livre"
        return {"hobby": hobby, "minutos_livres": livres,
                "texto": f"Você tem {tempo} e nada urgente. Que tal um dos seus hobbies: {hobby}?",
                "base": ["hobby do seu perfil", "nenhuma tarefa urgente agora", tempo]}
    except Exception:
        return None


def recomendar_tarefa_agora(id_usuario, agora=None):'''),
        ('sugestão de hobby no tempo livre (uso)',
         r'''    if not candidatas:
        saida["observacao"] = "Não há tarefas abertas relevantes para agora."
        return saida
''',
         r'''    if not candidatas:
        saida["observacao"] = "Não há tarefas abertas relevantes para agora."
        descanso = _sugestao_descanso(id_usuario, agora, situacao)   # [BEM-ESTAR]
        if descanso:
            saida["sugestao_descanso"] = descanso
            saida["observacao"] += " " + descanso["texto"]
        return saida
'''),
    )),
    ('aprendizado.py', '[POR-CATEGORIA]', (
        ('categorias aprendidas',
         r'''HORAS_VALIDADE_TAREFA_AGORA = 6 # recomendação 'tarefa_agora' vence após N horas
''',
         r'''HORAS_VALIDADE_TAREFA_AGORA = 6 # recomendação 'tarefa_agora' vence após N horas
CATEGORIAS_APRENDIDAS = ("estudo", "trabalho", "hobby", "pessoal", "saude")   # [POR-CATEGORIA] "outro" não ensina nada
'''),
        ('padrão e taxas por categoria',
         r'''    resumo["periodo_observado"] = {"acao": acao, "estado": estado}
''',
         r'''    resumo["periodo_observado"] = {"acao": acao, "estado": estado}

    # --- [POR-CATEGORIA] o mesmo aprendizado, separado por categoria (estudo, trabalho...): o horário em que a pessoa
    #     rende pode ser outro para cada tipo de tarefa. Só entra com evidência suficiente, com as mesmas regras do geral.
    metricas_categoria = {}
    por_categoria = {}
    for t in tarefas:
        if t.get("categoria") in CATEGORIAS_APRENDIDAS:
            por_categoria.setdefault(t["categoria"], []).append(t)
    resumo["por_categoria"] = {}
    for cat, ts in por_categoria.items():
        chave = f"{PADRAO_PERIODO_OBSERVADO}:{cat}"
        concl_cat = [t["concluido_em"] for t in ts if t["status"] == "concluida" and t["concluido_em"]]
        padrao_cat = db.obter_padrao(id_usuario, chave)
        atual_cat = None
        if padrao_cat and padrao_cat.get("confianca"):
            atual_cat = {"valor": padrao_cat["valor"], "confianca": padrao_cat["confianca"], "evidencias": padrao_cat.get("evidencias")}
        acao_cat, estado_cat = decidir_atualizacao(atual_cat, calcular_periodo_observado(concl_cat, agora))
        if acao_cat in ("criar", "reforcar", "trocar"):
            db.salvar_padrao_observado(id_usuario, chave, estado_cat["valor"], estado_cat["confianca"], estado_cat["n"])
        resumo["por_categoria"][cat] = {"acao": acao_cat, "estado": estado_cat}
        for periodo, d in calcular_taxas_por_periodo(ts, agora).items():
            metricas_categoria[f"taxa_conclusao_{cat}_{periodo}"] = d["taxa"]
'''),
        ('gravar as taxas por categoria',
         r'''    for nome, valor in metricas.items():
        db.salvar_metrica_unica(id_usuario, nome, valor, PERIODO_REF)
''',
         r'''    metricas.update(metricas_categoria)   # [POR-CATEGORIA]
    for nome, valor in metricas.items():
        db.salvar_metrica_unica(id_usuario, nome, valor, PERIODO_REF)
'''),
    )),
    ('ai.py', '[POR-CATEGORIA]', (
        ('a IA pode pedir horários de uma categoria',
         r'''    def sugerir_horarios(data, duracao_minutos=60):
        dia = _parse_dia(data).date()
        duracao = int(duracao_minutos or 60)
        if not 5 <= duracao <= 600:
            raise ValueError("duracao_minutos precisa estar entre 5 e 600.")
        return decisao.sugerir_horarios(id_usuario, dia, duracao, agora)''',
         r'''    def sugerir_horarios(data, duracao_minutos=60, categoria=None):
        dia = _parse_dia(data).date()
        duracao = int(duracao_minutos or 60)
        if not 5 <= duracao <= 600:
            raise ValueError("duracao_minutos precisa estar entre 5 e 600.")
        categoria = categoria if categoria in servicos.CATEGORIAS_VALIDAS else None   # [POR-CATEGORIA]
        return decisao.sugerir_horarios(id_usuario, dia, duracao, agora, categoria=categoria)'''),
        ('contrato de argumentos da ferramenta',
         r'''    "sugerir_horarios": "data, duracao_minutos",
''',
         r'''    "sugerir_horarios": "data, duracao_minutos, categoria",
'''),
    ))
)


def ler(caminho):
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n"), "\r\n" in bruto


def gravar_texto(texto, crlf):
    return (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")


def main():
    ap = argparse.ArgumentParser(description="Faz o aprendizado mudar o que o sistema sugere.")
    ap.add_argument("--aplicar", action="store_true", help="grava as mudanças (sem isso, só mostra)")
    args = ap.parse_args()
    if not (RAIZ / "app.py").exists():
        print("Rode na pasta do projeto (a do app.py).")
        return 2
    plano, problemas = [], []
    for rel, marca, trocas in ALVOS:
        arquivo = RAIZ / rel
        if not arquivo.exists():
            problemas.append(f"{rel}: o arquivo não existe.")
            continue
        texto, crlf = ler(arquivo)
        if marca in texto and all(depois in texto for _, _, depois in trocas):
            print(f"   {rel}: já aplicado (nada a fazer).")
            continue
        faltam = [rotulo for rotulo, antes, _ in trocas if texto.count(antes) != 1]
        if faltam:
            problemas.append(f"{rel}: NÃO reconheci: " + "; ".join(faltam))
            continue
        novo = texto
        for _, antes, depois in trocas:
            novo = novo.replace(antes, depois, 1)
        try:
            compile(novo, rel, "exec")
        except SyntaxError as e:
            problemas.append(f"{rel}: o arquivo novo não passou na conferência de sintaxe ({e})")
            continue
        print(f"-> {rel}: {len(trocas)} ajuste(s)")
        for rotulo, _, _ in trocas:
            print(f"     - {rotulo}")
        plano.append((arquivo, novo, crlf))
    if problemas:
        print("\nNADA FOI GRAVADO (é tudo ou nada). Motivo:")
        for p in problemas:
            print("  " + p)
        print("  Me mande o arquivo citado que eu ajusto.")
        return 1
    if not plano:
        return 0
    if not args.aplicar:
        print("\nNada foi alterado. Para aplicar:  python atualizar_aprendizado_aplicado.py --aplicar")
        return 0
    for arquivo, novo, crlf in plano:
        copia = arquivo.with_name(arquivo.name + ".bak")
        n = 1
        while copia.exists():
            n += 1
            copia = arquivo.with_name(f"{arquivo.name}.bak{n}")
        shutil.copy2(arquivo, copia)
        arquivo.write_bytes(gravar_texto(novo, crlf))
        print(f"gravado: {arquivo.relative_to(RAIZ)}  (cópia do original: {copia.name})")
    print("\nPronto. Reinicie o servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
