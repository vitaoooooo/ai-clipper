"""Picos de volume (gritos, explosoes, risadas): segundos bem mais altos que a mediana do video."""
import json
import subprocess
from pathlib import Path

from clipador.modelos import Pico


def picos_de_audio(video: Path, quantidade: int = 20, cache: Path | None = None) -> list[Pico]:
    if cache is not None and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    import numpy as np

    sr = 8000
    bruto = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", str(sr),
                            "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(bruto, dtype=np.int16).astype(np.float32)
    n = len(a) // sr
    if n == 0:
        return []
    rms = np.sqrt((a[: n * sr].reshape(n, sr) ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms / 32768)
    base = float(np.median(db))
    picos, ocupados = [], set()
    for seg in np.argsort(db)[::-1]:
        seg = int(seg)
        if any(abs(seg - o) < 15 for o in ocupados):
            continue
        ocupados.add(seg)
        picos.append({"segundo": seg, "acima_da_media_db": round(float(db[seg]) - base, 1)})
        if len(picos) >= quantidade:
            break
    picos = sorted(picos, key=lambda p: p["segundo"])
    if cache is not None:
        cache.write_text(json.dumps(picos), encoding="utf-8")
    return picos
