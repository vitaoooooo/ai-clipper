"""Historico em SQLite (FASE 2 - ainda nao ligado ao pipeline).

Guarda quais videos ja foram processados, quais cortes foram gerados e quais ja foram
postados, para nao repetir trabalho nem postar o mesmo corte duas vezes.
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

    def pendentes(self) -> list[sqlite3.Row]:
        """Cortes gerados e ainda nao postados, melhores notas primeiro."""
        return self.db.execute(
            "SELECT * FROM cortes WHERE postado_em IS NULL ORDER BY nota DESC, criado_em").fetchall()
