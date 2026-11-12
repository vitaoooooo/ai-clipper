"""Orquestra as etapas: video -> transcricao -> picos -> escolha -> ajuste -> render -> posts."""
from pathlib import Path

from clipador.analise.audio import picos_de_audio
from clipador.analise.cenas import atividade_visual, picos_visuais
from clipador.analise.chat import obter_tempos_chat, picos_de_chat
from clipador.analise.transcricao import transcrever
from clipador.config import Config
from clipador.fontes import obter_video
from clipador.publicacao.posts import montar_post, salvar_posts
from clipador.render.ffmpeg import checar_ffmpeg, duracao, renderizar
from clipador.render.legendas import gerar_ass
from clipador.selecao.ajuste import ajustar_cortes
from clipador.selecao.heuristica import candidatos_visuais, escolher_sem_ia
from clipador.selecao.ia import escolher_com_ia
from clipador.selecao.visao import escolher_com_visao
from clipador.util import fmt


def _picos_chat(fonte: str, pasta: Path, cfg: Config) -> list[dict]:
    if not (cfg.chat or cfg.chat_arquivo) or cfg.sem_ia:
        return []
    tempos = obter_tempos_chat(fonte, pasta, cfg.chat_arquivo)
    picos = picos_de_chat(tempos)
    if tempos:
        print(f"Chat: {len(tempos)} mensagens, {len(picos)} picos")
    return picos


def _picos_visuais(video: Path, pasta: Path, cfg: Config) -> list[dict]:
    if not cfg.cenas or cfg.sem_ia:
        return []
    cache = pasta / "atividade_visual.json"
    if not cache.exists():
        print("Medindo o movimento na tela...")
    picos = picos_visuais(atividade_visual(video, cache=cache))
    print(f"Movimento na tela: {len(picos)} picos")
    return picos


def executar(fonte: str, cfg: Config) -> list[dict]:
    checar_ffmpeg()

    # 1. video
    video = obter_video(fonte, Path(cfg.saida).resolve())
    video.duracao = duracao(video.caminho)
    print(f"Video: {video.titulo} ({fmt(video.duracao)})")

    # 2-3. analise (cada uma com cache na pasta do video)
    segs = transcrever(video.caminho, video.pasta, cfg.whisper, cfg.idioma)
    picos = picos_de_audio(video.caminho, cache=video.pasta / "picos_audio.json")
    picos_chat = _picos_chat(fonte, video.pasta, cfg)
    picos_vis = _picos_visuais(video.caminho, video.pasta, cfg)
    sinais_ia = {"picos_chat": picos_chat, "picos_vis": picos_vis}

    # 4. escolha
    if cfg.sem_ia:
        brutos = escolher_sem_ia(picos, cfg.cortes, cfg.dmin, cfg.dmax)
        cortes = ajustar_cortes(brutos, segs, video.duracao, cfg.cortes, cfg.dmin, cfg.dmax)
    elif not cfg.visao:
        brutos = escolher_com_ia(segs, picos, video.titulo, cfg.cortes, cfg.dmin, cfg.dmax,
                                 cfg.modelo, salvar_em=video.pasta / "resposta_ia.json", **sinais_ia)
        cortes = ajustar_cortes(brutos, segs, video.duracao, cfg.cortes, cfg.dmin, cfg.dmax)
    else:
        # 1a passada: fala (Whisper) + sinais -> candidatos, ja ajustados em frases e sem sobreposicao
        n_cand = max(cfg.candidatos, cfg.cortes)
        brutos = escolher_com_ia(segs, picos, video.titulo, n_cand, cfg.dmin, cfg.dmax,
                                 cfg.modelo, salvar_em=video.pasta / "resposta_ia.json", **sinais_ia)
        candidatos = ajustar_cortes(brutos, segs, video.duracao, n_cand, cfg.dmin, cfg.dmax)
        print(f"{len(candidatos)} candidatos na 1a passada")
        # + trechos de muita acao na tela que a fala nao pegou (a 2a passada decide se prestam)
        extras = candidatos_visuais(picos_vis, candidatos, segs, video.duracao,
                                    cfg.candidatos_visuais, cfg.dmin, cfg.dmax)
        if extras:
            print(f"+ {len(extras)} candidatos visuais (muito movimento na tela): "
                  + ", ".join(fmt(c.inicio) for c in extras))
        # 2a passada: prints 1/s + fala + sinais de cada candidato -> os N melhores entre eles
        cortes = escolher_com_visao(candidatos + extras, segs, video.caminho, video.pasta / "frames",
                                    video.titulo, cfg.cortes, cfg.modelo,
                                    salvar_em=video.pasta / "resposta_visao.json",
                                    sinais={"audio": picos, "chat": picos_chat, "visual": picos_vis},
                                    dmin=cfg.dmin, dmax=cfg.dmax, total=video.duracao)

    # 5. render
    pasta_cortes = video.pasta / "cortes"
    pasta_cortes.mkdir(exist_ok=True)
    posts = []
    for i, c in enumerate(cortes, 1):
        nome = f"corte_{i:02d}"
        print(f"Renderizando {nome}: {fmt(c.inicio)} -> {fmt(c.fim)}  {c.titulo}")
        ass = pasta_cortes / f"{nome}.ass"
        gerar_ass(ass, segs, c.inicio, c.fim, c.titulo, cfg.credito)
        try:
            renderizar(video.caminho, pasta_cortes, nome, c.inicio, c.fim, cfg.modo, cfg.facecam)
        finally:
            ass.unlink(missing_ok=True)
        posts.append(montar_post(c, f"{nome}.mp4", cfg.credito, cfg.hashtags_extras))

    # 6. posts
    salvar_posts(pasta_cortes, posts)
    print(f"\nPronto! {len(posts)} cortes em: {pasta_cortes}")
    return posts
