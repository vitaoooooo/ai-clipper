"""Monta o texto de cada post e grava posts.json / posts.txt."""
import json
from pathlib import Path

from clipador.modelos import Corte
from clipador.util import fmt


def montar_post(corte: Corte, arquivo: str, credito: str = "",
                hashtags_extras: list[str] | tuple = ()) -> dict:
    legenda = corte.legenda_post
    if credito:
        legenda = f"{legenda}\n\nCredito: {credito}".strip()
    tags = list(corte.hashtags)
    vistas = {t.lower() for t in tags}
    for t in hashtags_extras:
        if t.lower() not in vistas:
            tags.append(t)
            vistas.add(t.lower())
    return {"arquivo": arquivo, **corte.para_dict(), "hashtags": tags, "legenda_post": legenda}


def salvar_posts(pasta: Path, posts: list[dict]) -> None:
    (pasta / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(pasta / "posts.txt", "w", encoding="utf-8") as f:
        for post in posts:
            f.write(f"=== {post['arquivo']}  ({fmt(post['inicio'])}-{fmt(post['fim'])}, "
                    f"nota {post.get('nota', 0):g})\n")
            f.write(f"{post['legenda_post']}\n{' '.join(post.get('hashtags', []))}\n")
            f.write(f"Motivo: {post.get('motivo', '')}\n\n")
