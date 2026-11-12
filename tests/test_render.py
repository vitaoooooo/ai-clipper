"""Testes que rodam o ffmpeg de verdade num video sintetico (pulados se nao tiver ffmpeg)."""
import shutil

import pytest

from clipador.analise.audio import picos_de_audio
from clipador.analise.cenas import atividade_visual
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
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-g", "30",
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


def test_atividade_visual(video, tmp_path):
    """0-6s: testsrc2 (imagem animada); 6s: troca de cena; 6-12s: barras paradas."""
    cache = tmp_path / "ativ.json"
    ativ = atividade_visual(video, cache=cache)
    mov = ativ["movimento"]
    assert len(mov) == len(ativ["brilho"]) and len(mov) in (11, 12)  # so keyframes pode perder o ultimo s
    animado = sum(mov[1:6]) / 5
    parado = sum(mov[7:]) / len(mov[7:])
    assert animado > 3 * max(parado, 0.1)       # mexe mais na parte animada
    assert mov[6] == max(mov)                   # a troca de cena e o maior salto
    assert cache.exists() and atividade_visual(video, cache=cache) == ativ


def test_render_com_progresso_avisa_o_tempo(video, tmp_path):
    gerar_ass(tmp_path / "c.ass", [], 1, 5, "titulo", "@canal")
    tempos = []
    saida = renderizar(video, tmp_path, "c", 1, 5, "blur", progresso=tempos.append)
    assert dimensoes(saida) == (1080, 1920)
    assert tempos and 3.5 < max(tempos) < 4.5        # a barra chega ao fim do corte


def test_render_com_progresso_erro_do_ffmpeg(tmp_path):
    with pytest.raises(RuntimeError, match="Falhou"):
        renderizar(tmp_path / "nao_existe.mp4", tmp_path, "c", 0, 2, "blur", progresso=lambda t: None)
