"""Estruturas de dados que passam entre as etapas do pipeline."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TypedDict


# Formatos do cache transcricao.json (mantidos como dict para o cache continuar compativel)
class Palavra(TypedDict):
    start: float
    end: float
    word: str


class Segmento(TypedDict):
    start: float
    end: float
    text: str
    words: list[Palavra]


class Pico(TypedDict):
    segundo: int
    acima_da_media_db: float


@dataclass
class Video:
    caminho: Path      # arquivo .mp4
    pasta: Path        # pasta de trabalho (saida/<slug>/)
    titulo: str
    duracao: float = 0.0


@dataclass
class Corte:
    inicio: float
    fim: float
    titulo: str = ""            # texto que aparece no topo do video
    legenda_post: str = ""      # texto do post no TikTok
    hashtags: list[str] = field(default_factory=list)
    nota: float = 0.0
    motivo: str = ""
    climax: float | None = None  # segundo do momento principal (indicado pela 1a passada)
    contexto: str = ""           # o que o espectador precisa saber para entender o corte

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio

    @classmethod
    def de_dict(cls, d: dict) -> "Corte":
        return cls(
            inicio=float(d["inicio"]),
            fim=float(d["fim"]),
            titulo=d.get("titulo") or "",
            legenda_post=d.get("legenda_post") or "",
            hashtags=list(d.get("hashtags") or []),
            nota=float(d.get("nota") or 0),
            motivo=d.get("motivo") or "",
            climax=float(d["climax"]) if d.get("climax") is not None else None,
            contexto=d.get("contexto") or "",
        )

    def para_dict(self) -> dict:
        return asdict(self)
