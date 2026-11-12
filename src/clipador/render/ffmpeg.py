"""Chamadas ao ffmpeg/ffprobe."""
import shutil
import sys
from pathlib import Path

from clipador.render.layouts import montar_filtro
from clipador.util import rodar


def checar_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg nao encontrado. Instale (Windows: winget install ffmpeg) e abra um terminal novo.")


def duracao(video: Path) -> float:
    out = rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(video)])
    return float(out.strip())


def renderizar(video: Path, pasta_cortes: Path, nome: str, ini: float, fim: float,
               modo: str, facecam: tuple[float, float, float, float] | None = None) -> Path:
    """Gera <pasta_cortes>/<nome>.mp4. Espera <nome>.ass ja criado na mesma pasta.

    O ffmpeg roda dentro de pasta_cortes para o caminho da legenda ser so o nome do
    arquivo (caminhos do Windows com ':' e '\\' quebram o filtro subtitles).
    """
    filtro = montar_filtro(modo, f"{nome}.ass", facecam)
    rodar(["ffmpeg", "-y", "-ss", f"{ini:.2f}", "-i", str(video), "-t", f"{fim - ini:.2f}",
           "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", f"{nome}.mp4"],
          cwd=pasta_cortes)
    return pasta_cortes / f"{nome}.mp4"
