"""Reprise da IA (--reprisar-ia): reusa as respostas salvas da ultima execucao, sem chamar o Claude.

Serve para testar o resto do pipeline (visual do terminal, ajuste, legendas, render) sem gastar cota.
As respostas vem de `resposta_ia.json` (1a passada) e `resposta_visao.json` (2a passada), na pasta
do video. O uso de tokens mostrado e o daquela execucao.

1a passada: a resposta de cada bloco e achada pela parte ("parte 2 de 3") ou, com um bloco so, e a unica.
2a passada: cada candidato pega a resposta salva com maior sobreposicao de tempo. Nao exige o mesmo
inicio exato, porque mudancas no ajuste.py podem mexer um pouco nos limites dos candidatos.
"""
import json
import re
import threading
import time
from pathlib import Path

PAUSA_SEG = 0.6   # cada "chamada" espera um pouco, para as barras de progresso andarem como de verdade


class Reprise:
    def __init__(self, pasta: Path, com_visao: bool):
        arq_ia = pasta / "resposta_ia.json"
        if not arq_ia.exists():
            raise RuntimeError(f"--reprisar-ia: nao achei {arq_ia}. Rode uma vez com a IA antes.")
        self.blocos = json.loads(arq_ia.read_text(encoding="utf-8"))["blocos"]
        self.candidatos = []
        if com_visao:
            arq_visao = pasta / "resposta_visao.json"
            if not arq_visao.exists():
                raise RuntimeError(f"--reprisar-ia: nao achei {arq_visao}. Rode uma vez com a IA antes "
                                   "ou use --sem-visao.")
            self.candidatos = [c for c in json.loads(arq_visao.read_text(encoding="utf-8"))["candidatos"]
                               if c.get("resposta") is not None]
        self._trava = threading.Lock()
        self._usados: set[int] = set()

    def responder(self, conteudo: list, schema: dict) -> tuple[dict, dict]:
        time.sleep(PAUSA_SEG)
        texto = conteudo[0]["text"]
        if "Trecho sugerido:" in texto:
            return self._visao(texto)
        return self._primeira(texto)

    def _primeira(self, texto: str) -> tuple[dict, dict]:
        m = re.search(r"parte (\d+) de (\d+)", texto)
        i, qtd = (int(m.group(1)), int(m.group(2))) if m else (1, 1)
        if qtd != len(self.blocos):
            raise RuntimeError(f"--reprisar-ia: a execucao salva tem {len(self.blocos)} bloco(s) e esta "
                               f"tem {qtd}. Rode sem --reprisar-ia.")
        b = self.blocos[i - 1]
        return b["resposta"], {"modelo": b.get("modelo", "reprise"), "uso": b.get("uso", {"entrada": 0, "saida": 0})}

    def _visao(self, texto: str) -> tuple[dict, dict]:
        m = re.search(r"Trecho sugerido: ([\d.]+)s a ([\d.]+)s", texto)
        ini, fim = float(m.group(1)), float(m.group(2))
        with self._trava:   # a 2a passada roda em paralelo; cada resposta salva e usada uma vez so
            livres = [(k, c) for k, c in enumerate(self.candidatos) if k not in self._usados]
            sobreposicao = lambda c: min(fim, c["fim_1a_passada"]) - max(ini, c["inicio_1a_passada"])
            k, melhor = max(livres, key=lambda kc: sobreposicao(kc[1]), default=(None, None))
            if melhor is None or sobreposicao(melhor) <= 0:
                raise RuntimeError(f"--reprisar-ia: nenhuma resposta salva para o candidato {ini:.0f}-{fim:.0f}s")
            self._usados.add(k)
        uso = melhor.get("uso") or {"entrada": 0, "saida": 0}
        return melhor["resposta"], {"modelo": "reprise", "uso": uso}
