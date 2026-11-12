"""Orquestra as etapas: video -> transcricao -> picos -> escolha -> ajuste -> render -> posts."""
from pathlib import Path

from clipador import ui
from clipador.analise.audio import picos_de_audio
from clipador.analise.cenas import atividade_visual, picos_visuais
from clipador.analise.chat import obter_tempos_chat, picos_de_chat
from clipador.analise.transcricao import transcrever
from clipador.config import Config
from clipador.fontes import obter_video
from clipador.publicacao.credito import resolver as resolver_credito
from clipador.publicacao.posts import montar_post, salvar_posts
from clipador.render.capa import gerar_capa
from clipador.render.ffmpeg import checar_ffmpeg, duracao, renderizar
from clipador.render.legendas import gerar_ass
from clipador.selecao.ajuste import ajustar_cortes
from clipador.selecao.heuristica import candidatos_visuais, escolher_sem_ia
from clipador.selecao import ia
from clipador.selecao.ia import escolher_com_ia
from clipador.selecao.reprise import Reprise
from clipador.selecao.visao import escolher_com_visao
from clipador.util import fmt


def _picos_chat(fonte: str, pasta: Path, cfg: Config) -> list[dict]:
    if not (cfg.chat or cfg.chat_arquivo) or cfg.sem_ia:
        return []
    tempos = obter_tempos_chat(fonte, pasta, cfg.chat_arquivo)
    picos = picos_de_chat(tempos)
    if tempos:
        ui.ok(f"chat: {len(tempos)} mensagens, {len(picos)} picos")
    return picos


def _picos_visuais(video: Path, pasta: Path, cfg: Config) -> list[dict]:
    if not cfg.cenas or cfg.sem_ia:
        return []
    cache = pasta / "atividade_visual.json"
    if cache.exists():
        ativ = atividade_visual(video, cache=cache)
    else:
        with console_status("medindo o movimento na tela (so os keyframes)..."):
            ativ = atividade_visual(video, cache=cache)
    picos = picos_visuais(ativ)
    ui.ok(f"movimento na tela: {len(picos)} picos")
    return picos


def console_status(msg: str):
    return ui.console.status(ui.Text("  " + msg), spinner="dots", spinner_style="rosa")


