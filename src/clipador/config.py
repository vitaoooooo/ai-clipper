"""Configuracao: valores padrao < config.toml [padrao] < [canais.X] < linha de comando."""
from dataclasses import dataclass, field, fields
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

MODOS = ("blur", "crop", "facecam")
CONFIG_PADRAO = Path("config.toml")


@dataclass
class Config:
    credito: str = ""
    cortes: int = 5
    dmin: int = 20
    dmax: int = 60
    modo: str = "blur"
    facecam: tuple[float, float, float, float] | None = None  # x, y, largura, altura (0 a 1)
    whisper: str = "medium"
    idioma: str = "pt"
    modelo: str = "claude-sonnet-5-5"
    sem_ia: bool = False
    visao: bool = True       # 2a passada: IA ve os prints dos candidatos
    candidatos: int = 12     # quantos a 1a passada (so transcricao) pre-seleciona
    saida: str = "saida"
    hashtags_extras: list[str] = field(default_factory=list)

    def validar(self):
        if self.cortes < 1:
            raise ValueError("cortes precisa ser pelo menos 1")
        if self.candidatos < 1:
            raise ValueError("candidatos precisa ser pelo menos 1")
        if self.dmin < 1 or self.dmax < self.dmin:
            raise ValueError(f"duracoes invalidas: min={self.dmin} max={self.dmax}")
        if self.modo not in MODOS:
            raise ValueError(f"modo '{self.modo}' invalido, use: {', '.join(MODOS)}")
        if self.modo == "facecam" and self.facecam is None:
            raise ValueError("modo facecam precisa da regiao da facecam (--facecam x,y,largura,altura)")
        if self.facecam is not None:
            x, y, w, h = self.facecam
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1
                    and x + w <= 1.0001 and y + h <= 1.0001):
                raise ValueError(f"regiao da facecam fora do video: {self.facecam}")


def parse_facecam(texto: str) -> tuple[float, float, float, float]:
    partes = [p.strip() for p in str(texto).split(",")]
    if len(partes) != 4:
        raise ValueError("facecam deve ter 4 numeros: x,y,largura,altura (ex: 0,0,0.25,0.3)")
    x, y, w, h = (float(p) for p in partes)
    return x, y, w, h


def carregar(arquivo: Path | None = None, canal: str | None = None,
             sobrescritas: dict | None = None) -> Config:
    """Monta a Config. Se `arquivo` for None e existir ./config.toml, ele e usado."""
    if arquivo is None and CONFIG_PADRAO.exists():
        arquivo = CONFIG_PADRAO

    dados: dict = {}
    if arquivo is not None:
        bruto = tomllib.loads(Path(arquivo).read_text(encoding="utf-8"))
        dados.update(bruto.get("padrao", {}))
        if canal:
            canais = bruto.get("canais", {})
            if canal not in canais:
                raise ValueError(f"canal '{canal}' nao existe em {arquivo} "
                                 f"(disponiveis: {', '.join(canais) or 'nenhum'})")
            dados.update(canais[canal])
    elif canal:
        raise ValueError("--canal precisa de um arquivo de config (--config ou ./config.toml)")

    dados.update({k: v for k, v in (sobrescritas or {}).items() if v is not None})

    validos = {f.name for f in fields(Config)}
    desconhecidos = set(dados) - validos
    if desconhecidos:
        raise ValueError(f"opcoes desconhecidas na config: {', '.join(sorted(desconhecidos))}")

    if dados.get("facecam") is not None and not isinstance(dados["facecam"], tuple):
        fc = dados["facecam"]
        dados["facecam"] = parse_facecam(",".join(map(str, fc)) if isinstance(fc, list) else fc)

    cfg = Config(**dados)
    cfg.validar()
    return cfg
