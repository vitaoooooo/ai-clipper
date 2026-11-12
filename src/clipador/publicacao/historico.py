"""Historico em SQLite: videos processados, cortes gerados e quais ja foram postados.

Usado pela interface grafica (clipador.app): ela registra os cortes de cada video e o usuario marca
a mao o que ja postou (a postagem no TikTok e manual). A CLI ainda nao grava aqui.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS fontes (
    fonte         TEXT PRIMARY KEY,
    titulo        TEXT,
    pasta         TEXT,
    processado_em TEXT
);
CREATE TABLE IF NOT EXISTS cortes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte      TEXT REFERENCES fontes(fonte),
    arquivo    TEXT UNIQUE,
    inicio     REAL,
    fim        REAL,
    titulo     TEXT,
    nota       REAL,
    criado_em  TEXT,
    postado_em TEXT,
    link_post  TEXT
);
"""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Historico:
    def __init__(self, caminho: Path | str = "clipador.db"):
        self.db = sqlite3.connect(str(caminho))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA)

    def fechar(self):
        self.db.close()

    def ja_processada(self, fonte: str) -> bool:
        return self.db.execute("SELECT 1 FROM fontes WHERE fonte = ?", (fonte,)).fetchone() is not None

    def registrar_fonte(self, fonte: str, titulo: str, pasta: Path) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO fontes VALUES (?, ?, ?, ?)",
                            (fonte, titulo, str(pasta), _agora()))

    def registrar_corte(self, fonte: str, arquivo: Path, post: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO cortes (fonte, arquivo, inicio, fim, titulo, nota, criado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fonte, str(arquivo), post["inicio"], post["fim"], post.get("titulo", ""),
                 post.get("nota", 0), _agora()))

    def marcar_postado(self, arquivo: Path, link: str = "") -> None:
        with self.db:
            self.db.execute("UPDATE cortes SET postado_em = ?, link_post = ? WHERE arquivo = ?",
                            (_agora(), link, str(arquivo)))

    def desmarcar_postado(self, arquivo: Path) -> None:
        with self.db:
            self.db.execute("UPDATE cortes SET postado_em = NULL, link_post = NULL WHERE arquivo = ?",
                            (str(arquivo),))

    def postados(self, arquivos: list) -> dict[str, str]:
        """{arquivo: postado_em} dos arquivos ja marcados como postados."""
        nomes = [str(a) for a in arquivos]
        if not nomes:
            return {}
        marcas = ",".join("?" * len(nomes))
        linhas = self.db.execute(f"SELECT arquivo, postado_em FROM cortes WHERE postado_em IS NOT NULL "
                                 f"AND arquivo IN ({marcas})", nomes).fetchall()
        return {l["arquivo"]: l["postado_em"] for l in linhas}

    def fonte_da_pasta(self, pasta: Path) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM fontes WHERE pasta = ?", (str(pasta),)).fetchone()

    def pendentes(self) -> list[sqlite3.Row]:
        """Cortes gerados e ainda nao postados, melhores notas primeiro."""
        return self.db.execute(
            "SELECT * FROM cortes WHERE postado_em IS NULL ORDER BY nota DESC, criado_em").fetchall()
