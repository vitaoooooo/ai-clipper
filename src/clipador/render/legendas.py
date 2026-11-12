"""Legendas animadas no formato ASS (2-3 palavras por vez, em caixa alta, com destaque amarelo)."""
import re
from pathlib import Path

from clipador.modelos import Palavra, Segmento
from clipador.render.layouts import ALTURA, LARGURA


def tempo_ass(t: float) -> str:
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def limpar_ass(texto: str) -> str:
    return texto.replace("{", "(").replace("}", ")").replace("\\", "").replace("\n", " ")


def blocos_de_palavras(segs: list[Segmento], ini: float, fim: float,
                       max_palavras: int = 3) -> list[list[Palavra]]:
    palavras: list[Palavra] = []
    for s in segs:
        if s["end"] < ini or s["start"] > fim:
            continue
        if s["words"]:
            palavras += [w for w in s["words"] if w["start"] >= ini - 0.1 and w["end"] <= fim + 0.1]
        elif s["text"]:
            palavras.append({"start": s["start"], "end": s["end"], "word": s["text"]})
    blocos, atual = [], []
    for w in palavras:
        atual.append(w)
        if len(atual) >= max_palavras or re.search(r"[.!?,]$", w["word"]):
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    return blocos


CABECALHO = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGURA}
PlayResY: {ALTURA}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,560,1
Style: Destaque,Arial,84,&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,560,1
Style: Titulo,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,14,0,8,80,80,260,1
Style: Credito,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,8,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def gerar_ass(caminho: Path, segs: list[Segmento], ini: float, fim: float,
              titulo: str, credito: str) -> None:
    dur = fim - ini
    linhas = []
    if credito:
        linhas.append(f"Dialogue: 1,{tempo_ass(0)},{tempo_ass(dur)},Credito,,0,0,0,,{limpar_ass(credito)}")
    if titulo:
        linhas.append(f"Dialogue: 1,{tempo_ass(0)},{tempo_ass(min(dur, 4))},Titulo,,0,0,0,,"
                      f"{limpar_ass(titulo.upper())}")
    blocos = blocos_de_palavras(segs, ini, fim)
    for i, b in enumerate(blocos):
        a = b[0]["start"] - ini
        z = b[-1]["end"] - ini
        if i + 1 < len(blocos):
            prox = blocos[i + 1][0]["start"] - ini
            if prox - z < 0.4:
                z = prox
        texto = limpar_ass(" ".join(w["word"] for w in b).upper())
        estilo = "Destaque" if i % 4 == 3 else "Legenda"
        linhas.append(f"Dialogue: 0,{tempo_ass(a)},{tempo_ass(z)},{estilo},,0,0,0,,{texto}")
    caminho.write_text(CABECALHO + "\n".join(linhas) + "\n", encoding="utf-8")
