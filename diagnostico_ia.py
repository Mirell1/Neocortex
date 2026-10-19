"""
NEOCORTEX - diagnostico_ia.py

Chama a IA exatamente como a fragmentação de objetivos chama e mostra o erro REAL, caso ele exista.
Serve para descobrir por que a tela mostrou "Não consegui falar com a IA agora": o app esconde o erro verdadeiro.

  - NÃO mostra a chave da IA (qualquer trecho dela que apareça numa mensagem é trocado por ***).
  - NÃO grava nada, nem no banco. Faz 2 chamadas pequenas à IA (usa um pouco da sua cota).

Uso (venv ativa, na pasta do projeto, ao lado do app.py):
    python diagnostico_ia.py

Como ler o resultado:
    OK ................................ a IA respondeu: o problema foi passageiro (sobrecarga) ou já passou.
    code=429 / RESOURCE_EXHAUSTED ..... limite de uso (cota) da chave: espere uns minutos ou use outra chave/plano.
    code=503 / UNAVAILABLE ............ a IA do Google estava sobrecarregada.
    code=401 ou 403 / API key ......... a chave não foi aceita (confira GEMINI_API_KEY no .env).
    code=404 / NOT_FOUND .............. o nome do modelo (GEMINI_MODEL) não existe para essa chave.
    ERRO DE ARGUMENTO ................. o ai.py ainda é o antigo (falta o pacote "gerar mais passos").
"""
import inspect
import os
import sys
import time
from datetime import date, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import ai
except KeyError as e:
    print(f"Faltou a variável {e} no ambiente (.env). O ai.py não consegue nem carregar sem ela.")
    sys.exit(1)
except Exception as e:
    print(f"Não consegui carregar o ai.py: {type(e).__name__}: {str(e)[:300]}")
    sys.exit(1)

chave = os.environ.get("GEMINI_API_KEY", "")


def limpo(texto):
    texto = str(texto)
    return texto.replace(chave, "***") if chave else texto


print(f"modelo configurado ............ {getattr(ai, 'GEMINI_MODEL', '?')}")
try:
    aceita = "existentes" in inspect.signature(ai.gerar_titulos_fragmentos).parameters
except Exception:
    aceita = False
print(f"ai.py conhece 'gerar mais passos' . {'sim' if aceita else 'NÃO (ai.py antigo)'}")
print()

prazo = date.today() + timedelta(days=30)
casos = [("sem passos existentes", {})]
if aceita:
    casos.append(("com passos existentes", {"existentes": ["Definir espaço tranquilo", "Praticar 3 minutos de respiração"]}))
falhou = False
for rotulo, extra in casos:
    inicio = time.time()
    try:
        resposta = ai.gerar_titulos_fragmentos("Aprender a meditar", prazo, "geral", "moderado", 3, **extra)
        print(f"[{rotulo}] OK em {time.time() - inicio:.1f}s -> {resposta}")
    except TypeError as e:
        falhou = True
        print(f"[{rotulo}] ERRO DE ARGUMENTO (arquivo desatualizado?): {limpo(e)[:300]}")
    except Exception as e:
        falhou = True
        print(f"[{rotulo}] FALHOU em {time.time() - inicio:.1f}s")
        print(f"    tipo ..... {type(e).__name__}")
        print(f"    code ..... {getattr(e, 'code', None)}    status ..... {getattr(e, 'status', None)}")
        print(f"    mensagem . {limpo(e)[:700]}")
print()
print("Resultado: " + ("a IA está respondendo normalmente." if not falhou else "houve erro; veja acima o code/status e a tabela de leitura no topo deste arquivo."))
