"""Varios videos de uma vez: links na linha de comando e/ou um arquivo de lista (--lista).

Os videos rodam um depois do outro, com a mesma config. Um video que falhar (link quebrado,
limite do plano, etc.) nao para os outros: o erro aparece e o lote segue. No fim, um resumo
com o resultado de cada video. Rodar o mesmo lote de novo reaproveita o cache de cada video
(download, transcricao, sinais), entao da para refazer so o que falhou.
"""
import time
from pathlib import Path

from clipador import pipeline, ui
from clipador.config import Config


def ler_lista(arquivo: str | Path) -> list[str]:
    """Um link (ou caminho de arquivo) por linha. Linhas vazias e comecando com # sao ignoradas."""
    fontes = []
    for linha in Path(arquivo).read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            fontes.append(linha)
    return fontes


def juntar_fontes(fontes: list[str], lista: str | Path | None = None) -> list[str]:
    """Links da linha de comando + os da lista, sem repetir e na ordem em que apareceram."""
    todas = list(fontes) + (ler_lista(lista) if lista else [])
    return list(dict.fromkeys(todas))


def executar_lote(fontes: list[str], cfg: Config) -> list[dict]:
    """Roda o pipeline em cada fonte. Devolve um resultado por video (ok, cortes, pasta ou erro)."""
    resultados = []
    for i, fonte in enumerate(fontes, 1):
        if len(fontes) > 1:
            ui.cabecalho_video(i, len(fontes), fonte)
        t0 = time.monotonic()
        try:
            r = pipeline.executar(fonte, cfg)
            resultados.append({"fonte": fonte, "ok": True, "titulo": r["titulo"], "cortes": len(r["posts"]),
                               "pasta": str(r["pasta"])})
        except Exception as e:   # um video com problema nao para o lote (Ctrl+C nao e Exception: para tudo)
            if len(fontes) == 1:
                raise
            ui.erro(f"video {i}/{len(fontes)} falhou", f"{fonte}\n\n{e}")
            resultados.append({"fonte": fonte, "ok": False, "erro": str(e).strip().splitlines()[0][:150]})
        resultados[-1].update(tempo=time.monotonic() - t0, chamadas=ui.uso.chamadas,
                              entrada=ui.uso.entrada, saida=ui.uso.saida)
    if len(fontes) > 1:
        ui.resumo_lote(resultados)
    return resultados
