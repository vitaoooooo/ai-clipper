"""Transcricao com Whisper (faster-whisper). Usa a GPU se der, senao a CPU. Resultado fica em cache."""
import json
from pathlib import Path

from clipador.modelos import Segmento
from clipador.util import fmt


def transcrever(video: Path, pasta: Path, modelo: str, idioma: str) -> list[Segmento]:
    cache = pasta / "transcricao.json"
    if cache.exists():
        print("Usando transcricao salva.")
        return json.loads(cache.read_text(encoding="utf-8"))

    from faster_whisper import WhisperModel

    def _executar(device, compute):
        m = WhisperModel(modelo, device=device, compute_type=compute)
        segs, _ = m.transcribe(str(video), language=idioma or None,
                               word_timestamps=True, vad_filter=True)
        saida = []
        for s in segs:
            saida.append({
                "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                "words": [{"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip()}
                          for w in (s.words or [])],
            })
            print(f"\r  transcrito ate {fmt(s.end)}", end="", flush=True)
        print()
        return saida

    print(f"Transcrevendo com Whisper ({modelo})...")
    try:
        resultado = _executar("cuda", "float16")
    except Exception as e:
        print(f"  GPU indisponivel ({str(e)[:80]}), usando CPU (mais lento)...")
        resultado = _executar("cpu", "int8")
    cache.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return resultado
