"""2a passada da escolha: a IA ve os prints (1 por segundo) de cada candidato junto com a fala.

A 1a passada (ia.py) escolhe os candidatos so pela transcricao (e sinais), entao os limites que ela
sugere sao chutes: ela nao sabe quando a briga ou a perseguicao acaba na tela. Aqui cada candidato
vira uma chamada com as imagens do trecho MAIS uma margem antes e depois (MARGEM_ANTES/DEPOIS), a transcricao
e os sinais. A IA da a nota final e devolve inicio/fim corrigidos (comeca no contexto, termina depois
do desfecho). Depois, ajustar_cortes encaixa os novos limites na fala, aplica min/max, tira
sobreposicao e fica com os N de maior nota.

Uma chamada por candidato porque 15 trechos de 60s dariam ~900 imagens, bem acima do
limite de imagens por pedido.
"""
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from clipador import ui
from clipador.analise.frames import amostrar, extrair_frames
from clipador.modelos import Corte, Segmento
from clipador.selecao import ia
from clipador.selecao.ajuste import ajustar_cortes
from clipador.selecao.ia import chamar_ia
from clipador.util import fmt

MAX_FRAMES = 90      # por chamada; abaixo do limite de imagens por pedido
PARALELO = 4         # processos do Claude Code ao mesmo tempo
MARGEM_ANTES = 40    # segundos mostrados antes do trecho sugerido (o problema mais comum e faltar contexto)
MARGEM_DEPOIS = 20   # segundos mostrados depois (para achar o fim do desfecho/reacao)

