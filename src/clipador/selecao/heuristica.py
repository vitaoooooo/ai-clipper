"""Escolha sem IA (gratis): corta em volta dos maiores picos de audio."""
from clipador.modelos import Corte, Pico


def escolher_sem_ia(picos: list[Pico], n: int, dmin: int, dmax: int) -> list[Corte]:
    alvo = (dmin + dmax) / 2
    melhores = sorted(picos, key=lambda p: p["acima_da_media_db"], reverse=True)
    return [Corte(inicio=max(0, p["segundo"] - alvo * 0.6), fim=p["segundo"] + alvo * 0.4,
                  nota=p["acima_da_media_db"], motivo="pico de audio")
            for p in melhores[: n * 2]]