def executar(fonte: str, cfg: Config) -> dict:
    """Um video do comeco ao fim. Devolve {"titulo", "pasta" (dos cortes), "posts"}."""
    checar_ffmpeg()
    com_visao = cfg.visao and not cfg.sem_ia
    ui.iniciar(6 if com_visao else 5)

    # 1. video
    with ui.etapa("Video"):
        video = obter_video(fonte, Path(cfg.saida).resolve())
        video.duracao = duracao(video.caminho)
        ui.ok(f"{video.titulo}  ({fmt(video.duracao)})")
        ui.evento("video", titulo=video.titulo, duracao=video.duracao, pasta=str(video.pasta))
        credito = resolver_credito(cfg.credito, cfg.plataforma, fonte, video)
        if credito is not None:
            ui.ok(f"credito: {credito.texto}")
        else:
            ui.aviso("sem credito: passe --credito @usuario")
    ia.reprise = None
    if cfg.reprisar_ia and not cfg.sem_ia:
        ia.reprise = Reprise(video.pasta, com_visao)
        ui.aviso("reprise: usando as respostas salvas da ultima execucao, sem chamar o Claude")

    # 2-3. analise (cada uma com cache na pasta do video)
    with ui.etapa("Transcricao"):
        segs = transcrever(video.caminho, video.pasta, cfg.whisper, cfg.idioma)
    with ui.etapa("Sinais"):
        cache_audio = video.pasta / "picos_audio.json"
        if cache_audio.exists():
            picos = picos_de_audio(video.caminho, cache=cache_audio)
        else:
            with console_status("procurando os picos de volume..."):
                picos = picos_de_audio(video.caminho, cache=cache_audio)
        ui.ok(f"audio: {len(picos)} picos de volume")
        picos_chat = _picos_chat(fonte, video.pasta, cfg)
        picos_vis = _picos_visuais(video.caminho, video.pasta, cfg)
    sinais_ia = {"picos_chat": picos_chat, "picos_vis": picos_vis}

    # 4. escolha
    if cfg.sem_ia:
        with ui.etapa("Escolha pelos picos de audio"):
            brutos = escolher_sem_ia(picos, cfg.cortes, cfg.dmin, cfg.dmax)
            cortes = ajustar_cortes(brutos, segs, video.duracao, cfg.cortes, cfg.dmin, cfg.dmax)
            ui.ok(f"{len(cortes)} cortes nos maiores picos de audio")
    elif not cfg.visao:
        with ui.etapa("Escolha pela fala"):
            brutos = escolher_com_ia(segs, picos, video.titulo, cfg.cortes, cfg.dmin, cfg.dmax,
                                     cfg.modelo, salvar_em=video.pasta / "resposta_ia.json", **sinais_ia)
            cortes = ajustar_cortes(brutos, segs, video.duracao, cfg.cortes, cfg.dmin, cfg.dmax)
            ui.ok(f"{len(cortes)} cortes escolhidos")
    else:
        # 1a passada: fala (Whisper) + sinais -> candidatos, ja ajustados em frases e sem sobreposicao
        with ui.etapa("1a passada: candidatos pela fala"):
            n_cand = max(cfg.candidatos, cfg.cortes)
            brutos = escolher_com_ia(segs, picos, video.titulo, n_cand, cfg.dmin, cfg.dmax,
                                     cfg.modelo, salvar_em=video.pasta / "resposta_ia.json", **sinais_ia)
            candidatos = ajustar_cortes(brutos, segs, video.duracao, n_cand, cfg.dmin, cfg.dmax)
            ui.ok(f"{len(candidatos)} candidatos pela fala")
            # + trechos de muita acao na tela que a fala nao pegou (a 2a passada decide se prestam)
            extras = candidatos_visuais(picos_vis, candidatos, segs, video.duracao,
                                        cfg.candidatos_visuais, cfg.dmin, cfg.dmax)
            if extras:
                ui.ok(f"+ {len(extras)} candidatos visuais (muito movimento na tela): "
                      + ", ".join(fmt(c.inicio) for c in extras))
        # 2a passada: prints 1/s + fala + sinais de cada candidato -> os N melhores entre eles
        with ui.etapa("2a passada: a IA olha a tela"):
            cortes = escolher_com_visao(candidatos + extras, segs, video.caminho, video.pasta / "frames",
                                        video.titulo, cfg.cortes, cfg.modelo,
                                        salvar_em=video.pasta / "resposta_visao.json",
                                        sinais={"audio": picos, "chat": picos_chat, "visual": picos_vis},
                                        dmin=cfg.dmin, dmax=cfg.dmax, total=video.duracao)

    # 5. render + 6. posts
    pasta_cortes = video.pasta / "cortes"
    pasta_cortes.mkdir(exist_ok=True)
    posts = []
    with ui.etapa("Render"):
        # a barra anda em segundos de corte prontos, conforme o ffmpeg avanca
        with ui.barra("renderizando", sum(c.duracao for c in cortes), unidade="tempo") as barra:
            feito = 0.0
            for i, c in enumerate(cortes, 1):
                nome = f"corte_{i:02d}"
                barra.ate(feito, descricao=f"  {nome}/{len(cortes):02d}")
                ass = pasta_cortes / f"{nome}.ass"
                capa = pasta_cortes / f"{nome}_capa.png"
                gerar_ass(ass, segs, c.inicio, c.fim, "", "")   # titulo e credito vao na capa (PNG)
                gerar_capa(capa, c.titulo, credito)
                try:
                    renderizar(video.caminho, pasta_cortes, nome, c.inicio, c.fim, cfg.modo, cfg.facecam,
                               progresso=lambda t, base=feito, d=c.duracao: barra.ate(base + min(t, d)),
                               capa=capa.name)
                finally:
                    ass.unlink(missing_ok=True)
                    capa.unlink(missing_ok=True)
                feito += c.duracao
                barra.ate(feito)
                posts.append(montar_post(c, f"{nome}.mp4", credito.texto if credito else "",
                                         cfg.hashtags_extras))
                ui.ok(f"{nome}.mp4  {fmt(c.inicio)} -> {fmt(c.fim)}  {c.titulo or ''}")
        salvar_posts(pasta_cortes, posts)
        ui.ok("posts.txt e posts.json com legenda, hashtags e credito")

    ui.resumo(cortes, pasta_cortes, com_nota=not cfg.sem_ia)
    return {"titulo": video.titulo, "pasta": pasta_cortes, "posts": posts}
