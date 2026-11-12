"""Escolha sem IA (gratis): corta em volta dos maiores picos de audio.

Tambem cria os candidatos visuais (picos de movimento na tela) que vao para a 2a passada.
"""
from clipador.modelos import Corte, Pico, Segmento
from clipador.selecao.ajuste import ajustar_cortes


def candidatos_visuais(picos_vis: list[dict], existentes: list[Corte], segs: list[Segmento],
                       total: float, qtd: int, dmin: int, dmax: int) -> list[Corte]:
    """Ate `qtd` trechos de muito movimento na tela que a 1a passada (so fala) nao pegou.

    O trecho comeca um pouco antes do pico (o gancho) e e encaixado em frases como os outros.
    Nao se sobrepoe a nenhum candidato existente. Quem decide se presta e a 2a passada.
    """
    if qtd <= 0 or not picos_vis:
        return []
    alvo = (dmin + dmax) / 2

    def sobrepoe(c: Corte) -> bool:
        return any(c.inicio < e.fim and c.fim > e.inicio for e in existentes)

    brutos = [Corte(inicio=max(0.0, p["segundo"] - alvo * 0.25),
                    fim=p["segundo"] + alvo * 0.75,
                    nota=p["movimento_x_media"],
                    motivo="muito movimento na tela (sinal visual; nao passou pela triagem da fala)")
              for p in picos_vis]
    livres = [c for c in brutos if not sobrepoe(c)]
    ajustados = [c for c in ajustar_cortes(livres, segs, total, qtd * 2, dmin, dmax) if not sobrepoe(c)]
    return sorted(ajustados, key=lambda c: c.nota, reverse=True)[:qtd]


def escolher_sem_ia(picos: list[Pico], n: int, dmin: int, dmax: int) -> list[Corte]:
    alvo = (dmin + dmax) / 2
    melhores = sorted(picos, key=lambda p: p["acima_da_media_db"], reverse=True)
    return [Corte(inicio=max(0, p["segundo"] - alvo * 0.6), fim=p["segundo"] + alvo * 0.4,
                  nota=p["acima_da_media_db"], motivo="pico de audio")
            for p in melhores[: n * 2]]
