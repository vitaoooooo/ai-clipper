"""Download via yt-dlp. Funciona com YouTube e com a maioria dos sites que o yt-dlp suporta."""
from pathlib import Path

from clipador.modelos import Video
from clipador.util import slug

FORMATO = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b"


def obter(url: str, pasta_base: Path) -> Video:
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    titulo = info.get("title") or "video"
    pasta = pasta_base / slug(titulo)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "original.mp4"
    if not caminho.exists():
        print(f"Baixando: {titulo}")
        opts = {
            "format": FORMATO,
            "merge_output_format": "mp4",
            "outtmpl": str(pasta / "original.%(ext)s"),
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    return Video(caminho=caminho, pasta=pasta, titulo=titulo)
