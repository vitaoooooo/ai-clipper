"""Encaixa inicio/fim dos cortes na fala, respeita duracoes e remove sobreposicao.

Regra: so mexe num limite que cai DENTRO de uma fala (para nao comecar nem terminar no meio dela).
Limite em silencio fica onde esta: pode ter sido escolhido olhando a imagem (2a passada), por
exemplo o fim de uma briga sem fala. E idempotente: ajustar duas vezes da o mesmo resultado
(o pipeline ajusta depois da 1a e depois da 2a passada).
"""
import re
from dataclasses import replace

from clipador.modelos import Corte, Segmento

FOLGA_INI = 0.2   # segundos antes do inicio da frase
FOLGA_FIM = 0.4   # segundos depois do fim da frase
FOLGA_PALAVRA = 0.1
TOLERANCIA = 0.5  # limite a ate 0.5s de uma fala conta como "encostado" nela
EPS = 1e-6        # folga de arredondamento (os limites saem com 2 casas)


def encaixar_inicio(t: float, segs: list[Segmento]) -> float:
    """Se t cai dentro de uma fala (ou ate 0.5s antes dela), volta para o comeco da fala."""
    for s in segs:
        # max(...): numa fala curtissima (< 0.5s) a janela ainda cobre o proprio inicio ajustado
        if s["start"] - TOLERANCIA <= t < max(s["end"] - TOLERANCIA, s["start"]):
            return max(0.0, s["start"] - FOLGA_INI)
    return t


def encaixar_fim(t: float, segs: list[Segmento]) -> float:
    """Se t cai dentro de uma fala (ou ate 0.5s depois dela), vai ate o fim da fala."""
    for s in segs:
        # min(...): numa fala curtissima a janela ainda cobre o proprio fim ajustado
        if min(s["start"] + TOLERANCIA, s["end"]) < t <= s["end"] + TOLERANCIA:
            return s["end"] + FOLGA_FIM
    return t


def _primeiro_fim_de_frase(segs: list[Segmento], a: float, b: float) -> float | None:
    """Primeiro fim de frase (com folga) entre a e b. Usado para esticar ate a duracao minima."""
    fins = [s["end"] + FOLGA_FIM for s in segs if a - EPS <= s["end"] + FOLGA_FIM <= b + EPS]
    return min(fins) if fins else None


def _ultimo_fim_natural(segs: list[Segmento], a: float, b: float) -> float | None:
    """Ultimo ponto bom para terminar entre a e b, para encurtar ate a duracao maxima.

    Preferencia: fim de frase > palavra com pontuacao > fim de qualquer palavra.
    """
    fins = [s["end"] + FOLGA_FIM for s in segs if a - EPS <= s["end"] + FOLGA_FIM <= b + EPS]
    if fins:
        return max(fins)
    palavras = [w for s in segs for w in s["words"] if a - EPS <= w["end"] + FOLGA_PALAVRA <= b + EPS]
    pontuadas = [w["end"] + FOLGA_PALAVRA for w in palavras if re.search(r"[.!?,]$", w["word"])]
    if pontuadas:
        return max(pontuadas)
    if palavras:
        return max(w["end"] + FOLGA_PALAVRA for w in palavras)
    return None


def ajustar_cortes(cortes: list[Corte], segs: list[Segmento], total: float,
                   n: int, dmin: int, dmax: int) -> list[Corte]:
    prontos: list[Corte] = []
    for c in sorted(cortes, key=lambda c: c.nota, reverse=True):
        # arredonda ANTES de decidir: a saida tem 2 casas e a 2a rodada tem que ver o mesmo numero
        ini = round(encaixar_inicio(round(max(0.0, c.inicio), 2), segs), 2)
        fim = min(total, encaixar_fim(round(c.fim, 2), segs))
        if fim - ini < dmin:
            # estica ate o primeiro fim de frase depois da duracao minima
            primeiro = _primeiro_fim_de_frase(segs, ini + dmin, ini + dmax)
            # sem fim de frase na janela: encaixa na fala; se passar do maximo, o bloco abaixo recua
            fim = min(total, primeiro if primeiro is not None else encaixar_fim(ini + dmin, segs))
        if fim - ini > dmax:
            alvo = ini + dmax
            encaixado = encaixar_fim(alvo, segs)   # mesma regra de "dentro da fala" do resto
            if encaixado <= alvo + EPS:
                fim = encaixado  # o maximo cai em silencio (ou logo depois de um fim de frase)
            else:
                # cairia no meio de uma fala: recua ate o ultimo fim de frase (ou de palavra)
                fim = _ultimo_fim_natural(segs, ini + dmin, alvo) or alvo
            fim = min(total, fim)
        if fim - ini < 5:
            continue
        if any(ini < p.fim and fim > p.inicio for p in prontos):
            continue
        prontos.append(replace(c, inicio=round(ini, 2), fim=round(fim, 2)))
        if len(prontos) >= n:
            break
    return sorted(prontos, key=lambda c: c.inicio)
