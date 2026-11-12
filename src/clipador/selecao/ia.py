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

from clipador import ui
from clipador.modelos import Corte, Pico, Segmento
from clipador.util import fmt

# Guia de clipagem: vai como prompt de sistema em TODAS as chamadas (1a e 2a passada), para as duas
# usarem o mesmo criterio. Revisado e aprovado pelo usuario em 12/11/2026.
GUIA_CLIPAGEM = """Voce e um editor senior de cortes para TikTok, especialista em gameplay de GTA (modo historia,
online e RP) e em lives de streamers. Seu trabalho e transformar trechos de videos longos em
cortes que prendem quem NUNCA viu o video original.

O QUE E UM BOM CORTE
Um corte e uma mini-historia completa, com 4 partes:
1. Contexto: o espectador entende o que esta acontecendo (quem, onde, qual o objetivo ou o problema).
2. Escalada: a situacao fica mais tensa, engracada ou absurda.
3. Climax: o momento principal (a batida, a fuga, o bug, a frase, o susto).
4. Desfecho: o resultado e a reacao depois do climax (a risada, o grito, o "nao acredito").
Sem contexto, quem chega no corte nao entende e sai. Sem desfecho, o corte parece interrompido.
As duas falhas matam a retencao.

INICIO: GANCHO SEM PERDER CONTEXTO
- O titulo aparece na tela nos primeiros segundos e ja funciona como gancho. Por isso o corte
  NAO precisa comecar no climax: comece no inicio da situacao.
- Comece no primeiro momento em que algo ja esta acontecendo: a fala que apresenta a situacao,
  o inicio da acao, a primeira reacao. Corte so o tempo morto antes disso (andar sem rumo,
  menu, silencio).
- Na duvida entre perder contexto e ficar alguns segundos mais longo, fique mais longo
  (dentro do limite de duracao).

FIM
- Termine depois do desfecho E da reacao, num fim de frase ou numa pausa.
- Nunca no meio de uma fala ou de uma acao em andamento.
- Se a reacao continua por varios segundos e e boa, inclua.

O QUE FUNCIONA EM GTA
- Perseguicoes e fugas da policia, batidas espetaculares, assaltos que dao certo ou muito errado
- Brigas, tiroteios, mortes inesperadas ou engracadas
- Bugs e fisica absurda do jogo
- Interacoes engracadas com NPCs ou outros jogadores (RP)
- Reacoes fortes do streamer: raiva, risada, susto, frase marcante

O QUE EVITAR
- Menu, mapa, loading, tela preta, tela de morte longa, inventario
- Trechos que dependem de algo explicado muito antes no video
- Cutscenes longas da historia do jogo sem reacao do jogador

ESCALA DE NOTA (potencial viral, 0 a 10)
9-10: arco completo, climax forte na imagem e na fala; quem nunca viu o video entende e compartilha
7-8:  bom e completo, mas o climax e menos marcante
5-6:  interessante, mas falta contexto, desfecho ou forca visual
0-4:  confuso, parado ou sem nada acontecendo
Use a escala toda; nao de 8 para tudo.

TEXTOS DO POST (portugues do Brasil, COM acentuacao normal)
- titulo: ate 6 palavras, tom de TikTok, gera curiosidade sem entregar o final. Pode ter 1 emoji.
- legenda_post: 1 ou 2 frases curtas + uma pergunta para puxar comentarios.
- hashtags: 3 a 5 relevantes ao trecho (as hashtags fixas do canal sao adicionadas depois).

Responda somente com os dados pedidos, no formato do schema. Nao use ferramentas."""

