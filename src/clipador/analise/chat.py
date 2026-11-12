"""Picos de chat: momentos em que o chat da live explode (FASE 1 - ainda nao ligado ao pipeline).

Fontes suportadas:
- YouTube (replay de live): baixar_chat_youtube() usa o yt-dlp.
- Twitch: baixe o JSON com o TwitchDownloaderCLI
    TwitchDownloaderCLI chatdownload --id <id-do-vod> -o chat.json
  e leia com ler_chat_twitch().
"""
import json
from pathlib import Path


def baixar_chat_youtube(url: str, pasta: Path) -> Path | None:
    """Baixa o replay do chat de uma live do YouTube. Retorna None se o video nao tiver chat."""
    destino = pasta / "chat.live_chat.json"
    if destino.exists():
        return destino
    import yt_dlp

    opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "subtitleslangs": ["live_chat"],
        "outtmpl": str(pasta / "chat.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return destino if destino.exists() else None


def ler_chat_youtube(arquivo: Path) -> list[float]:
    """Segundo (no video) de cada mensagem do arquivo live_chat.json (uma linha JSON por evento)."""
    tempos = []
    with open(arquivo, encoding="utf-8") as f:
        for linha in f:
            try:
                acao = json.loads(linha).get("replayChatItemAction", {})
            except json.JSONDecodeError:
                continue
            ms = acao.get("videoOffsetTimeMsec")
            if ms is None:
                continue
            for a in acao.get("actions", []):
                if "addChatItemAction" in a:
                    tempos.append(int(ms) / 1000)
    return tempos


def ler_chat_twitch(arquivo: Path) -> list[float]:
    """Segundo de cada mensagem num JSON do TwitchDownloader."""
    dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    return [float(c["content_offset_seconds"]) for c in dados.get("comments", [])]


def picos_de_chat(tempos: list[float], quantidade: int = 20, janela: int = 5,
                  distancia_min: int = 15) -> list[dict]:
    """Janelas de `janela` segundos com mais mensagens, comparadas com a mediana do video."""
    import numpy as np

    if not tempos:
        return []
    total = int(max(tempos)) + 1
    por_segundo = np.bincount(np.array(tempos, dtype=int), minlength=total).astype(float)
    soma = np.convolve(por_segundo, np.ones(janela), mode="same")
    base = max(float(np.median(soma)), 1.0)

    picos, ocupados = [], []
    for seg in np.argsort(soma)[::-1]:
        seg = int(seg)
        if soma[seg] <= 0:
            break
        if any(abs(seg - o) < distancia_min for o in ocupados):
            continue
        ocupados.append(seg)
        picos.append({"segundo": seg, "mensagens": int(soma[seg]),
                      "vezes_a_media": round(float(soma[seg]) / base, 1)})
        if len(picos) >= quantidade:
            break
    return sorted(picos, key=lambda p: p["segundo"])
