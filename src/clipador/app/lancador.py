"""Comando `clipador-ui`: garante o servidor rodando em segundo plano e abre a janela.

- O servidor e um processo separado (sem console): fechar a janela nao para os cortes.
  Abrir de novo so reconecta e mostra o estado atual.
- `clipador-ui --parar` desliga o servidor (e o que estiver rodando).
- Janela: pywebview (WebView2 do Windows). Sem ele, abre o Edge em modo app; por ultimo, o navegador.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from clipador.app.servidor import PORTA_PADRAO

ICONE = Path(__file__).parent / "static" / "icone.ico"
LOG = Path(tempfile.gettempdir()) / "clipador-ui.log"


def _url(porta: int) -> str:
    return f"http://127.0.0.1:{porta}"


def saude(porta: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(_url(porta) + "/api/saude", timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
            return dados if dados.get("app") == "clipador" else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def desligar(porta: int) -> bool:
    req = urllib.request.Request(_url(porta) + "/api/desligar", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except (urllib.error.URLError, OSError):
        return False
    for _ in range(50):
        if saude(porta, 0.3) is None:
            return True
        time.sleep(0.1)
    return False


def subir_servidor(porta: int, raiz: Path) -> dict:
    """Sobe o servidor como processo independente (sobrevive a janela e ao terminal)."""
    cmd = [sys.executable, "-m", "clipador.app.servidor", "--porta", str(porta), "--raiz", str(raiz)]
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    log = open(LOG, "a", encoding="utf-8")
    log.write(f"\n=== {time.strftime('%d/%m/%Y %H:%M:%S')} {' '.join(cmd)}\n")
    log.flush()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # cwd fora do projeto: com `-m`, a pasta atual entra no sys.path e o clipador.py da raiz
    # "esconderia" o pacote clipador. O servidor entra sozinho na `--raiz` (os.chdir) ao comecar.
    subprocess.Popen(cmd, cwd=tempfile.gettempdir(), stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env,
                     creationflags=flags, close_fds=True, start_new_session=sys.platform != "win32")
    for _ in range(150):   # ate ~30 s (o primeiro import do pacote demora)
        info = saude(porta, 0.5)
        if info:
            return info
        time.sleep(0.2)
    raise SystemExit(f"o servidor nao respondeu em {_url(porta)}. Veja o log: {LOG}")


def abrir_janela(url: str, modo: str) -> str:
    """Abre a interface. Devolve como abriu: janela | edge | navegador."""
    if modo == "janela":
        try:
            import webview
            webview.create_window("Clipador", url, width=1440, height=900, min_size=(1100, 700),
                                  background_color="#0B0B0F")
            webview.start(icon=str(ICONE) if ICONE.exists() else None)
            return "janela"
        except Exception as e:   # sem pywebview/WebView2: cai para o Edge em modo app
            print(f"pywebview indisponivel ({e}); abrindo no navegador")
    if modo in ("janela", "edge"):
        edge = shutil.which("msedge") or next(
            (str(p) for p in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
                              Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe")
             if p.exists()), None)
        if edge:
            subprocess.Popen([edge, f"--app={url}", "--window-size=1440,900"])
            return "edge"
    webbrowser.open(url)
    return "navegador"


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipador-ui", description="Interface grafica do Clipador.")
    p.add_argument("--porta", type=int, default=PORTA_PADRAO)
    p.add_argument("--parar", action="store_true", help="Desliga o servidor (para o que estiver rodando)")
    p.add_argument("--navegador", action="store_true", help="Abre no navegador padrao em vez da janela")
    p.add_argument("--sem-janela", action="store_true", help="So sobe o servidor e mostra o endereco")
    a = p.parse_args(argv)
    url = _url(a.porta)

    if a.parar:
        if saude(a.porta) is None:
            print("o servidor do Clipador nao esta rodando")
            return
        print("servidor desligado" if desligar(a.porta) else "nao consegui desligar o servidor")
        return

    raiz = Path.cwd().resolve()
    info = saude(a.porta)
    if info is None:
        print(f"subindo o servidor em {url} ...")
        info = subir_servidor(a.porta, raiz)
    elif Path(info.get("raiz", "")).resolve() != raiz:
        print(f"aviso: o servidor ja rodando usa a pasta {info['raiz']} (config.toml e saida/ de la). "
              f"Para trocar: clipador-ui --parar e abra de novo nesta pasta.")
    print(f"Clipador em {url}  (fechar a janela nao para os cortes; para desligar: clipador-ui --parar)")
    if a.sem_janela:
        return
    abrir_janela(url, "navegador" if a.navegador else "janela")


if __name__ == "__main__":
    main()
