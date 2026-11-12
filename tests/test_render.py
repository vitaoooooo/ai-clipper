"""Testes que rodam o ffmpeg de verdade num video sintetico (pulados se nao tiver ffmpeg)."""
import shutil

import pytest

from clipador.analise.audio import picos_de_audio
from clipador.analise.cenas import trocas_de_cena
from clipador.render.ffmpeg import duracao, renderizar
from clipador.render.legendas import gerar_ass
from clipador.util import rodar

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg nao instalado")


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    """12s em 1280x720: 6s de barras de cor + 6s de outro padrao (troca de cena em 6s),
    com um bip alto entre 8s e 9s."""
    pasta = tmp_path_factory.mktemp("video")
    v = pasta / "teste.mp4"
    rodar(["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=6",
           "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=30:duration=6",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
           "-filter_complex",
           "[0:v][1:v]concat=n=2:v=1[v];"
           "[2:a]volume='if(between(t,8,9),1,0.02)':eval=frame[a]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
           "-c:a", "aac", str(v)])
    return v


def dimensoes(arquivo):
    out = rodar(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height", "-of", "csv=p=0", str(arquivo)])
    return tuple(int(x) for x in out.strip().split(","))


@pytest.mark.parametrize("modo,facecam", [("blur", None), ("crop", None),
                                          ("facecam", (0.0, 0.0, 0.3, 0.3))])
def test_renderiza_vertical_em_todos_os_modos(video, tmp_path, modo, facecam):
    segs = [{"start": 1, "end": 3, "text": "", "words": [
        {"start": 1, "end": 2, "word": "teste"}, {"start": 2, "end": 3, "word": "legenda"}]}]
    gerar_ass(tmp_path / "c.ass", segs, 1, 5, "titulo", "@canal")
    saida = renderizar(video, tmp_path, "c", 1, 5, modo, facecam)
    assert dimensoes(saida) == (1080, 1920)
    assert 3.5 < duracao(saida) < 4.5


def test_pico_de_audio_no_bip(video):
    picos = picos_de_audio(video, quantidade=1)
    assert picos[0]["segundo"] in (8, 9)


def test_troca_de_cena(video):
    trocas = trocas_de_cena(video)
    assert any(5.5 < t < 6.5 for t in trocas)
