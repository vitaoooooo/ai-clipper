"""2a passada da escolha: a IA ve os prints (1 por segundo) de cada candidato junto com a fala.

A 1a passada (ia.py) escolhe de 10 a 15 candidatos so pela transcricao. Aqui cada candidato
vira uma chamada com as imagens do trecho + a transcricao dele, e a IA da a nota final.
Os N cortes com maior nota sao os escolhidos. So candidatos da 1a passada podem ser escolhidos.

Uma chamada por candidato porque 15 trechos de 60s dariam ~900 imagens, bem acima do
limite de imagens por pedido.
"""
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from clipador.analise.frames import amostrar, extrair_frames
from clipador.modelos import Corte, Segmento
from clipador.selecao.ia import chamar_ia
from clipador.util import fmt

MAX_FRAMES = 90      # por chamada; abaixo do limite de imagens por pedido
PARALELO = 4         # processos do Claude Code ao mesmo tempo

PROMPT = """Voce e editor de cortes virais para TikTok. O video original se chama "{titulo}".
Uma primeira triagem (pela fala ou pelo movimento na tela) separou este trecho como candidato a corte.
Agora voce tem tambem os prints do video, 1 por segundo (cada imagem vem depois de uma marca
"t=Xs", o tempo dentro do trecho). Avalie o trecho olhando a IMAGEM junto com a FALA.

Trecho: {ini:.1f}s a {fim:.1f}s ({dur:.0f}s)
Sugestao da triagem: titulo "{titulo_corte}" | motivo: {motivo}

TRANSCRICAO DO TRECHO (tempos do video original):
{transcricao}

SINAIS NO TRECHO (tempos do video original):
{sinais}

Considere:
- Os primeiros 2 segundos prendem visualmente (acao, reacao, algo chamativo na tela)?
- A imagem confirma o que a fala sugere (ou a fala engana e na tela nao acontece nada)?
- Ha momentos visuais fortes que a transcricao nao mostra (explosao, perseguicao, bug, morte, susto)?
- A tela fica parada, em menu, loading, tela preta ou com algo que estraga o corte?
- Funciona sozinho, sem contexto do resto do video?

Seja exigente e use a escala toda: 9-10 so para trechos com imagem e fala fortes, 5 ou menos
se a imagem nao ajuda. Reescreva titulo, legenda e hashtags levando em conta o que aparece na tela.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "nota": {"type": "number"},
        "titulo": {"type": "string"},
        "legenda_post": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "motivo": {"type": "string"},
    },
    "required": ["nota", "titulo", "legenda_post", "hashtags", "motivo"],
    "additionalProperties": False,
}


def _transcricao_do_trecho(segs: list[Segmento], ini: float, fim: float) -> str:
    linhas = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
              for s in segs if s["end"] > ini and s["start"] < fim]
    return "\n".join(linhas) or "(sem fala)"


def _sinais_do_trecho(sinais: dict | None, ini: float, fim: float) -> str:
    """Picos de audio/chat/movimento que caem dentro do trecho, para a IA cruzar com as imagens."""
    s = sinais or {}
    linhas = []
    for p in s.get("audio", []):
        if ini <= p["segundo"] < fim:
            linhas.append(f"{p['segundo']}s: audio alto (+{p['acima_da_media_db']} dB)")
    for p in s.get("chat", []):
        if ini <= p["segundo"] < fim:
            linhas.append(f"{p['segundo']}s: chat explodiu ({p['vezes_a_media']}x a media)")
    for p in s.get("visual", []):
        if p["segundo"] < fim and p["segundo"] + 10 > ini:
            linhas.append(f"{p['segundo']}s: muito movimento na tela ({p['movimento_x_media']}x a media)")
    return "\n".join(linhas) or "(nenhum)"


def _imagem(caminho: Path) -> dict:
    dados = base64.standard_b64encode(caminho.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": dados}}


def _avaliar(c: Corte, frames: list[Path], segs: list[Segmento], titulo: str, modelo: str,
             sinais: dict | None = None):
    texto = PROMPT.format(titulo=titulo, ini=c.inicio, fim=c.fim, dur=c.duracao,
                          titulo_corte=c.titulo or "(sem titulo)", motivo=c.motivo,
                          transcricao=_transcricao_do_trecho(segs, c.inicio, c.fim),
                          sinais=_sinais_do_trecho(sinais, c.inicio, c.fim))
    conteudo: list[dict] = [{"type": "text", "text": texto}]
    for i, f in amostrar(frames, MAX_FRAMES):
        conteudo.append({"type": "text", "text": f"t={i}s"})
        conteudo.append(_imagem(f))
    dados, info = chamar_ia(conteudo, SCHEMA, modelo)
    return dados, info["uso"]


def escolher_com_visao(candidatos: list[Corte], segs: list[Segmento], video: Path,
                       pasta_frames: Path, titulo: str, n: int, modelo: str,
                       salvar_em: Path | None = None, sinais: dict | None = None) -> list[Corte]:
    """Da a nota final a cada candidato olhando os frames e devolve os `n` melhores.

    `sinais` = {"audio": [...], "chat": [...], "visual": [...]}: os picos que caem em cada trecho
    vao no prompt daquele candidato.
    """
    print(f"Tirando prints (1/s) dos {len(candidatos)} candidatos...")
    frames = [extrair_frames(video, c.inicio, c.fim, pasta_frames / f"{c.inicio:.2f}-{c.fim:.2f}")
              for c in candidatos]

    print(f"Pedindo pra IA avaliar os candidatos com imagem + fala...")
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = [ex.submit(_avaliar, c, f, segs, titulo, modelo, sinais)
                   for c, f in zip(candidatos, frames)]
        resultados = []
        for c, fut in zip(candidatos, futuros):
            try:
                resultados.append(fut.result())
            except Exception as e:  # um candidato com erro nao derruba os outros
                print(f"  aviso: falhou avaliar {fmt(c.inicio)}-{fmt(c.fim)}: {e}")
                resultados.append((None, None))

    avaliados, registro = [], []
    for c, f, (dados, uso) in zip(candidatos, frames, resultados):
        if dados is None:
            # sem a avaliacao visual, fica com a nota da 1a passada, mas atras dos avaliados
            avaliados.append(replace(c, nota=min(c.nota, 5.0)))
        else:
            avaliados.append(replace(c, nota=float(dados["nota"]),
                                     titulo=dados["titulo"] or c.titulo,
                                     legenda_post=dados["legenda_post"] or c.legenda_post,
                                     hashtags=list(dados["hashtags"]) or c.hashtags,
                                     motivo=dados["motivo"] or c.motivo))
        registro.append({"inicio": c.inicio, "fim": c.fim, "frames": len(f),
                         "nota_1a_passada": c.nota, "uso": uso, "resposta": dados})
        print(f"  {fmt(c.inicio)}-{fmt(c.fim)}  nota {c.nota:g} -> {avaliados[-1].nota:g}")

    if salvar_em is not None:
        salvar_em.write_text(json.dumps({"modelo": modelo, "candidatos": registro},
                                        ensure_ascii=False, indent=2), encoding="utf-8")

    falhas = sum(1 for dados, _ in resultados if dados is None)
    if falhas == len(candidatos):
        raise RuntimeError(
            f"A 2a passada falhou em todos os {falhas} candidatos (limite do plano? veja /usage "
            "no claude). Nada foi renderizado. Tente mais tarde ou use --sem-visao.")
    if falhas:
        print(f"\n  ATENCAO: {falhas} de {len(candidatos)} candidatos nao foram avaliados com imagem; "
              "eles ficaram com nota <= 5 e so entram se faltar candidato avaliado.\n")

    melhores = sorted(avaliados, key=lambda c: c.nota, reverse=True)[:n]
    return sorted(melhores, key=lambda c: c.inicio)
