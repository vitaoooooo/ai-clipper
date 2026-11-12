"""Video que ja esta no computador (ex: arquivo que o criador mandou)."""
from pathlib import Path

from clipador.modelos import Video
from clipador.util import slug


def obter(caminho: str, pasta_base: Path) -> Video:
    video = Path(caminho).resolve()
    pasta = pasta_base / slug(video.stem)
    pasta.mkdir(parents=True, exist_ok=True)
    return Video(caminho=video, pasta=pasta, titulo=video.stem)
