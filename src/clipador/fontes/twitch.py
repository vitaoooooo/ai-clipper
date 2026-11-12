"""VODs da Twitch.

O yt-dlp ja baixa VODs da Twitch, entao o download reaproveita fontes/youtube.py.
O chat da Twitch NAO vem pelo yt-dlp: baixe com o TwitchDownloaderCLI
(https://github.com/lay295/TwitchDownloader) e leia com analise/chat.py (fase 1).
"""
from pathlib import Path

from clipador.fontes import youtube
from clipador.modelos import Video


def eh_twitch(url: str) -> bool:
    return "twitch.tv" in url.lower()


def obter(url: str, pasta_base: Path) -> Video:
    return youtube.obter(url, pasta_base)
