"""Picos de chat: momentos em que o chat da live explode. Opcional (--chat).

Fontes suportadas (obter_tempos_chat escolhe sozinho):
- YouTube (replay de live): baixa com o yt-dlp.
- Twitch: baixa com o TwitchDownloaderCLI, se ele estiver no PATH
  (https://github.com/lay295/TwitchDownloader). Sem ele, segue sem chat.
- Qualquer video: --chat-arquivo <arquivo> com o live_chat.json do YouTube ou o JSON do TwitchDownloader.
Chat e um sinal extra: se nao der para obter, o clipador avisa e continua sem ele.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path


def obter_tempos_chat(fonte: str, pasta: Path, arquivo: str | Path | None = None) -> list[float]:
    """Segundo (no video) de cada mensagem do chat. Lista vazia se nao der para obter."""
    try:
        if arquivo:
            return ler_chat_arquivo(Path(arquivo))
        if Path(fonte).exists():
            print("  aviso: video local; para usar o chat passe --chat-arquivo <arquivo>")
            return []
        if "twitch.tv" in fonte.lower():
            destino = baixar_chat_twitch(fonte, pasta)
            return ler_chat_twitch(destino) if destino else []
        destino = baixar_chat_youtube(fonte, pasta)
        if destino is None:
            print("  aviso: esse video nao tem replay de chat (so lives passadas tem)")
            return []
        return ler_chat_youtube(destino)
    except Exception as e:  # chat e opcional: nao derruba o resto
        print(f"  aviso: nao consegui ler o chat ({str(e)[:120]}); seguindo sem ele")
        return []


def ler_chat_arquivo(arquivo: Path) -> list[float]:
    """Detecta o formato: JSON do TwitchDownloader ({"comments": [...]}) ou live_chat.json do YouTube."""
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if isinstance(dados, dict) and "comments" in dados:
            return ler_chat_twitch(arquivo)
    except json.JSONDecodeError:
        pass  # live_chat.json do YouTube e uma linha JSON por evento
    return ler_chat_youtube(arquivo)


def baixar_chat_twitch(url: str, pasta: Path) -> Path | None:
    destino = pasta / "chat_twitch.json"
    if destino.exists():
        return destino
    m = re.search(r"twitch\.tv/videos/(\d+)", url)
    if not m:
        print("  aviso: link da Twitch sem id de VOD (twitch.tv/videos/<id>); seguindo sem chat")
        return None
    exe = shutil.which("TwitchDownloaderCLI")
    if exe is None:
        print("  aviso: TwitchDownloaderCLI nao encontrado no PATH; seguindo sem chat "
              "(ou baixe o chat e passe --chat-arquivo)")
        return None
    print("Baixando o chat da Twitch...")
    subprocess.run([exe, "chatdownload", "--id", m.group(1), "-o", str(destino)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return destino if destino.exists() else None


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
    print("Baixando o chat do YouTube...")
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