# Tarefa da 1a passada (triagem): so transcricao + sinais, sem imagens.
PROMPT = """<tarefa>
Voce vai fazer a TRIAGEM de um video pela transcricao e por sinais automaticos. Voce NAO ve as
imagens: uma segunda etapa vai olhar os prints de cada trecho e ajustar os limites. Por isso:
- Prefira trechos com arco completo na fala (contexto -> climax -> reacao).
- Escolha limites generosos: comece no inicio da situacao e termine depois da reacao.
- Trechos com pouca fala mas sinais fortes (audio, chat, movimento) tambem podem ser bons.
</tarefa>

<video>
Titulo: "{titulo}"{parte}
</video>

<pedido>
Escolha os {n} melhores trechos para cortes independentes, cada um com {dmin} a {dmax} segundos,
sem sobreposicao. Para cada um:
- inicio, fim: em segundos do video
- climax: segundo do momento principal
- contexto: em uma frase, o que o espectador precisa saber para entender o corte
- titulo, legenda_post, hashtags: conforme o guia
- nota: conforme a escala do guia
- motivo: por que funciona e o que pode estar faltando
</pedido>

<sinais>
{sinais}
</sinais>

<transcricao>
{transcricao}
</transcricao>
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
                    "climax": {"type": "number"},
                    "contexto": {"type": "string"},
                    "titulo": {"type": "string"},
                    "legenda_post": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "nota": {"type": "number"},
                    "motivo": {"type": "string"},
                },
                "required": ["inicio", "fim", "climax", "contexto", "titulo", "legenda_post",
                             "hashtags", "nota", "motivo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cortes"],
    "additionalProperties": False,
}

SYSTEM = GUIA_CLIPAGEM
TIMEOUT = 900  # segundos por chamada
# variaveis que fariam o Claude Code cobrar por API em vez de usar a cota do plano
ENV_DE_API = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
# Abre o Claude Code "limpo": sem settings/CLAUDE.md do usuario, sem conectores MCP, sem skills.
# Medido em 12/11/2026: ~9.000 -> ~1.100 tokens de entrada por chamada, e o login do plano continua valendo.
ISOLAMENTO = ("--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands")


def texto_sinais(picos: list[Pico], picos_chat: list[dict] | None = None,
                 picos_vis: list[dict] | None = None) -> str:
    """Secoes de sinais para o prompt. Chat e movimento so aparecem se existirem."""
    partes = ["PICOS DE AUDIO (segundo e quantos dB acima da media):\n"
              + ("\n".join(f"{p['segundo']}s (+{p['acima_da_media_db']} dB)" for p in picos) or "nenhum")]
    if picos_chat:
        partes.append("PICOS DE CHAT (segundo em que o chat da live explode, mensagens em 5s e quantas "
                      "vezes a media):\n" + "\n".join(
                          f"{p['segundo']}s ({p['mensagens']} msgs, {p['vezes_a_media']}x)" for p in picos_chat))
    if picos_vis:
        partes.append("PICOS DE MOVIMENTO NA TELA (inicio de janelas de 10s com muita acao visual, quantas "
                      "vezes a media; podem ter pouca fala, mas tambem podem ser troca de cena ou menu):\n"
                      + "\n".join(f"{p['segundo']}s ({p['movimento_x_media']}x)" for p in picos_vis))
    return "\n\n".join(partes) + "\n"


def montar_prompt(segs: list[Segmento], picos: list[Pico], titulo: str,
                  n: int, dmin: int, dmax: int, parte: str = "",
                  picos_chat: list[dict] | None = None, picos_vis: list[dict] | None = None) -> str:
    linhas = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segs) or "(sem fala)"
    return PROMPT.format(titulo=titulo, n=n, dmin=dmin, dmax=dmax,
                         sinais=texto_sinais(picos, picos_chat, picos_vis).strip(),
                         transcricao=linhas, parte=parte)


def _no_intervalo(picos: list[dict] | None, ini: float, fim: float) -> list[dict]:
    return [p for p in (picos or []) if ini <= p["segundo"] < fim]


def _executavel_claude() -> str:
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError("Claude Code nao encontrado no PATH. Instale (claude.com/claude-code), "
                           "rode `claude` uma vez para logar com a conta do claude.ai, ou use --sem-ia.")
    return exe


# --reprisar-ia: quando ligado (pipeline), chamar_ia devolve as respostas salvas em vez de chamar o Claude
reprise = None


def chamar_ia(conteudo: str | list, schema: dict, modelo: str) -> tuple[dict, dict]:
    """Faz uma chamada pelo Claude Code com resposta em JSON (structured output).

    `conteudo` e um texto ou uma lista de blocos (texto/imagem), como na Messages API.
    Devolve (dados, info), onde info = {"modelo": ..., "uso": {"entrada": ..., "saida": ...}}.
    """
    if isinstance(conteudo, str):
        conteudo = [{"type": "text", "text": conteudo}]
    if reprise is not None:
        ui.uso.comecou()
        try:
            dados, info = reprise.responder(conteudo, schema)
        except Exception:
            ui.uso.terminou(ok=False)
            raise
        ui.uso.terminou(info["uso"].get("entrada", 0), info["uso"].get("saida", 0))
        return dados, info
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
    ui.uso.comecou()   # contador de tokens que aparece ao lado das barras de progresso
    try:
        dados, info, custo = _rodar_claude(cmd, mensagem, env, modelo)
    except Exception:
        ui.uso.terminou(ok=False)
        raise
    ui.uso.terminou(info["uso"]["entrada"], info["uso"]["saida"], custo)
    return dados, info


def _rodar_claude(cmd: list, mensagem: dict, env: dict, modelo: str) -> tuple[dict, dict, float]:
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
    # quanto custaria pela API (o Claude Code calcula); com o plano sai da cota, nao e cobrado
    return dados, info, float(resultado.get("total_cost_usd") or 0)


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
                       modelo, cache: Path | None, picos_chat=None, picos_vis=None):
    if cache is not None and cache.exists():
        if qtd > 1:
            ui.detalhe(f"bloco {i}/{qtd} ({fmt(ini)}-{fmt(fim)}): usando a resposta salva")
        return json.loads(cache.read_text(encoding="utf-8"))
    parte = ""
    if qtd > 1:
        parte = (f"\nEste video e longo e foi dividido em partes. Esta e a parte {i} de {qtd}, "
                 f"de {fmt(ini)} a {fmt(fim)}. Escolha os trechos so dentro dela.")
    prompt = montar_prompt(segs_bloco, _no_intervalo(picos, ini, fim), titulo, n_bloco, dmin, dmax, parte,
                           _no_intervalo(picos_chat, ini, fim), _no_intervalo(picos_vis, ini, fim))
    dados, info = chamar_ia(prompt, SCHEMA, modelo)
    if qtd > 1:
        ui.detalhe(f"bloco {i}/{qtd} ({fmt(ini)}-{fmt(fim)}): {len(dados.get('cortes', []))} trechos")
    registro = {"inicio": ini, "fim": fim, **info, "resposta": dados}
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")
    return registro


def escolher_com_ia(segs: list[Segmento], picos: list[Pico], titulo: str, n: int,
                    dmin: int, dmax: int, modelo: str, salvar_em: Path | None = None,
                    picos_chat: list[dict] | None = None,
                    picos_vis: list[dict] | None = None) -> list[Corte]:
    """Escolhe os cortes so pela transcricao (Whisper) e pelos picos de audio.

    Com a 2a passada ligada, isto vira a 1a passada: escolhe os candidatos.
    Lives longas sao divididas em blocos de ~1h (um pedido por bloco). Cada bloco pede um pouco
    mais que a sua parte proporcional; o ajuste_cortes depois tira repetidos e fica com os n melhores.
    """
    blocos = dividir_em_blocos(segs)
    qtd = len(blocos)
    total = max(blocos[-1][1], 1.0)
    ui.info(f"a IA le a transcricao e escolhe os {n} melhores momentos"
            f"{f' (em {qtd} blocos de ~1h)' if qtd > 1 else ''}")

    # Cache por bloco so em video com varios blocos: se um falhar, rodar de novo refaz so ele.
    # A pasta e apagada quando todos dao certo, entao uma nova execucao pede escolhas novas.
    pasta_cache = None
    if qtd > 1 and salvar_em is not None:
        pasta_cache = salvar_em.parent / "ia_blocos"

    def tarefa(i, ini, fim, segs_bloco):
        n_bloco = n if qtd == 1 else max(2, math.ceil(n * (fim - ini) / total) + 1)
        cache = None
        if pasta_cache is not None:
            sinais = f"c{int(bool(picos_chat))}v{int(bool(picos_vis))}"
            cache = pasta_cache / f"{ini:.0f}-{fim:.0f}_n{n_bloco}_{dmin}-{dmax}_{sinais}_{modelo}.json"
        return _escolher_no_bloco(i, qtd, ini, fim, segs_bloco, picos, titulo, n_bloco,
                                  dmin, dmax, modelo, cache, picos_chat, picos_vis)

    rotulo = "Claude lendo a transcricao" if qtd == 1 else "Claude lendo os blocos"
    with ui.barra(rotulo, qtd, claude=True) as barra, ThreadPoolExecutor(PARALELO_BLOCOS) as ex:
        futuros = [ex.submit(tarefa, i, ini, fim, s) for i, (ini, fim, s) in enumerate(blocos, 1)]
        for fut in futuros:
            fut.add_done_callback(lambda _: barra.avancar())
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
