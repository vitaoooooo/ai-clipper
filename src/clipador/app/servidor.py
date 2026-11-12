"""Servidor local da interface (Starlette). So escuta em 127.0.0.1.

Uso direto (normalmente quem chama e o `clipador-ui`):
    python -m clipador.app.servidor --porta 8765 --raiz <pasta do projeto>

O progresso vai por SSE (/api/eventos): uma "foto" do estado inteiro sempre que ele muda.
Fechar a janela nao para nada; o servidor so para com /api/desligar (`clipador-ui --parar`).
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from clipador import __version__
from clipador.app import biblioteca, estimativa, midia, presets
from clipador.app.estado import Estado
from clipador.app.gerente import Gerente

ESTATICOS = Path(__file__).parent / "static"
PORTA_PADRAO = 8765
OPCOES = set(presets.CAMPOS) | {"reprisar_ia"}


def _erro(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"erro": msg}, status_code=status)


def _gpu() -> bool | None:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return None


def criar_app(raiz: Path, gerente: Gerente | None = None) -> Starlette:
    raiz = Path(raiz).resolve()
    estado = gerente.estado if gerente is not None else Estado()

    def pasta_saida(cfg=None) -> Path:
        if cfg is None:
            try:
                cfg = presets.resolver(raiz)
            except Exception:
                return raiz / "saida"
        p = Path(cfg.saida)
        return p if p.is_absolute() else raiz / p

    def ao_terminar(item: dict, fim: dict):
        cfg = estado.config(item["id"])
        biblioteca.registrar_video(pasta_saida(cfg), item["fonte"], fim.get("titulo", ""),
                                   Path(fim["pasta_cortes"]), fim.get("posts") or [])

    if gerente is None:
        gerente = Gerente(estado, ao_terminar=ao_terminar)
    else:
        gerente._ao_terminar = gerente._ao_terminar or ao_terminar

    pasta_prints = Path(tempfile.gettempdir()) / "clipador-ui"
    info_maquina: dict = {}

    async def corpo(request: Request) -> dict:
        try:
            dados = await request.json()
        except ValueError:
            return {}
        return dados if isinstance(dados, dict) else {}

    def _sobrescritas(opcoes: dict) -> dict:
        desconhecidas = set(opcoes) - OPCOES
        if desconhecidas:
            raise ValueError(f"opcoes desconhecidas: {', '.join(sorted(desconhecidas))}")
        return opcoes

    # ------------------------------------------------------------ paginas e estado

    async def inicio(request):
        return FileResponse(ESTATICOS / "index.html", headers={"Cache-Control": "no-store"})

    async def saude(request):
        return JSONResponse({"ok": True, "app": "clipador", "versao": __version__, "pid": os.getpid(),
                             "raiz": str(raiz)})

    async def ver_estado(request):
        return JSONResponse(estado.foto())

    async def eventos(request):
        async def fluxo():
            ultima, parado = -1, 0
            while True:
                if await request.is_disconnected():
                    break
                if estado.versao != ultima:
                    foto = estado.foto()
                    ultima = foto["versao"]
                    parado = 0
                    yield f"data: {json.dumps(foto, ensure_ascii=False)}\n\n"
                else:
                    parado += 1
                    if parado >= 60:   # ~15 s sem nada: um comentario mantem a conexao viva
                        parado = 0
                        yield ": oi\n\n"
                await asyncio.sleep(0.25)
        return StreamingResponse(fluxo(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------ config e presets

    def ver_config(request):
        canal = request.query_params.get("canal") or None
        try:
            cfg = presets.resolver(raiz, canal)
            erro = ""
        except (ValueError, OSError) as e:
            cfg, erro = None, str(e)
        if "gpu" not in info_maquina:
            info_maquina["gpu"] = _gpu()
            info_maquina["claude"] = shutil.which("claude") is not None
        return JSONResponse({"presets": presets.ler(raiz), "resolvido": presets._serializavel(asdict(cfg)) if cfg else None,
                             "erro": erro, "maquina": info_maquina, "saida": str(pasta_saida(cfg))})

    async def salvar_canal(request):
        dados = await corpo(request)
        try:
            preset = presets.salvar_canal(raiz, request.path_params["nome"], dados.get("valores") or {})
        except (ValueError, OSError) as e:
            return _erro(str(e))
        return JSONResponse({"ok": True, "preset": preset})

    async def apagar_canal(request):
        try:
            presets.apagar_canal(raiz, request.path_params["nome"])
        except (ValueError, OSError) as e:
            return _erro(str(e))
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------ fontes, prints e estimativa

    async def ver_info(request):
        fonte = ((await corpo(request)).get("fonte") or "").strip()
        if not fonte:
            return _erro("fonte vazia")
        return JSONResponse(await asyncio.to_thread(midia.info, fonte))

    def ver_print(request):
        fonte = request.query_params.get("fonte", "")
        try:
            segundo = float(request.query_params.get("t", "60"))
        except ValueError:
            return _erro("t invalido")
        try:
            jpg = midia.tirar_print(fonte, segundo, pasta_prints, pasta_saida())
        except Exception as e:
            return _erro(str(e).strip().splitlines()[-1][:300] if str(e).strip() else "falhou", 500)
        return FileResponse(jpg, media_type="image/jpeg")

    async def ver_estimativa(request):
        dados = await corpo(request)
        try:
            cfg = presets.resolver(raiz, dados.get("canal"), _sobrescritas(dados.get("opcoes") or {}))
        except (ValueError, OSError) as e:
            return _erro(str(e))
        duracoes = [(midia._cache.get(f) or {}).get("duracao") for f in dados.get("fontes") or []]
        return JSONResponse(estimativa.estimar(cfg, duracoes))

    def escolher_arquivos(request):
        """Abre a janela de "abrir arquivo" do Windows (o navegador nao entrega o caminho do arquivo)."""
        try:
            import tkinter
            from tkinter import filedialog
            janela = tkinter.Tk()
            janela.withdraw()
            janela.attributes("-topmost", True)
            caminhos = filedialog.askopenfilenames(
                parent=janela, title="Escolha os videos",
                filetypes=[("Videos", "*.mp4 *.mkv *.mov *.webm *.ts *.flv"), ("Todos", "*.*")])
            janela.destroy()
        except Exception as e:
            return _erro(f"nao consegui abrir a janela de arquivos: {e}", 500)
        return JSONResponse({"arquivos": [str(Path(c)) for c in caminhos]})

    # ------------------------------------------------------------ execucao

    async def executar(request):
        dados = await corpo(request)
        fontes = list(dict.fromkeys(f.strip() for f in dados.get("fontes") or [] if f and f.strip()))
        if not fontes:
            return _erro("cole pelo menos um link ou escolha um arquivo")
        try:
            cfg = presets.resolver(raiz, dados.get("canal"), _sobrescritas(dados.get("opcoes") or {}))
        except (ValueError, OSError) as e:
            return _erro(str(e))
        cfg.saida = str(pasta_saida(cfg))   # o processo filho nao depende do diretorio atual
        ids = gerente.enfileirar(fontes, cfg, dados.get("canal") or "")
        return JSONResponse({"ok": True, "ids": ids})

    async def parar(request):
        return JSONResponse({"ok": True, "cancelados": gerente.parar()})

    async def limpar(request):
        estado.remover_terminados()
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------ biblioteca

    def ver_videos(request):
        return JSONResponse({"videos": biblioteca.listar(pasta_saida())})

    def ver_video(request):
        try:
            return JSONResponse(biblioteca.posts(pasta_saida(), request.path_params["pasta"]))
        except (FileNotFoundError, ValueError):
            return _erro("video nao encontrado", 404)

    async def postado(request):
        dados = await corpo(request)
        try:
            quando = biblioteca.marcar(pasta_saida(), request.path_params["pasta"], dados.get("arquivo", ""),
                                       bool(dados.get("postado")))
        except (FileNotFoundError, ValueError) as e:
            return _erro(str(e), 404)
        return JSONResponse({"ok": True, "postado_em": quando})

    async def abrir(request):
        dados = await corpo(request)
        try:
            pasta = biblioteca.pasta_do_video(pasta_saida(), request.path_params["pasta"]) / "cortes"
        except ValueError as e:
            return _erro(str(e))
        alvo = pasta / Path(dados.get("arquivo") or "").name if dados.get("arquivo") else pasta
        if not alvo.exists():
            return _erro("nao encontrado", 404)
        if sys.platform == "win32":
            if alvo.is_file():
                subprocess.Popen(["explorer", "/select,", str(alvo)])
            else:
                os.startfile(alvo)
        return JSONResponse({"ok": True})

    def ver_midia(request):
        try:
            pasta = biblioteca.pasta_do_video(pasta_saida(), request.path_params["pasta"]) / "cortes"
        except ValueError:
            return Response(status_code=404)
        arq = (pasta / request.path_params["arquivo"]).resolve()
        if arq.parent != pasta.resolve() or not arq.is_file():
            return Response(status_code=404)
        return FileResponse(arq)   # o FileResponse responde Range: o <video> consegue pular no tempo

    # ------------------------------------------------------------ desligar

    async def desligar(request):
        gerente.encerrar()
        servidor = getattr(app.state, "servidor", None)
        if servidor is not None:
            threading.Timer(0.3, lambda: setattr(servidor, "should_exit", True)).start()
        return JSONResponse({"ok": True})

    rotas = [
        Route("/", inicio),
        Route("/api/saude", saude),
        Route("/api/estado", ver_estado),
        Route("/api/eventos", eventos),
        Route("/api/config", ver_config),
        Route("/api/canais/{nome}", salvar_canal, methods=["PUT"]),
        Route("/api/canais/{nome}", apagar_canal, methods=["DELETE"]),
        Route("/api/info", ver_info, methods=["POST"]),
        Route("/api/print", ver_print),
        Route("/api/estimativa", ver_estimativa, methods=["POST"]),
        Route("/api/escolher-arquivos", escolher_arquivos, methods=["POST"]),
        Route("/api/executar", executar, methods=["POST"]),
        Route("/api/parar", parar, methods=["POST"]),
        Route("/api/limpar", limpar, methods=["POST"]),
        Route("/api/videos", ver_videos),
        Route("/api/videos/{pasta}", ver_video),
        Route("/api/videos/{pasta}/postado", postado, methods=["POST"]),
        Route("/api/videos/{pasta}/abrir", abrir, methods=["POST"]),
        Route("/midia/{pasta}/{arquivo}", ver_midia),
        Route("/api/desligar", desligar, methods=["POST"]),
        Mount("/static", StaticFiles(directory=ESTATICOS), name="static"),
    ]
    app = Starlette(routes=rotas)
    app.state.gerente = gerente
    app.state.estado = estado
    return app


def main(argv=None):
    import uvicorn

    p = argparse.ArgumentParser(prog="clipador-servidor")
    p.add_argument("--porta", type=int, default=PORTA_PADRAO)
    p.add_argument("--raiz", type=Path, default=Path.cwd(), help="Pasta com o config.toml e a saida/")
    a = p.parse_args(argv)
    os.chdir(a.raiz)
    app = criar_app(a.raiz)
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=a.porta, log_level="warning",
                                             access_log=False))
    app.state.servidor = servidor
    servidor.run()


if __name__ == "__main__":
    main()
