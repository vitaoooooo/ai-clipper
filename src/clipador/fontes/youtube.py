"""Download via yt-dlp. Funciona com YouTube e com a maioria dos sites que o yt-dlp suporta."""
from pathlib import Path

from clipador import ui
from clipador.modelos import Video
from clipador.util import slug

FORMATO = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b"


def obter(url: str, pasta_base: Path) -> Video:
    import yt_dlp

    with ui.console.status(ui.Text("  lendo o link..."), spinner="dots", spinner_style="rosa"):
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    titulo = info.get("title") or "video"
    pasta = pasta_base / slug(titulo)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "original.mp4"
    if not caminho.exists():
        with ui.barra("baixando", 1, unidade="bytes") as barra:
            def progresso(d):
                # o yt-dlp baixa video e audio separados; cada um tem o seu total
                if d.get("status") != "downloading":
                    return
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                faixa = "audio" if (d.get("info_dict") or {}).get("vcodec") == "none" else "video"
                barra.ate(d.get("downloaded_bytes") or 0, total=max(total, 1), descricao=f"  baixando {faixa}")

            opts = {
                "format": FORMATO,
                "merge_output_format": "mp4",
                "outtmpl": str(pasta / "original.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                "progress_hooks": [progresso],
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        ui.ok("download concluido")
    return Video(caminho=caminho, pasta=pasta, titulo=titulo)
