"""Escolha dos cortes pelo Claude, com resposta em JSON garantido pelo schema (structured output).

A IA e chamada pelo Claude Code (`claude -p`), logado com a conta do claude.ai: consome a cota
do plano (Pro/Max), sem cobranca por chamada de API. A ANTHROPIC_API_KEY e removida do ambiente
do subprocesso de proposito, senao o Claude Code usaria a chave e cobraria por uso.
"""
import json
import math
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from clipador.modelos import Corte, Pico, Segmento
from clipador.util import fmt

PROMPT = """Voce e editor de cortes virais para TikTok. Abaixo esta a transcricao de um video do YouTube
chamado "{titulo}", com tempos em segundos, e os momentos em que o audio fica bem mais alto que o normal
(costumam ser reacoes, gritos, explosoes, risadas).{parte}

Escolha os {n} melhores trechos para virar cortes independentes de TikTok. Regras:
- Cada corte deve ter entre {dmin} e {dmax} segundos.
- Precisa fazer sentido sozinho, sem contexto do resto do video.
- Comece num gancho forte (algo engracado, chocante, uma pergunta, uma reacao) nos primeiros 2 segundos.
- Termine num ponto natural (fim de frase, desfecho, punchline). Nunca no meio de uma fala.
- Prefira momentos engracados, absurdos, epicos, surpreendentes ou polemicos.
- Os cortes nao podem se sobrepor.

Para cada corte, preencha:
- inicio / fim: em segundos, conforme a transcricao
- titulo: texto curto que aparece no topo do video (max 6 palavras)
- legenda_post: legenda para o post do TikTok
- hashtags: lista de hashtags com # (ex: "#gta6")
- nota: de 0 a 10, quanto potencial viral o trecho tem
- motivo: por que esse trecho funciona

PICOS DE AUDIO (segundo e quantos dB acima da media):
{picos}

TRANSCRICAO:
{transcricao}
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "cortes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "number"},
                    "fim": {"type": "number"},
                    "titulo": {"type": "string"},
                    "legenda_post": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "nota": {"type": "number"},
                    "motivo": {"type": "string"},
                },
                "required": ["inicio", "fim", "titulo", "legenda_post", "hashtags", "nota", "motivo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cortes"],
    "additionalProperties": False,
}

SYSTEM = ("Voce e um assistente de edicao de video. Responda somente com os dados pedidos, "
          "no formato do schema. Nao use ferramentas.")
TIMEOUT = 900  # segundos por chamada
# variaveis que fariam o Claude Code cobrar por API em vez de usar a cota do plano
ENV_DE_API = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
# Abre o Claude Code "limpo": sem settings/CLAUDE.md do usuario, sem conectores MCP, sem skills.
# Medido em 12/11/2026: ~9.000 -> ~1.100 tokens de entrada por chamada, e o login do plano continua valendo.
ISOLAMENTO = ("--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands")


def montar_prompt(segs: list[Segmento], picos: list[Pico], titulo: str,
                  n: int, dmin: int, dmax: int, parte: str = "") -> str:
    linhas = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segs)
    txt_picos = "\n".join(f"{p['segundo']}s (+{p['acima_da_media_db']} dB)" for p in picos) or "nenhum"
    return PROMPT.format(titulo=titulo, n=n, dmin=dmin, dmax=dmax, picos=txt_picos,
                         transcricao=linhas, parte=parte)


def _executavel_claude() -> str:
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError("Claude Code nao encontrado no PATH. Instale (claude.com/claude-code), "
                           "rode `claude` uma vez para logar com a conta do claude.ai, ou use --sem-ia.")
    return exe


def chamar_ia(conteudo: str | list, schema: dict, modelo: str) -> tuple[dict, dict]:
    """Faz uma chamada pelo Claude Code com resposta em JSON (structured output).

    `conteudo` e um texto ou uma lista de blocos (texto/imagem), como na Messages API.
    Devolve (dados, info), onde info = {"modelo": ..., "uso": {"entrada": ..., "saida": ...}}.
    """
    if isinstance(conteudo, str):
        conteudo = [{"type": "text", "text": conteudo}]
    mensagem = {"type": "user", "message": {"role": "user", "content": conteudo}}

    cmd = [_executavel_claude(), "-p",
           "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", modelo,
           "--json-schema", json.dumps(schema),
           "--system-prompt", SYSTEM,
           "--tools", "",
           "--no-session-persistence",
           *ISOLAMENTO]
    env = {k: v for k, v in os.environ.items() if k not in ENV_DE_API}
    # cwd fora do projeto: assim o Claude Code nao carrega o CLAUDE.md (gastaria cota a toa)
    try:
        proc = subprocess.run(cmd, input=json.dumps(mensagem) + "\n", capture_output=True,
                              text=True, encoding="utf-8", env=env, cwd=tempfile.gettempdir(),
                              timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"O Claude Code nao respondeu em {TIMEOUT}s.") from None

    resultado = None
    for linha in proc.stdout.splitlines():
        try:
            evento = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if evento.get("type") == "result":
            resultado = evento
    if resultado is None:
        erro = (proc.stderr or proc.stdout).strip()[-800:]
        raise RuntimeError(f"O Claude Code falhou (codigo {proc.returncode}): {erro}")

    if resultado.get("stop_reason") == "refusal":
        raise RuntimeError("A IA recusou o pedido. Tente de novo ou use --sem-ia.")
    if resultado.get("stop_reason") == "max_tokens":
        raise RuntimeError("A resposta da IA foi cortada (max_tokens). Peca menos cortes.")
    if resultado.get("is_error") or resultado.get("subtype") != "success":
        detalhe = resultado.get("result") or resultado.get("subtype")
        raise RuntimeError(f"Erro do Claude Code: {detalhe} "
                           "(limite do plano atingido? veja com /usage no claude)")

    dados = resultado.get("structured_output")
    if dados is None:
        dados = json.loads(resultado["result"])
    uso = resultado.get("usage", {})
    info = {
        "modelo": next(iter(resultado.get("modelUsage") or {}), modelo),
        "uso": {"entrada": uso.get("input_tokens", 0) + uso.get("cache_creation_input_tokens", 0)
                + uso.get("cache_read_input_tokens", 0),
                "saida": uso.get("output_tokens", 0)},
    }
    return dados, info


# Lives longas sao divididas em blocos: um pedido gigante pode estourar o contexto/timeout,
# a IA escolhe pior (favorece o comeco) e, se falhar, perde tudo.
BLOCO_SEG = 3600        # ~1 hora de video por pedido
SOBREPOSICAO_SEG = 90   # para nao perder um momento bem na emenda entre dois blocos
PARALELO_BLOCOS = 2     # pedidos ao mesmo tempo (mais que isso estoura o limite do plano rapido)


def dividir_em_blocos(segs: list[Segmento], bloco: float = BLOCO_SEG,
                      sobreposicao: float = SOBREPOSICAO_SEG) -> list[tuple[float, float, list[Segmento]]]:
    """(inicio, fim, segmentos) de cada bloco. Video de ate 1h15 fica num bloco so.

    Uma sobra menor que 1/4 de bloco no final e absorvida pelo ultimo bloco.
    """
    if not segs:
        return [(0.0, 0.0, [])]
    total = segs[-1]["end"]
    blocos, ini = [], 0.0
    while True:
        fim = ini + bloco
        if total - fim < bloco * 0.25:
            fim = total
        blocos.append((ini, fim, [s for s in segs if s["end"] > ini and s["start"] < fim]))
        if fim >= total:
            return blocos
        ini = fim - sobreposicao


def _escolher_no_bloco(i, qtd, ini, fim, segs_bloco, picos, titulo, n_bloco, dmin, dmax,
                       modelo, cache: Path | None):
    if cache is not None and cache.exists():
        print(f"  bloco {i}/{qtd} ({fmt(ini)}-{fmt(fim)}): usando resposta salva")
        return json.loads(cache.read_text(encoding="utf-8"))
    parte = ""
    if qtd > 1:
        parte = (f"\n\nEste video e longo e foi dividido em partes. Esta e a parte {i} de {qtd}, "
                 f"de {fmt(ini)} a {fmt(fim)}. Escolha os trechos so dentro dela.")
    picos_bloco = [p for p in picos if ini <= p["segundo"] < fim]
    prompt = montar_prompt(segs_bloco, picos_bloco, titulo, n_bloco, dmin, dmax, parte)
    print(f"  bloco {i}/{qtd} ({fmt(ini)}-{fmt(fim)}): pedindo {n_bloco} trechos...")
    dados, info = chamar_ia(prompt, SCHEMA, modelo)
    registro = {"inicio": ini, "fim": fim, **info, "resposta": dados}
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")
    return registro


def escolher_com_ia(segs: list[Segmento], picos: list[Pico], titulo: str, n: int,
                    dmin: int, dmax: int, modelo: str, salvar_em: Path | None = None) -> list[Corte]:
    """Escolhe os cortes so pela transcricao (Whisper) e pelos picos de audio.

    Com a 2a passada ligada, isto vira a 1a passada: escolhe os candidatos.
    Lives longas sao divididas em blocos de ~1h (um pedido por bloco). Cada bloco pede um pouco
    mais que a sua parte proporcional; o ajuste_cortes depois tira repetidos e fica com os n melhores.
    """
    blocos = dividir_em_blocos(segs)
    qtd = len(blocos)
    total = max(blocos[-1][1], 1.0)
    print(f"Pedindo pra IA escolher os {n} melhores momentos (pela transcricao"
          f"{f', em {qtd} blocos de ~1h' if qtd > 1 else ''})...")

    # Cache por bloco so em video com varios blocos: se um falhar, rodar de novo refaz so ele.
    # A pasta e apagada quando todos dao certo, entao uma nova execucao pede escolhas novas.
    pasta_cache = None
    if qtd > 1 and salvar_em is not None:
        pasta_cache = salvar_em.parent / "ia_blocos"

    def tarefa(i, ini, fim, segs_bloco):
        n_bloco = n if qtd == 1 else max(2, math.ceil(n * (fim - ini) / total) + 1)
        cache = None
        if pasta_cache is not None:
            cache = pasta_cache / f"{ini:.0f}-{fim:.0f}_n{n_bloco}_{dmin}-{dmax}_{modelo}.json"
        return _escolher_no_bloco(i, qtd, ini, fim, segs_bloco, picos, titulo, n_bloco,
                                  dmin, dmax, modelo, cache)

    with ThreadPoolExecutor(PARALELO_BLOCOS) as ex:
        futuros = [ex.submit(tarefa, i, ini, fim, s) for i, (ini, fim, s) in enumerate(blocos, 1)]
        registros, erros = [], []
        for i, fut in enumerate(futuros, 1):
            try:
                registros.append(fut.result())
            except Exception as e:  # os outros blocos continuam e ficam salvos
                erros.append(f"bloco {i}: {e}")
    if erros:
        raise RuntimeError(f"{len(erros)} de {qtd} blocos falharam na 1a passada. Os que deram certo "
                           "ficaram salvos: rode de novo e so os que faltaram serao refeitos.\n"
                           + "\n".join(erros))

    if salvar_em is not None:
        uso = {"entrada": sum(r["uso"]["entrada"] for r in registros),
               "saida": sum(r["uso"]["saida"] for r in registros)}
        salvar_em.write_text(json.dumps({"modelo": registros[0]["modelo"], "uso": uso, "blocos": registros},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    if pasta_cache is not None:
        shutil.rmtree(pasta_cache, ignore_errors=True)

    return [Corte.de_dict(c) for r in registros for c in r["resposta"]["cortes"]]
