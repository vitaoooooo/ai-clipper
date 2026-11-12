"""Chamadas ao ffmpeg/ffprobe."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

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
               modo: str, facecam: tuple[float, float, float, float] | None = None,
               progresso: Callable[[float], None] | None = None, capa: str | None = None) -> Path:
    """Gera <pasta_cortes>/<nome>.mp4. Espera <nome>.ass ja criado na mesma pasta.

    O ffmpeg roda dentro de pasta_cortes para o caminho da legenda ser so o nome do
    arquivo (caminhos do Windows com ':' e '\\' quebram o filtro subtitles).
    `progresso(segundos)` e chamado enquanto o ffmpeg avanca (para a barra do terminal).
    `capa` = nome do PNG (na pasta_cortes) com o titulo e o credito, posto por cima do video.
    """
    filtro = montar_filtro(modo, f"{nome}.ass", facecam, capa=capa is not None)
    # a capa entra logo depois do video: se viesse depois do -t, o -t valeria para ela
    entrada_capa = ["-i", capa] if capa else []
    cmd = ["ffmpeg", "-y", "-ss", f"{ini:.2f}", "-i", str(video), *entrada_capa, "-t", f"{fim - ini:.2f}",
           "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", f"{nome}.mp4"]
    if progresso is None:
        rodar(cmd, cwd=pasta_cortes)
    else:
        _rodar_com_progresso(cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]], pasta_cortes, progresso)
    return pasta_cortes / f"{nome}.mp4"


def _rodar_com_progresso(cmd: list, cwd: Path, progresso: Callable[[float], None]) -> None:
    """Como util.rodar, mas le o '-progress pipe:1' do ffmpeg (linhas out_time_us=...).

    O stderr vai para um arquivo temporario: lido por pipe junto com o stdout, ele poderia
    encher o buffer e travar o ffmpeg.
    """
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=err, text=True,
                                encoding="utf-8", errors="replace")
        for linha in proc.stdout:
            chave, _, valor = linha.strip().partition("=")
            if chave in ("out_time_us", "out_time_ms") and valor.isdigit():   # os dois vem em microssegundos
                progresso(int(valor) / 1_000_000)
        proc.wait()
        if proc.returncode != 0:
            err.seek(0)
            raise RuntimeError(f"Falhou: {' '.join(map(str, cmd))}\n{err.read()[-2000:]}")
