"""Atividade visual: quanto a imagem muda a cada segundo (sinal de acao sem fala).

Por que importa: a 1a passada escolhe candidatos so pela fala, entao acao sem fala
(perseguicao, explosao, tiroteio) nunca vira candidato e a 2a passada (que olha as imagens)
nunca a ve. Os picos visuais daqui viram candidatos extras para a 2a passada e tambem
entram como sinal no prompt da 1a.

Como mede: o ffmpeg decodifica so os keyframes (rapido mesmo em lives de 8h), reduz cada
quadro para 64x36 em cinza e o numpy compara um segundo com o anterior.
Limites: muito movimento nem sempre e bom (troca de cena da live, menu, mapa). Por isso
os picos visuais passam pela 2a passada, onde a IA olha as imagens e descarta o que nao presta.
"""
import json
import subprocess
from pathlib import Path

LARG, ALT = 64, 36
BRILHO_TELA_PRETA = 16   # media de luminancia (0-255) abaixo disso = tela preta/loading
MOVIMENTO_MINIMO = 0.5   # movimento medio por segundo abaixo disso = tela praticamente parada


def atividade_visual(video: Path, cache: Path | None = None, so_keyframes: bool = True) -> dict:
    """{"movimento": [...], "brilho": [...]}, um valor por segundo de video.

    movimento = diferenca media (0-255) entre o quadro do segundo e o do segundo anterior.
    Com so_keyframes, segundos sem keyframe repetem o quadro anterior (movimento 0); a soma
    em janelas de varios segundos (picos_visuais) compensa isso.
    """
    if cache is not None and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    import numpy as np

    cmd = ["ffmpeg", "-v", "error"]
    if so_keyframes:
        cmd += ["-skip_frame", "nokey"]
    cmd += ["-i", str(video), "-an", "-vf", f"fps=1,scale={LARG}:{ALT},format=gray",
            "-f", "rawvideo", "-"]
    bruto = subprocess.run(cmd, capture_output=True).stdout
    n = len(bruto) // (LARG * ALT)
    if n == 0:
        resultado = {"movimento": [], "brilho": []}
    else:
        q = np.frombuffer(bruto[: n * LARG * ALT], dtype=np.uint8).reshape(n, ALT, LARG).astype(np.float32)
        mov = np.zeros(n, dtype=np.float32)
        mov[1:] = np.abs(q[1:] - q[:-1]).mean(axis=(1, 2))
        resultado = {"movimento": [round(float(x), 2) for x in mov],
                     "brilho": [round(float(x), 1) for x in q.mean(axis=(1, 2))]}

    if cache is not None:
        cache.write_text(json.dumps(resultado), encoding="utf-8")
    return resultado


def picos_visuais(ativ: dict, quantidade: int = 20, janela: int = 10, distancia_min: int = 30,
                  minimo_x_media: float = 1.5) -> list[dict]:
    """Janelas de `janela` segundos com muito mais movimento que a mediana do video.

    Segundos de tela preta/loading nao contam. Devolve
    [{"segundo": inicio_da_janela, "movimento_x_media": 2.3}, ...] em ordem de tempo.
    """
    import numpy as np

    mov = np.array(ativ.get("movimento", []), dtype=np.float32)
    if len(mov) < janela:
        return []
    brilho = np.array(ativ.get("brilho", []), dtype=np.float32)
    if len(brilho) == len(mov):
        mov = np.where(brilho < BRILHO_TELA_PRETA, 0, mov)
        # a primeira imagem depois de uma tela preta nao e "acao"
        mov[1:] = np.where(brilho[:-1] < BRILHO_TELA_PRETA, 0, mov[1:])

    soma = np.convolve(mov, np.ones(janela), mode="valid")   # soma[i] = segundos i..i+janela-1
    # piso de 0.5 por segundo: em video quase parado a mediana ~0 faria ruido virar "pico de 1000x"
    base = max(float(np.median(soma)), MOVIMENTO_MINIMO * janela)

    picos, ocupados = [], []
    for seg in np.argsort(soma)[::-1]:
        seg = int(seg)
        vezes = float(soma[seg]) / base
        if vezes < minimo_x_media:
            break
        if any(abs(seg - o) < distancia_min for o in ocupados):
            continue
        ocupados.append(seg)
        picos.append({"segundo": seg, "movimento_x_media": round(vezes, 1)})
        if len(picos) >= quantidade:
            break
    return sorted(picos, key=lambda p: p["segundo"])
