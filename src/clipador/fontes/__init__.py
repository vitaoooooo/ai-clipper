"""De onde vem o video: arquivo local, YouTube (ou qualquer site do yt-dlp), Twitch."""
from pathlib import Path

from clipador.fontes import local, twitch, youtube
from clipador.modelos import Video


def obter_video(fonte: str, pasta_base: Path) -> Video:
    if Path(fonte).exists():
        return local.obter(fonte, pasta_base)
    if twitch.eh_twitch(fonte):
        return twitch.obter(fonte, pasta_base)
    return youtube.obter(fonte, pasta_base)
