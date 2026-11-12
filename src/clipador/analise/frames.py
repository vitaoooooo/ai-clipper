"""Prints (frames) de um trecho do video, 1 por segundo, para a IA olhar a imagem."""
from pathlib import Path

from clipador.util import rodar


def extrair_frames(video: Path, ini: float, fim: float, pasta: Path,
                   fps: float = 1.0, largura: int = 480) -> list[Path]:
    """Salva os frames de [ini, fim] em `pasta` (JPEG reduzido) e devolve a lista em ordem.

    Se a pasta ja tiver frames, reaproveita (cache). O frame i corresponde a ini + i/fps segundos.
    """
    existentes = sorted(pasta.glob("f_*.jpg"))
    if existentes:
        return existentes
    pasta.mkdir(parents=True, exist_ok=True)
    # -ss antes do -i = busca rapida; scale reduz para gastar menos tokens de imagem
    rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.2f}", "-i", str(video),
           "-t", f"{fim - ini:.2f}", "-vf", f"fps={fps},scale={largura}:-2",
           "-q:v", "5", str(pasta / "f_%04d.jpg")])
    return sorted(pasta.glob("f_*.jpg"))


def amostrar(frames: list[Path], maximo: int) -> list[tuple[int, Path]]:
    """Ate `maximo` frames espalhados por igual. Devolve (indice original, caminho)."""
    if len(frames) <= maximo:
        return list(enumerate(frames))
    passo = len(frames) / maximo
    return [(int(i * passo), frames[int(i * passo)]) for i in range(maximo)]
