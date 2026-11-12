"""Titulo no estilo A (PNG por cima do video) e credito automatico pela plataforma do link."""
import shutil

import pytest
from PIL import Image

from clipador.fontes.youtube import _plataforma, _usuario
from clipador.modelos import Credito, Video
from clipador.publicacao.credito import plataforma_do_link, resolver
from clipador.render import capa as mod_capa
from clipador.render.capa import gerar_capa, palavra_chave
from clipador.render.layouts import montar_filtro


def _video(**kw):
    return Video(caminho="v.mp4", pasta=".", titulo="t", **kw)


# ---------------------------------------------------------------- credito

def test_plataforma_do_link():
    assert plataforma_do_link("https://www.twitch.tv/videos/123") == "twitch"
    assert plataforma_do_link("https://youtu.be/abc") == "youtube"
    assert plataforma_do_link("https://www.youtube.com/watch?v=x") == "youtube"
    assert plataforma_do_link("D:/videos/live.mp4") is None


def test_credito_vem_do_link_sem_passar_nada():
    c = resolver("", "", "https://www.twitch.tv/videos/1", _video(plataforma="twitch", usuario="mount"))
    assert c == Credito("twitch", "mount", "twitch.tv/mount")
    c = resolver("", "", "https://youtu.be/x", _video(plataforma="youtube", usuario="@Gaules"))
    assert c.texto == "youtube.com/@Gaules"


def test_credito_passado_vence_o_do_link_mas_mantem_a_plataforma():
    c = resolver("@outro", "", "https://www.twitch.tv/videos/1", _video(plataforma="twitch", usuario="mount"))
    assert c.texto == "twitch.tv/outro"


def test_arquivo_local_sem_plataforma_fica_sem_icone():
    assert resolver("@mount", "", "D:/live.mp4", _video()) == Credito(None, "mount", "@mount")
    assert resolver("@mount", "twitch", "D:/live.mp4", _video()).texto == "twitch.tv/mount"
    assert resolver("", "", "D:/live.mp4", _video()) is None


def test_credito_com_espaco_e_texto_livre():
    c = resolver("Clip do Gaules", "", "https://www.twitch.tv/videos/1", _video(plataforma="twitch"))
    assert c == Credito(None, "", "Clip do Gaules")


def test_usuario_e_plataforma_do_yt_dlp():
    assert _plataforma({"extractor_key": "TwitchVod"}) == "twitch"
    assert _plataforma({"extractor_key": "Youtube"}) == "youtube"
    assert _plataforma({"extractor_key": "Generic"}) is None
    assert _usuario({"uploader_id": "@Gaules"}) == "Gaules"
    assert _usuario({"uploader_id": "UCabcdefghijklmnopqrstuv", "uploader": "Canal"}) == "Canal"
    assert _usuario({}) is None


# ---------------------------------------------------------------- capa (titulo + credito)

def test_palavra_chave_e_a_ultima_com_letras():
    assert palavra_chave(["Fugi", "da", "policia", "🚓🔥"]) == 2
    assert palavra_chave(["🔥"]) == -1


def _tem_cor(img, cor, tol=30, regiao=None):
    px = img.crop(regiao) if regiao else img
    for r, g, b, a in px.get_flattened_data():
        if a > 200 and abs(r - cor[0]) < tol and abs(g - cor[1]) < tol and abs(b - cor[2]) < tol:
            return True
    return False


def test_capa_tem_caixa_branca_palavra_rosa_e_icone_da_twitch(tmp_path):
    arq = gerar_capa(tmp_path / "c.png", "Emboscada dos Vagos virou tiroteio",
                     Credito("twitch", "mount", "twitch.tv/mount"))
    img = Image.open(arq).convert("RGBA")
    assert img.size == (1080, 1920)
    assert img.getpixel((540, 950))[3] == 0                         # meio do video fica livre
    topo = (0, 200, 1080, 520)
    assert _tem_cor(img, (255, 255, 255), 5, topo)                  # caixa branca
    assert _tem_cor(img, mod_capa.ROSA, 40, topo)                   # palavra-chave rosa
    assert _tem_cor(img, (145, 70, 255), 30, (0, 110, 1080, 200))   # roxo da Twitch na pilula


def test_capa_sem_credito_e_sem_titulo_e_transparente(tmp_path):
    img = Image.open(gerar_capa(tmp_path / "c.png", "", None)).convert("RGBA")
    assert img.getextrema()[3] == (0, 0)


def test_titulo_longo_quebra_em_varias_linhas_sem_sair_da_tela(tmp_path):
    titulo = "Esse titulo e enorme e precisa quebrar em varias linhas para caber na tela do TikTok"
    img = Image.open(gerar_capa(tmp_path / "c.png", titulo, None)).convert("RGBA")
    colunas = [x for x in range(1080) if img.getpixel((x, 300))[3] > 200]
    assert colunas and min(colunas) >= 60 and max(colunas) <= 1020


def test_sem_fonte_de_emoji_tira_o_emoji(tmp_path, monkeypatch):
    monkeypatch.setattr(mod_capa, "FONTES_EMOJI", [])
    gerar_capa(tmp_path / "c.png", "🔥🔥", None)                  # so emoji: nao desenha nada, nao quebra
    assert Image.open(tmp_path / "c.png").getextrema()[3] == (0, 0)


def test_filtro_poe_a_capa_por_cima():
    f = montar_filtro("crop", "c.ass", capa=True)
    assert f.endswith("subtitles=c.ass[base];[base][1:v]overlay=0:0[v]")
    assert montar_filtro("crop", "c.ass").endswith("subtitles=c.ass[v]")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg nao instalado")
def test_render_com_capa(tmp_path):
    from clipador.render.ffmpeg import renderizar
    from clipador.render.legendas import gerar_ass
    from clipador.util import rodar
    v = tmp_path / "v.mp4"
    rodar(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x223344:s=1280x720:d=4",
           "-c:v", "libx264", "-preset", "ultrafast", str(v)])
    gerar_ass(tmp_path / "c.ass", [], 0, 3, "", "")
    gerar_capa(tmp_path / "c_capa.png", "Titulo de teste", Credito("youtube", "x", "youtube.com/@x"))
    saida = renderizar(v, tmp_path, "c", 0, 3, "blur", capa="c_capa.png")
    quadro = tmp_path / "q.png"
    rodar(["ffmpeg", "-y", "-v", "error", "-ss", "2.5", "-i", str(saida), "-frames:v", "1", str(quadro)])
    img = Image.open(quadro).convert("RGB")
    assert img.size == (1080, 1920)
    assert _tem_cor(img.convert("RGBA"), (255, 255, 255), 12, (0, 200, 1080, 400))   # titulo ate o fim
    assert _tem_cor(img.convert("RGBA"), (255, 0, 0), 40, (0, 110, 1080, 200))      # play do YouTube
