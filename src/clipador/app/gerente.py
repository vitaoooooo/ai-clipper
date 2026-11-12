"""Roda a fila: um video por vez, cada um num processo filho.

Processo filho (e nao thread) por dois motivos: o ui.py guarda estado global (etapas, tokens),
e "Parar" precisa matar de verdade o que estiver rodando (Whisper, ffmpeg, claude -p).
O filho manda os eventos do ui.py por uma fila do multiprocessing e, no fim, um evento "fim".
"""
import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import traceback

from clipador.app.estado import CANCELADO, Estado


def rodar_no_filho(fonte: str, cfg, fila) -> None:
    """Corpo do processo filho: roda o pipeline e manda os eventos para `fila`."""
    from clipador import pipeline, ui

    # o terminal do servidor nao e de ninguem: o rich escreve no vazio (os eventos vao pela fila)
    ui.console.file = open(os.devnull, "w", encoding="utf-8")
    ui.ouvir(fila.put)
    try:
        r = pipeline.executar(fonte, cfg)
        fila.put({"tipo": "fim", "ok": True, "titulo": r["titulo"], "pasta_cortes": str(r["pasta"]),
                  "posts": r["posts"]})
    except BaseException as e:   # inclusive KeyboardInterrupt: o servidor precisa saber que acabou
        texto = str(e).strip() or e.__class__.__name__
        fila.put({"tipo": "fim", "ok": False, "erro": texto,
                  "detalhe": "".join(traceback.format_exception(e))[-4000:]})


class Processo:
    """Um processo filho do multiprocessing que sabe morrer junto com os netos (ffmpeg, claude)."""

    def __init__(self, ctx, fonte, cfg, fila):
        self.p = ctx.Process(target=rodar_no_filho, args=(fonte, cfg, fila), daemon=True)
        self.p.start()

    def vivo(self) -> bool:
        return self.p.is_alive()

    def matar(self):
        if not self.p.is_alive():
            return
        if sys.platform == "win32":
            # /T mata a arvore inteira (ffmpeg e claude rodam como netos)
            subprocess.run(["taskkill", "/PID", str(self.p.pid), "/T", "/F"],
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            self.p.kill()

    def esperar(self, timeout: float = 5):
        self.p.join(timeout)


class Gerente:
    def __init__(self, estado: Estado, lancar=None, nova_fila=None, ao_terminar=None):
        """`lancar(fonte, cfg, fila)` devolve um objeto com vivo()/matar()/esperar() (os testes trocam)."""
        self.estado = estado
        ctx = multiprocessing.get_context("spawn")
        self._lancar = lancar or (lambda fonte, cfg, fila: Processo(ctx, fonte, cfg, fila))
        self._nova_fila = nova_fila or ctx.Queue
        self._ao_terminar = ao_terminar
        self._acordar = threading.Event()
        self._trava = threading.Lock()
        self._atual = None
        self._fim = False
        self._thread = threading.Thread(target=self._laco, daemon=True, name="gerente")
        self._thread.start()

    def enfileirar(self, fontes: list[str], cfg, canal: str = "") -> list[int]:
        ids = self.estado.adicionar(fontes, cfg, canal)
        self._acordar.set()
        return ids

    def parar(self) -> int:
        """Cancela a fila e mata o video que esta rodando. Devolve quantos itens foram cancelados."""
        n = self.estado.cancelar_pendentes()
        with self._trava:
            atual = self._atual
        if atual is not None:
            atual.matar()
        return n

    def encerrar(self):
        self._fim = True
        self.parar()
        self._acordar.set()

    # ------------------------------------------------------------ laco

    def _laco(self):
        while not self._fim:
            it = self.estado.proximo()
            if it is None:
                self._acordar.wait(1)
                self._acordar.clear()
                continue
            try:
                self._rodar(it["id"], it["fonte"])
            except Exception as e:   # o gerente nunca morre: o item falha e a fila segue
                self.estado.terminar(it["id"], False, erro=f"erro interno: {e}")

    def _rodar(self, i: int, fonte: str):
        self.estado.comecar(i)
        fila = self._nova_fila()
        processo = self._lancar(fonte, self.estado.config(i), fila)
        with self._trava:
            self._atual = processo
        fim = None
        try:
            while True:
                try:
                    ev = fila.get(timeout=0.3)
                except queue.Empty:
                    if processo.vivo():
                        continue
                    try:   # o processo acabou: ainda pode ter sobrado evento na fila
                        ev = fila.get(timeout=0.5)
                    except queue.Empty:
                        break
                if ev.get("tipo") == "fim":
                    fim = ev
                    break
                self.estado.aplicar(i, ev)
        finally:
            processo.esperar()
            with self._trava:
                self._atual = None
        item = self.estado.item(i)
        if item is None or item["status"] == CANCELADO:
            return
        if fim is None:
            self.estado.terminar(i, False, erro="o processo terminou sem avisar o resultado")
        elif fim["ok"]:
            posts = fim.get("posts") or []
            self.estado.terminar(i, True, titulo=fim.get("titulo", ""), pasta_cortes=fim.get("pasta_cortes", ""),
                                 cortes=len(posts))
            if self._ao_terminar is not None:
                try:
                    self._ao_terminar(self.estado.item(i), fim)
                except Exception:
                    pass
        else:
            self.estado.terminar(i, False, erro=fim.get("erro", "erro"))
