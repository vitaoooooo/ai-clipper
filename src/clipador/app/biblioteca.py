"""Videos ja processados (saida/<video>/cortes/posts.json) e a marcacao manual de "postado".

O historico (publicacao/historico.py, SQLite) fica em saida/clipador.db. A chave de cada corte e
o caminho absoluto do .mp4. Um video processado fora da interface (pela CLI) entra no historico
na primeira vez que um corte dele e marcado.
"""
import json
from contextlib import contextmanager
from pathlib import Path

from clipador.publicacao.historico import Historico

NOME_DB = "clipador.db"


@contextmanager
def historico(saida: Path):
    Path(saida).mkdir(parents=True, exist_ok=True)
    h = Historico(Path(saida) / NOME_DB)
    try:
        yield h
    finally:
        h.fechar()


def _titulo_da_pasta(nome: str) -> str:
    return nome.replace("-", " ").strip().capitalize() or nome


def pasta_do_video(saida: Path, nome: str) -> Path:
    """saida/<nome>, sem deixar escapar da pasta de saida (nome vem da URL)."""
    base = Path(saida).resolve()
    pasta = (base / nome).resolve()
    if pasta.parent != base:
        raise ValueError("pasta invalida")
    return pasta


def listar(saida: Path) -> list[dict]:
    saida = Path(saida)
    if not saida.is_dir():
        return []
    videos = []
    with historico(saida) as h:
        for posts_json in saida.glob("*/cortes/posts.json"):
            pasta = posts_json.parent.parent
            try:
                posts = json.loads(posts_json.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            arquivos = [str((posts_json.parent / p.get("arquivo", "")).resolve()) for p in posts]
            fonte = h.fonte_da_pasta(pasta.resolve())
            notas = [float(p.get("nota") or 0) for p in posts]
            videos.append({
                "pasta": pasta.name,
                "titulo": (fonte["titulo"] if fonte else "") or _titulo_da_pasta(pasta.name),
                "fonte": fonte["fonte"] if fonte else "",
                "cortes": len(posts),
                "postados": len(h.postados(arquivos)),
                "melhor_nota": max(notas, default=0),
                "atualizado": posts_json.stat().st_mtime,
                "primeiro": posts[0].get("arquivo") if posts else "",
            })
    videos.sort(key=lambda v: -v["atualizado"])
    return videos


def _hashtags(tags) -> list[str]:
    return [t if t.startswith("#") else f"#{t}" for t in (str(x).strip() for x in tags or []) if t]


def posts(saida: Path, nome: str) -> dict:
    pasta = pasta_do_video(saida, nome)
    cortes = pasta / "cortes"
    arq = cortes / "posts.json"
    if not arq.exists():
        raise FileNotFoundError(nome)
    lista = json.loads(arq.read_text(encoding="utf-8"))
    with historico(saida) as h:
        caminhos = [str((cortes / p.get("arquivo", "")).resolve()) for p in lista]
        marcados = h.postados(caminhos)
        fonte = h.fonte_da_pasta(pasta)
    saida_posts = []
    for p, caminho in zip(lista, caminhos):
        saida_posts.append({**p, "hashtags": _hashtags(p.get("hashtags")),
                            "duracao": float(p.get("fim", 0)) - float(p.get("inicio", 0)),
                            "existe": Path(caminho).exists(), "postado_em": marcados.get(caminho)})
    return {"pasta": pasta.name, "titulo": (fonte["titulo"] if fonte else "") or _titulo_da_pasta(pasta.name),
            "fonte": fonte["fonte"] if fonte else "", "caminho": str(cortes), "posts": saida_posts}


def marcar(saida: Path, nome: str, arquivo: str, postado: bool) -> str | None:
    """Marca/desmarca um corte como postado. Devolve a data gravada (ou None)."""
    pasta = pasta_do_video(saida, nome)
    cortes = pasta / "cortes"
    lista = json.loads((cortes / "posts.json").read_text(encoding="utf-8"))
    post = next((p for p in lista if p.get("arquivo") == arquivo), None)
    if post is None:
        raise ValueError(f"corte nao encontrado: {arquivo}")
    caminho = (cortes / arquivo).resolve()
    with historico(saida) as h:
        fonte = h.fonte_da_pasta(pasta)
        chave = fonte["fonte"] if fonte else f"pasta:{pasta.name}"
        if fonte is None:
            h.registrar_fonte(chave, _titulo_da_pasta(pasta.name), pasta)
        h.registrar_corte(chave, caminho, post)
        if postado:
            h.marcar_postado(caminho)
        else:
            h.desmarcar_postado(caminho)
        return h.postados([caminho]).get(str(caminho))


def registrar_video(saida: Path, fonte: str, titulo: str, pasta_cortes: Path, posts_: list[dict]):
    """Chamado quando a interface termina um video: guarda a fonte e os cortes no historico."""
    pasta_cortes = Path(pasta_cortes).resolve()
    with historico(saida) as h:
        h.registrar_fonte(fonte, titulo, pasta_cortes.parent)
        for p in posts_:
            h.registrar_corte(fonte, pasta_cortes / p["arquivo"], p)