# Tarefa da 2a passada. O criterio (o que e um bom corte, escala de nota, textos) vem do
# GUIA_CLIPAGEM, que vai como prompt de sistema em toda chamada (ia.SYSTEM).
PROMPT = """<tarefa>
Voce vai REVISAR um candidato a corte olhando os prints do video (1 por segundo) junto com a fala.
A triagem nao viu as imagens: os limites sugeridos sao aproximados e costumam cortar contexto no
inicio ou o desfecho no final.
</tarefa>

<video>
Titulo: "{titulo}"
</video>

<candidato>
Trecho sugerido: {ini:.1f}s a {fim:.1f}s ({fmt_ini} a {fmt_fim}, {dur:.0f}s)
Climax indicado pela triagem: {climax}
Contexto indicado pela triagem: {contexto}
Titulo sugerido: "{titulo_corte}" | motivo: {motivo}
</candidato>

<o_que_voce_ve>
Prints de {ext_ini:.1f}s a {ext_fim:.1f}s: o trecho sugerido mais {margem_antes:.0f}s antes e
{margem_depois:.0f}s depois. Cada print vem depois de uma marca "t=Xs" com o tempo no video original.
</o_que_voce_ve>

<passos>
1. Veja o que acontece na tela do inicio ao fim da janela.
2. Ache o climax na imagem (pode ser diferente do indicado pela triagem).
3. A partir do climax, volte ate o primeiro momento em que a situacao ja esta acontecendo e da
   para entender: esse e o INICIO.
4. A partir do climax, avance ate a acao se resolver e a reacao terminar: esse e o FIM.
5. Confira a duracao ({dmin} a {dmax}s). Se passar, corte tempo morto do comeco antes de
   cortar o desfecho.
6. Se o contexto necessario comeca antes da janela que voce ve, use o inicio da janela e
   marque falta_contexto = true.
7. De a nota do corte FINAL (com os seus limites) pela escala do guia e reescreva os textos.
</passos>

<transcricao>
{transcricao}
</transcricao>

<sinais>
{sinais}
</sinais>
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "inicio": {"type": "number"},
        "fim": {"type": "number"},
        "falta_contexto": {"type": "boolean"},
        "nota": {"type": "number"},
        "titulo": {"type": "string"},
        "legenda_post": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "motivo": {"type": "string"},
    },
    "required": ["inicio", "fim", "falta_contexto", "nota", "titulo", "legenda_post", "hashtags",
                 "motivo"],
    "additionalProperties": False,
}


def janela_com_margem(c: Corte, total: float, antes: float = MARGEM_ANTES,
                      depois: float = MARGEM_DEPOIS) -> tuple[float, float]:
    return max(0.0, c.inicio - antes), min(total, c.fim + depois)


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


def _avaliar(c: Corte, ext: tuple[float, float], frames: list[Path], segs: list[Segmento],
             titulo: str, modelo: str, dmin: int, dmax: int, sinais: dict | None = None):
    ext_ini, ext_fim = ext
    texto = PROMPT.format(titulo=titulo, ini=c.inicio, fim=c.fim, dur=c.duracao,
                          fmt_ini=fmt(c.inicio), fmt_fim=fmt(c.fim),
                          ext_ini=ext_ini, ext_fim=ext_fim, dmin=dmin, dmax=dmax,
                          margem_antes=c.inicio - ext_ini, margem_depois=ext_fim - c.fim,
                          climax=f"{c.climax:.1f}s" if c.climax is not None else "(nao indicado)",
                          contexto=c.contexto or "(nao indicado)",
                          titulo_corte=c.titulo or "(sem titulo)", motivo=c.motivo,
                          transcricao=_transcricao_do_trecho(segs, ext_ini, ext_fim),
                          sinais=_sinais_do_trecho(sinais, ext_ini, ext_fim))
    conteudo: list[dict] = [{"type": "text", "text": texto}]
    for i, f in amostrar(frames, MAX_FRAMES):
        conteudo.append({"type": "text", "text": f"t={ext_ini + i:.0f}s"})   # frame i = ext_ini + i s
        conteudo.append(_imagem(f))
    dados, info = chamar_ia(conteudo, SCHEMA, modelo)
    return dados, info["uso"]


def _limites_da_ia(c: Corte, dados: dict, ext: tuple[float, float]) -> tuple[float, float]:
    """Limites devolvidos pela IA, presos a janela que ela viu. Se vierem absurdos, mantem os originais."""
    ext_ini, ext_fim = ext
    ini = min(max(float(dados["inicio"]), ext_ini), ext_fim)
    fim = min(max(float(dados["fim"]), ext_ini), ext_fim)
    if fim - ini < 5:
        return c.inicio, c.fim
    return ini, fim


def escolher_com_visao(candidatos: list[Corte], segs: list[Segmento], video: Path,
                       pasta_frames: Path, titulo: str, n: int, modelo: str,
                       salvar_em: Path | None = None, sinais: dict | None = None,
                       dmin: int = 20, dmax: int = 60, total: float | None = None) -> list[Corte]:
    """Da a nota final e corrige os limites de cada candidato olhando os frames; devolve os `n` melhores.

    `sinais` = {"audio": [...], "chat": [...], "visual": [...]}: os picos que caem em cada trecho
    vao no prompt daquele candidato. `total` = duracao do video (limita a margem no final).
    """
    if total is None:
        total = max((c.fim for c in candidatos), default=0.0) + MARGEM_DEPOIS
    janelas = [janela_com_margem(c, total) for c in candidatos]

    ui.info(f"{len(candidatos)} candidatos, com {MARGEM_ANTES}s antes e {MARGEM_DEPOIS}s depois de cada um")
    if ia.reprise is not None:   # --reprisar-ia: as respostas ja estao salvas, ninguem vai olhar os prints
        frames = [[] for _ in janelas]
        ui.detalhe("reprise: pulando os prints")
    else:
        frames = []
        with ui.barra("tirando prints (1/s)", len(janelas)) as barra:
            for a, b in janelas:
                frames.append(extrair_frames(video, a, b, pasta_frames / f"{a:.2f}-{b:.2f}"))
                barra.avancar()
        ui.ok(f"{sum(len(f) for f in frames)} prints prontos")

    erros = []
    with ui.barra("Claude olhando a tela", len(candidatos), claude=True) as barra,             ThreadPoolExecutor(PARALELO) as ex:
        futuros = [ex.submit(_avaliar, c, j, f, segs, titulo, modelo, dmin, dmax, sinais)
                   for c, j, f in zip(candidatos, janelas, frames)]
        for fut in futuros:
            fut.add_done_callback(lambda _: barra.avancar())
        resultados = []
        for c, fut in zip(candidatos, futuros):
            try:
                resultados.append(fut.result())
            except Exception as e:  # um candidato com erro nao derruba os outros
                erros.append(f"falhou avaliar {fmt(c.inicio)}-{fmt(c.fim)}: {e}")
                resultados.append((None, None))
    for e in erros:
        ui.aviso(e)

    avaliados, registro, linhas = [], [], []
    for c, j, f, (dados, uso) in zip(candidatos, janelas, frames, resultados):
        if dados is None:
            # sem a avaliacao visual, fica com a nota da 1a passada, mas atras dos avaliados
            avaliados.append(replace(c, nota=min(c.nota, 5.0)))
        else:
            ini, fim = _limites_da_ia(c, dados, j)
            avaliados.append(replace(c, inicio=ini, fim=fim, nota=float(dados["nota"]),
                                     titulo=dados["titulo"] or c.titulo,
                                     legenda_post=dados["legenda_post"] or c.legenda_post,
                                     hashtags=list(dados["hashtags"]) or c.hashtags,
                                     motivo=dados["motivo"] or c.motivo))
        a = avaliados[-1]
        falta = bool(dados and dados.get("falta_contexto"))
        registro.append({"inicio_1a_passada": c.inicio, "fim_1a_passada": c.fim,
                         "inicio": a.inicio, "fim": a.fim, "falta_contexto": falta, "frames": len(f),
                         "nota_1a_passada": c.nota, "uso": uso, "resposta": dados})
        linhas.append((c, a, dados is not None, falta))
    ui.tabela_visao(linhas)

    if salvar_em is not None:
        salvar_em.write_text(json.dumps({"modelo": modelo, "candidatos": registro},
                                        ensure_ascii=False, indent=2), encoding="utf-8")

    falhas = sum(1 for dados, _ in resultados if dados is None)
    if falhas == len(candidatos):
        raise RuntimeError(
            f"A 2a passada falhou em todos os {falhas} candidatos (limite do plano? veja /usage "
            "no claude). Nada foi renderizado. Tente mais tarde ou use --sem-visao.")
    if falhas:
        ui.aviso(f"ATENCAO: {falhas} de {len(candidatos)} candidatos nao foram avaliados com imagem; "
                 "eles ficaram com nota <= 5 e so entram se faltar candidato avaliado.")

    # novos limites podem ter crescido e se sobreposto: o ajuste resolve (maior nota ganha)
    return ajustar_cortes(avaliados, segs, total, n, dmin, dmax)
