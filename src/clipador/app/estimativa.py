"""Quantas chamadas ao Claude uma execucao faz (para o usuario controlar a cota do plano).

Mesma conta do pipeline:
- 1a passada: um pedido por bloco de ~1h (ia.dividir_em_blocos; ate ~1h15 e um bloco so)
- 2a passada: um pedido por candidato (max(candidatos, cortes) da fala + ate candidatos_visuais)
Sem IA ou com --reprisar-ia: zero chamadas de verdade.
"""
from clipador.config import Config
from clipador.selecao.ia import BLOCO_SEG, SOBREPOSICAO_SEG


def blocos(duracao: float | None) -> int:
    if not duracao:
        return 1
    n, ini = 0, 0.0
    while True:
        n += 1
        fim = ini + BLOCO_SEG
        if duracao - fim < BLOCO_SEG * 0.25:
            return n
        ini = fim - SOBREPOSICAO_SEG


def chamadas(cfg: Config, duracao: float | None) -> dict:
    """{"primeira", "segunda", "total"} de um video. `segunda` e o maximo (candidatos visuais podem faltar)."""
    if cfg.sem_ia or cfg.reprisar_ia:
        return {"primeira": 0, "segunda": 0, "total": 0}
    primeira = blocos(duracao)
    segunda = 0
    if cfg.visao:
        segunda = max(cfg.candidatos, cfg.cortes) + (cfg.candidatos_visuais if cfg.cenas else 0)
    return {"primeira": primeira, "segunda": segunda, "total": primeira + segunda}


def estimar(cfg: Config, duracoes: list[float | None]) -> dict:
    por_video = [chamadas(cfg, d) for d in duracoes]
    return {"total": sum(v["total"] for v in por_video), "por_video": por_video,
            "aproximado": any(d is None for d in duracoes),
            "duracao_total": sum(d for d in duracoes if d),
            "reprise": bool(cfg.reprisar_ia and not cfg.sem_ia)}
