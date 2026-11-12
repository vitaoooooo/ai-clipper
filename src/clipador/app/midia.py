"""Dados de uma fonte (titulo, canal, duracao) e um print dela para marcar a regiao da facecam.

Link: o yt-dlp le os dados sem baixar o video; o print sai direto do stream (o ffmpeg busca o
segundo pedido sem baixar o resto). Arquivo local: ffprobe/ffmpeg no proprio arquivo.
"""
import hashlib
import threading
from pathlib import Path

from clipador.fontes import twitch
from clipador.util import rodar, slug

_cache: dict[str, dict] = {}
_trava = threading.Lock()


def plataforma(fonte: str) -> str | None:
    if Path(fonte).exists():
        return None
    if twitch.eh_twitch(fonte):
        return "twitch"
    if "youtu" in fonte.lower():
        return "youtube"
    return "link"


def info(fonte: str) -> dict:
    """{"fonte", "titulo", "canal", "duracao", "plataforma", "local", "erro"}. Fica em cache."""
    with _trava:
        if fonte in _cache:
            return _cache[fonte]
    dados = {"fonte": fonte, "titulo": "", "canal": "", "duracao": None, "plataforma": plataforma(fonte),
             "local": Path(fonte).exists(), "erro": ""}
    try:
        if dados["local"]:
            from clipador.render.ffmpeg import duracao
            dados["titulo"] = Path(fonte).stem
            dados["duracao"] = duracao(Path(fonte))
        else:
            meta = _extrair(fonte)
            dados["titulo"] = meta.get("title") or ""
            dados["canal"] = meta.get("uploader_id") or meta.get("uploader") or meta.get("channel") or ""
            dados["duracao"] = meta.get("duration")
    except Exception as e:
        dados["erro"] = str(e).strip().splitlines()[0][:200] if str(e).strip() else "erro ao ler"
    if not dados["erro"]:   # erro nao fica em cache: o usuario pode corrigir o link e tentar de novo
        with _trava:
            _cache[fonte] = dados
    return dados


def _extrair(url: str, formato: str | None = None) -> dict:
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if formato:
        opts["format"] = formato
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def entrada_video(fonte: str, pasta_saida: Path) -> str:
    """Caminho (ou URL) que o ffmpeg abre para tirar um print."""
    if Path(fonte).exists():
        return str(Path(fonte).resolve())
    titulo = info(fonte).get("titulo")
    if titulo:   # o video ja foi baixado numa execucao anterior?
        baixado = Path(pasta_saida) / slug(titulo) / "original.mp4"
        if baixado.exists():
            return str(baixado)
    meta = _extrair(fonte, "b[height<=720]/b")
    url = meta.get("url") or next((f.get("url") for f in meta.get("requested_formats") or [] if f.get("url")), None)
    if not url:
        raise RuntimeError("nao consegui o endereco do video para tirar o print")
    return url


def tirar_print(fonte: str, segundo: float, pasta_cache: Path, pasta_saida: Path) -> Path:
    """JPEG de 960px de largura no `segundo` pedido. Fica em cache em `pasta_cache`."""
    chave = hashlib.sha1(f"{fonte}|{int(segundo)}".encode("utf-8")).hexdigest()[:16]
    destino = Path(pasta_cache) / f"print_{chave}.jpg"
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(segundo, 0):.2f}", "-i", entrada_video(fonte, pasta_saida),
           "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "3", str(destino)])
    if not destino.exists():
        raise RuntimeError("o ffmpeg nao gerou o print (o segundo pedido passa do fim do video?)")
    return destino
