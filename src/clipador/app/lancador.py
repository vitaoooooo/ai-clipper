"""Comando `clipador-ui`: garante o servidor rodando em segundo plano e abre a janela.

- O servidor e um processo separado (sem console). Fechar a janela pelo X pergunta antes e, se o
  usuario confirmar, desliga o servidor e o que estiver rodando (avisa o que esta em andamento).
  Isso vale para a janela do pywebview; no Edge/navegador nao da para interceptar o X.
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
import threading
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
        # CREATE_NO_WINDOW da ao servidor um console OCULTO, herdado pelos filhos (o python real do
        # .venv, os workers, ffmpeg e claude). Nao use DETACHED_PROCESS: sem console, o python.exe do
        # .venv (um redirecionador) abre o python de verdade num console NOVO e visivel, e fechar essa
        # janela mata o servidor ("forrtl: program aborting due to window-CLOSE event").
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
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


def estado_atual(porta: int) -> dict | None:
    try:
        with urllib.request.urlopen(_url(porta) + "/api/estado", timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def mensagem_fechar(foto: dict | None) -> tuple[str, bool]:
    """Texto da confirmacao ao fechar pelo X e se ha algo em andamento."""
    itens = (foto or {}).get("itens", [])
    rodando = [it for it in itens if it.get("status") == "rodando"]
    na_fila = [it for it in itens if it.get("status") == "fila"]
    if not rodando and not na_fila:
        return "Fechar o Clipador?", False
    linhas = ["Ainda tem coisa em andamento:", ""]
    for it in rodando:
        nome = it.get("titulo") or it.get("fonte", "")
        etapa = next((e["titulo"] for e in reversed(it.get("etapas", [])) if e.get("status") == "rodando"), "")
        linhas.append(f"- {nome}" + (f" ({etapa.lower()})" if etapa else ""))
    if na_fila:
        linhas.append(f"- {len(na_fila)} video(s) esperando na fila")
    linhas += ["", "Se fechar, tudo isso para agora (o que ja foi transcrito fica salvo",
               "e e reaproveitado na proxima vez).", "", "Fechar mesmo assim?"]
    return "\n".join(linhas), True


def _perguntar(texto: str, aviso: bool, dono: int = 0) -> bool:
    """Caixa nativa do Windows: so o plano B quando a pagina nao responde."""
    if sys.platform != "win32":
        return True
    import ctypes
    MB_YESNO, MB_ICONQUESTION, MB_ICONWARNING, MB_DEFBUTTON2, MB_TOPMOST, IDYES = 0x4, 0x20, 0x30, 0x100, 0x40000, 6
    flags = MB_YESNO | MB_TOPMOST | (MB_ICONWARNING | MB_DEFBUTTON2 if aviso else MB_ICONQUESTION)
    return ctypes.windll.user32.MessageBoxW(dono, texto, "Clipador", flags) == IDYES


class ApiJanela:
    """Exposta ao JS como `window.pywebview.api`. Atributos com `_` nao sao expostos."""

    def __init__(self, porta: int):
        self._porta = porta
        self._janela = None
        self._liberado = False   # True depois de confirmar: o proximo `closing` passa direto

    def fechar(self):
        """Chamado pelo dialogo da pagina depois que o usuario confirma: desliga tudo e fecha."""
        if saude(self._porta, 0.5) is not None:
            desligar(self._porta)
        self._liberado = True
        if self._janela is not None:
            threading.Thread(target=self._janela.destroy, daemon=True).start()


def _ao_fechar(janela, api: ApiJanela) -> bool:
    """Evento `closing` do pywebview (roda na thread da interface): False cancela o fechamento.

    A confirmacao e o dialogo da propria pagina (`clipadorPedirFechar` no app.js), no visual do app.
    O evaluate_js espera a pagina, entao vai numa thread (na thread da interface travaria).
    Se a pagina nao responder (nao carregou, servidor fora), cai na caixa nativa do Windows.
    """
    if api._liberado:
        return True

    def pedir():
        try:
            ok = janela.evaluate_js("window.clipadorPedirFechar ? window.clipadorPedirFechar() : false")
        except Exception:
            ok = False
        if ok is True:
            return
        texto, aviso = mensagem_fechar(estado_atual(api._porta))
        if _perguntar(texto, aviso):
            api.fechar()

    threading.Thread(target=pedir, daemon=True).start()
    return False


def _identidade_windows():
    """Faz a barra de tarefas tratar a janela como "Clipador" (icone proprio), nao como python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Clipador.Interface")
    except (OSError, AttributeError):
        pass


def abrir_janela(url: str, modo: str, porta: int = PORTA_PADRAO) -> str:
    """Abre a interface. Devolve como abriu: janela | edge | navegador."""
    if modo == "janela":
        try:
            import webview
            _identidade_windows()
            api = ApiJanela(porta)
            janela = webview.create_window("Clipador", url, js_api=api, width=1440, height=900,
                                           min_size=(1100, 700), background_color="#0B0B0F")
            api._janela = janela
            janela.events.closing += lambda: _ao_fechar(janela, api)
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
    print(f"Clipador em {url}  (fechar a janela pelo X desliga tudo; ou: clipador-ui --parar)")
    if a.sem_janela:
        return
    abrir_janela(url, "navegador" if a.navegador else "janela", a.porta)


if __name__ == "__main__":
    main()
