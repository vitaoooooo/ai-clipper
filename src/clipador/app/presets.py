"""Presets de canal no config.toml, editados pela interface.

O config.toml e do usuario e tem comentarios: a escrita usa o tomlkit, que mexe so nas chaves
alteradas e preserva o resto do arquivo (comentarios, ordem, espacos). A leitura usa a mesma
regra do clipador.config (padrao < [padrao] < [canais.X]).
"""
import re
import shutil
from dataclasses import asdict, fields
from pathlib import Path

import tomlkit

from clipador import config
from clipador.config import Config

NOME_CONFIG = "config.toml"
NOME_EXEMPLO = "config.example.toml"
NOME_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

# o que a interface pode gravar num preset (o resto do config.toml fica como esta)
CAMPOS = ("credito", "plataforma", "cortes", "dmin", "dmax", "modo", "facecam", "whisper", "idioma",
          "modelo", "sem_ia", "visao", "candidatos", "cenas", "candidatos_visuais", "chat",
          "hashtags_extras")


def caminho(raiz: Path) -> Path:
    return Path(raiz) / NOME_CONFIG


def garantir(raiz: Path) -> Path:
    """Cria o config.toml a partir do config.example.toml (ou vazio) se ele ainda nao existir."""
    arq = caminho(raiz)
    if not arq.exists():
        exemplo = Path(raiz) / NOME_EXEMPLO
        if exemplo.exists():
            shutil.copyfile(exemplo, arq)
        else:
            arq.write_text("# Config do Clipador (criada pela interface)\n\n[padrao]\n", encoding="utf-8")
    return arq


def ler(raiz: Path) -> dict:
    """{"existe", "padrao": {...}, "canais": {nome: {...}}, "campos_padrao": Config() como dict}."""
    arq = caminho(raiz)
    dados = {"existe": arq.exists(), "padrao": {}, "canais": {},
             "campos_padrao": _serializavel(asdict(Config()))}
    if arq.exists():
        doc = tomlkit.parse(arq.read_text(encoding="utf-8")).unwrap()
        dados["padrao"] = doc.get("padrao", {}) or {}
        dados["canais"] = doc.get("canais", {}) or {}
    return dados


def resolver(raiz: Path, canal: str | None = None, sobrescritas: dict | None = None) -> Config:
    """Config final (mesma regra da CLI). Erro de validacao vira ValueError."""
    arq = caminho(raiz)
    sobrescritas = {k: v for k, v in (sobrescritas or {}).items() if v is not None}
    if "facecam" in sobrescritas and isinstance(sobrescritas["facecam"], (list, tuple)):
        sobrescritas["facecam"] = tuple(float(x) for x in sobrescritas["facecam"])
    return config.carregar(arq if arq.exists() else None, canal or None, sobrescritas)


def salvar_canal(raiz: Path, nome: str, valores: dict) -> dict:
    """Cria ou atualiza [canais.<nome>] com `valores` (None apaga a chave). Devolve o preset gravado."""
    if not NOME_VALIDO.match(nome or ""):
        raise ValueError("nome de canal invalido: use letras, numeros, - ou _ (sem espacos)")
    desconhecidos = set(valores) - set(CAMPOS)
    if desconhecidos:
        raise ValueError(f"opcoes desconhecidas: {', '.join(sorted(desconhecidos))}")
    valores = {k: _normalizar(k, v) for k, v in valores.items()}

    arq = garantir(raiz)
    doc = tomlkit.parse(arq.read_text(encoding="utf-8"))
    atual = dict((doc.get("canais", {}) or {}).get(nome, {}) or {})
    final = {**atual, **{k: v for k, v in valores.items() if v is not None}}
    for k, v in valores.items():
        if v is None:
            final.pop(k, None)
    # valida antes de gravar: o preset precisa gerar uma Config valida junto com o [padrao]
    padrao = dict(doc.get("padrao", {}) or {})
    _validar({**padrao, **final})

    if "canais" not in doc:
        doc.add(tomlkit.nl())
        doc["canais"] = tomlkit.table(is_super_table=True)
    canais = doc["canais"]
    if nome not in canais:
        canais[nome] = tomlkit.table()
    tabela = canais[nome]
    for k, v in valores.items():
        if v is None:
            if k in tabela:
                del tabela[k]
        else:
            tabela[k] = _item_toml(k, v)
    arq.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return final


def apagar_canal(raiz: Path, nome: str) -> None:
    arq = caminho(raiz)
    if not arq.exists():
        raise ValueError("nao ha config.toml")
    doc = tomlkit.parse(arq.read_text(encoding="utf-8"))
    canais = doc.get("canais")
    if canais is None or nome not in canais:
        raise ValueError(f"canal '{nome}' nao existe")
    del canais[nome]
    arq.write_text(tomlkit.dumps(doc), encoding="utf-8")


# ------------------------------------------------------------ apoio

def _normalizar(k: str, v):
    if v is None:
        return None
    if k == "facecam":
        if isinstance(v, str):
            v = config.parse_facecam(v)
        return [round(float(x), 4) for x in v]
    if k == "hashtags_extras":
        if isinstance(v, str):
            v = v.split()
        return [str(t).strip() for t in v if str(t).strip()]
    return v


def _item_toml(k: str, v):
    if isinstance(v, list):
        arr = tomlkit.array()
        arr.extend(v)
        return arr
    return v


def _validar(dados: dict):
    validos = {f.name for f in fields(Config)}
    dados = {k: v for k, v in dados.items() if k in validos}
    if isinstance(dados.get("facecam"), list):
        dados["facecam"] = tuple(dados["facecam"])
    Config(**dados).validar()


def _serializavel(d: dict) -> dict:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}
