"""Encaixa inicio/fim dos cortes em frases inteiras, respeita duracoes e remove sobreposicao."""
import re
from dataclasses import replace

from clipador.modelos import Corte, Segmento

FOLGA_INI = 0.2   # segundos antes do inicio da frase
FOLGA_FIM = 0.4   # segundos depois do fim da frase
FOLGA_PALAVRA = 0.1


def _primeiro_fim_de_frase(segs: list[Segmento], a: float, b: float) -> float | None:
    """Primeiro fim de frase (com folga) entre a e b. Usado para esticar ate a duracao minima."""
    fins = [s["end"] + FOLGA_FIM for s in segs if a <= s["end"] + FOLGA_FIM <= b]
    return min(fins) if fins else None


def _ultimo_fim_natural(segs: list[Segmento], a: float, b: float) -> float | None:
    """Ultimo ponto bom para terminar entre a e b, para encurtar ate a duracao maxima.

    Preferencia: fim de frase > palavra com pontuacao > fim de qualquer palavra.
    """
    fins = [s["end"] + FOLGA_FIM for s in segs if a <= s["end"] + FOLGA_FIM <= b]
    if fins:
        return max(fins)
    palavras = [w for s in segs for w in s["words"] if a <= w["end"] + FOLGA_PALAVRA <= b]
    pontuadas = [w["end"] + FOLGA_PALAVRA for w in palavras if re.search(r"[.!?,]$", w["word"])]
    if pontuadas:
        return max(pontuadas)
    if palavras:
        return max(w["end"] + FOLGA_PALAVRA for w in palavras)
    return None


def ajustar_cortes(cortes: list[Corte], segs: list[Segmento], total: float,
                   n: int, dmin: int, dmax: int) -> list[Corte]:
    inicios = [s["start"] for s in segs]
    fins = [s["end"] for s in segs]
    prontos: list[Corte] = []
    for c in sorted(cortes, key=lambda c: c.nota, reverse=True):
        ini, fim = c.inicio, c.fim
        if segs:
            antes = [x for x in inicios if x <= ini + 0.5]
            ini = max(antes) if antes else ini
            depois = [x for x in fins if x >= fim - 0.5]
            fim = min(depois) if depois else fim
        ini, fim = max(0.0, ini - FOLGA_INI), min(total, fim + FOLGA_FIM)
        if fim - ini < dmin:
            # estica ate o primeiro fim de frase depois da duracao minima
            fim = min(total, _primeiro_fim_de_frase(segs, ini + dmin, ini + dmax) or ini + dmin)
        if fim - ini > dmax:
            # recua ate o ultimo fim de frase (ou de palavra) antes da duracao maxima
            fim = min(total, _ultimo_fim_natural(segs, ini + dmin, ini + dmax) or ini + dmax)
        if fim - ini < 5:
            continue
        if any(ini < p.fim and fim > p.inicio for p in prontos):
            continue
        prontos.append(replace(c, inicio=round(ini, 2), fim=round(fim, 2)))
        if len(prontos) >= n:
            break
    return sorted(prontos, key=lambda c: c.inicio)
