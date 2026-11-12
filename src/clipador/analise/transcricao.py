"""Transcricao com Whisper (faster-whisper). Usa a GPU se der, senao a CPU. Resultado fica em cache."""
import json
import os
import subprocess
import sys
from pathlib import Path

from clipador.modelos import Segmento
from clipador.util import fmt


TAXA = 16000  # o Whisper trabalha com audio mono em 16 kHz


def carregar_audio(video: Path):
    """Audio do video em float32 mono 16 kHz, decodificado pelo ffmpeg.

    O faster-whisper decodificaria com o PyAV, mas o PyAV 19+ quebrou a chamada que ele usa
    (`metadata_errors`). Com o ffmpeg (que o projeto ja exige) nao dependemos disso.
    Memoria: ~230 MB por hora de video.
    """
    import numpy as np

    bruto = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
                            "-ar", str(TAXA), "-f", "s16le", "-"], capture_output=True)
    if bruto.returncode != 0 or not bruto.stdout:
        raise RuntimeError(f"Nao consegui extrair o audio: {bruto.stderr.decode(errors='replace')[-500:]}")
    return np.frombuffer(bruto.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _registrar_dlls_cuda() -> None:
    """No Windows, deixa o ctranslate2 achar as DLLs do CUDA instaladas via pip.

    Pacotes nvidia-cublas-cu12 / nvidia-cudnn-cu12 poem as DLLs em site-packages/nvidia/*/bin,
    que nao esta no caminho de busca do Windows. Sem eles, o Whisper cai para a CPU.
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for pasta_bin in Path(base).glob("*/bin"):
            os.add_dll_directory(str(pasta_bin))
            os.environ["PATH"] = str(pasta_bin) + os.pathsep + os.environ.get("PATH", "")


def transcrever(video: Path, pasta: Path, modelo: str, idioma: str) -> list[Segmento]:
    cache = pasta / "transcricao.json"
    if cache.exists():
        print("Usando transcricao salva.")
        return json.loads(cache.read_text(encoding="utf-8"))

    _registrar_dlls_cuda()
    from faster_whisper import WhisperModel

    audio = carregar_audio(video)

    def _executar(device, compute):
        m = WhisperModel(modelo, device=device, compute_type=compute)
        segs, _ = m.transcribe(audio, language=idioma or None,
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
