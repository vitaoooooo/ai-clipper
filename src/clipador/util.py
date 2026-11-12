"""Utilidades gerais: rodar comandos, formatar tempo, nomes de pasta."""
import re
import subprocess


def rodar(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"Falhou: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout


def fmt(seg):
    """Segundos -> 'mm:ss' ou 'h:mm:ss'."""
    m, s = divmod(int(seg), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def slug(texto):
    texto = re.sub(r"[^\w\s-]", "", texto, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", texto)[:60] or "video"
