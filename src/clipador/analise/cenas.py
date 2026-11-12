"""Trocas bruscas de imagem (FASE 1 - ainda nao ligado ao pipeline).

Serve para achar acao sem fala (perseguicao, explosao, morte, corte de camera).
Usa o filtro de deteccao de cena do ffmpeg num video reduzido, entao e rapido.
"""
import re
import subprocess
from pathlib import Path


def trocas_de_cena(video: Path, limiar: float = 0.4) -> list[float]:
    """Segundos em que a imagem muda mais que `limiar` (0 a 1) de um quadro para o outro."""
    filtro = f"scale=320:-2,select='gt(scene,{limiar})',showinfo"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", filtro,
                        "-an", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def picos_de_cena(trocas: list[float], quantidade: int = 20, janela: int = 10,
                  distancia_min: int = 15) -> list[dict]:
    """Janelas de `janela` segundos com mais trocas de cena (muita acao)."""
    if not trocas:
        return []
    candidatos = []
    for t in trocas:
        n = sum(1 for o in trocas if t <= o < t + janela)
        candidatos.append((n, int(t)))
    picos, ocupados = [], []
    for n, seg in sorted(candidatos, reverse=True):
        if any(abs(seg - o) < distancia_min for o in ocupados):
            continue
        ocupados.append(seg)
        picos.append({"segundo": seg, "trocas_de_cena": n})
        if len(picos) >= quantidade:
            break
    return sorted(picos, key=lambda p: p["segundo"])
