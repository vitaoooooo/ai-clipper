"""Encaixa inicio/fim dos cortes em frases inteiras, respeita duracoes e remove sobreposicao."""
from dataclasses import replace

from clipador.modelos import Corte, Segmento


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
        ini, fim = max(0.0, ini - 0.2), min(total, fim + 0.4)
        if fim - ini < dmin:
            fim = min(total, ini + dmin)
        if fim - ini > dmax:
            # TODO fase 1: recuar ate o fim de frase anterior em vez de cortar no meio da fala
            fim = ini + dmax
        if fim - ini < 5:
            continue
        if any(ini < p.fim and fim > p.inicio for p in prontos):
            continue
        prontos.append(replace(c, inicio=round(ini, 2), fim=round(fim, 2)))
        if len(prontos) >= n:
            break
    return sorted(prontos, key=lambda c: c.inicio)
