"""Credito do criador: plataforma (Twitch/YouTube) + usuario, para a pilula no video e o texto do post.

De onde vem cada parte (a primeira que existir):
- plataforma: --plataforma / `plataforma` da config > o link do video (twitch.tv, youtube.com, youtu.be).
- usuario: --credito / `credito` da config ("@mount" ou "mount") > o canal que o yt-dlp informa no link.
Arquivo local sem --plataforma fica sem icone, so com "@usuario".
Um --credito com espaco ("Clip do Gaules") nao e um usuario: vira o texto inteiro, sem icone.
"""
import re

from clipador.modelos import Credito, Video

PLATAFORMAS = ("twitch", "youtube")


def plataforma_do_link(fonte: str) -> str | None:
    f = fonte.lower()
    if "twitch.tv" in f:
        return "twitch"
    if "youtube.com" in f or "youtu.be" in f:
        return "youtube"
    return None


def texto_do_credito(plataforma: str | None, usuario: str) -> str:
    if plataforma == "twitch":
        return f"twitch.tv/{usuario}"
    if plataforma == "youtube":
        return f"youtube.com/@{usuario}"
    return f"@{usuario}"


def resolver(credito: str, plataforma: str, fonte: str, video: Video) -> Credito | None:
    """Monta o credito a partir da config/CLI e dos dados do video. None se nao houver o que mostrar."""
    plat = plataforma or video.plataforma or plataforma_do_link(fonte)
    credito = (credito or "").strip()
    if credito and not re.fullmatch(r"@?[\w.\-]+", credito):
        return Credito(None, "", credito)            # texto livre: mostra como veio
    usuario = credito.lstrip("@") or (video.usuario or "").lstrip("@")
    if not usuario:
        return None
    return Credito(plat, usuario, texto_do_credito(plat, usuario))
