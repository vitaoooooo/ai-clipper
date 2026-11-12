"""Estado da fila e do progresso, montado a partir dos eventos que o ui.py emite.

Tudo aqui e thread-safe e serializavel em JSON (o servidor manda `foto()` pelo SSE).
Cada video da fila e um "item". O processo filho que roda o pipeline manda os eventos
(dicts) e o gerente chama `aplicar(id, evento)`.
"""
import threading
import time
from dataclasses import asdict

from clipador.config import Config

MAX_REGISTRO = 300

# status de um item
FILA, RODANDO, OK, FALHOU, CANCELADO = "fila", "rodando", "ok", "falhou", "cancelado"
TERMINADOS = (OK, FALHOU, CANCELADO)


def etapas_previstas(cfg: Config) -> list[str]:
    """Nomes das etapas na ordem do pipeline.executar (para desenhar as que ainda nao comecaram)."""
    if cfg.sem_ia:
        escolha = ["Escolha pelos picos de audio"]
    elif not cfg.visao:
        escolha = ["Escolha pela fala"]
    else:
        escolha = ["1a passada: candidatos pela fala", "2a passada: a IA olha a tela"]
    return ["Video", "Transcricao", "Sinais", *escolha, "Render"]


def _tokens_vazios() -> dict:
    return {"entrada": 0, "saida": 0, "chamadas": 0, "falhas": 0, "rodando": 0, "custo": 0.0}


class Estado:
    def __init__(self):
        self._trava = threading.RLock()
        self._mudou = threading.Condition(self._trava)
        self.itens: list[dict] = []
        self.configs: dict[int, Config] = {}
        self.versao = 0
        self._proximo_id = 0

    # ------------------------------------------------------------ fila

    def adicionar(self, fontes: list[str], cfg: Config, canal: str = "") -> list[int]:
        ids = []
        with self._trava:
            for fonte in fontes:
                self._proximo_id += 1
                i = self._proximo_id
                self.configs[i] = cfg
                self.itens.append({
                    "id": i, "fonte": fonte, "canal": canal, "status": FILA,
                    "titulo": "", "duracao": None, "pasta": "", "pasta_cortes": "", "erro": "",
                    "cortes": 0, "criado": time.time(), "inicio": None, "fim": None,
                    "opcoes": {k: v for k, v in asdict(cfg).items()
                               if k in ("modo", "cortes", "dmin", "dmax", "visao", "sem_ia", "reprisar_ia",
                                        "chat", "credito", "modelo")},
                    "etapas_previstas": etapas_previstas(cfg), "etapas": [],
                    "barras": {}, "tokens": _tokens_vazios(), "registro": [], "candidatos": [],
                    "resumo": None,
                })
                ids.append(i)
            self._tocar()
        return ids

    def proximo(self) -> dict | None:
        with self._trava:
            return next((it for it in self.itens if it["status"] == FILA), None)

    def esperar_mudanca(self, versao: int, timeout: float) -> int:
        with self._mudou:
            if self.versao == versao:
                self._mudou.wait(timeout)
            return self.versao

    def item(self, i: int) -> dict | None:
        with self._trava:
            return next((it for it in self.itens if it["id"] == i), None)

    def config(self, i: int) -> Config:
        return self.configs[i]

    def comecar(self, i: int):
        with self._trava:
            it = self.item(i)
            it["status"], it["inicio"] = RODANDO, time.time()
            self._tocar()

    def terminar(self, i: int, ok: bool, erro: str = "", **dados):
        with self._trava:
            it = self.item(i)
            if it is None or it["status"] in TERMINADOS:
                return
            it["status"] = OK if ok else FALHOU
            it["erro"] = erro
            it["fim"] = time.time()
            it["barras"] = {}
            it["tokens"]["rodando"] = 0
            for e in it["etapas"]:
                if e["status"] == "rodando":
                    e["status"] = "ok" if ok else "erro"
            it.update(dados)
            self._tocar()

    def cancelar_pendentes(self, incluir_rodando: bool = True) -> int:
        """Cancela o que esta na fila (e o que esta rodando). Devolve quantos foram cancelados."""
        n = 0
        with self._trava:
            for it in self.itens:
                if it["status"] == FILA or (incluir_rodando and it["status"] == RODANDO):
                    it["status"], it["fim"] = CANCELADO, time.time()
                    it["barras"] = {}
                    for e in it["etapas"]:
                        if e["status"] == "rodando":
                            e["status"] = "erro"
                    n += 1
            self._tocar()
        return n

    def remover_terminados(self):
        with self._trava:
            self.itens = [it for it in self.itens if it["status"] not in TERMINADOS]
            self._tocar()

    # ------------------------------------------------------------ eventos do ui.py

    def aplicar(self, i: int, ev: dict):
        with self._trava:
            it = self.item(i)
            if it is None or it["status"] in TERMINADOS:
                return
            tipo = ev.get("tipo")
            if tipo == "execucao":
                it["etapas"] = []
            elif tipo == "etapa":
                if ev["status"] == "rodando":
                    it["etapas"].append({"n": ev["n"], "titulo": ev["titulo"], "status": "rodando",
                                         "tempo": None, "inicio": time.time()})
                    it["barras"] = {}
                else:
                    for e in reversed(it["etapas"]):
                        if e["n"] == ev["n"]:
                            e["status"], e["tempo"] = ev["status"], ev.get("tempo")
                            break
            elif tipo == "barra":
                chave = str(ev["id"])
                if ev.get("ativa", True):
                    it["barras"][chave] = {k: ev[k] for k in ("id", "descricao", "feito", "total", "unidade")}
                else:
                    it["barras"].pop(chave, None)
            elif tipo == "tokens":
                it["tokens"] = {k: ev.get(k, 0) for k in _tokens_vazios()}
            elif tipo == "msg":
                it["registro"].append({"nivel": ev.get("nivel", "info"), "texto": ev.get("texto", ""),
                                       "hora": time.time()})
                del it["registro"][:-MAX_REGISTRO]
            elif tipo == "candidato":
                it["candidatos"].append({k: v for k, v in ev.items() if k != "tipo"})
            elif tipo == "candidatos":
                it["candidatos"] = list(ev.get("linhas", []))
            elif tipo == "video":
                it["titulo"], it["duracao"], it["pasta"] = ev.get("titulo", ""), ev.get("duracao"), ev.get("pasta", "")
            elif tipo == "resumo":
                it["resumo"] = {k: v for k, v in ev.items() if k != "tipo"}
            else:
                return
            self._tocar()

    # ------------------------------------------------------------ leitura

    def tokens_total(self) -> dict:
        total = _tokens_vazios()
        with self._trava:
            for it in self.itens:
                for k in total:
                    total[k] += it["tokens"].get(k, 0)
        return total

    def rodando(self) -> bool:
        with self._trava:
            return any(it["status"] in (FILA, RODANDO) for it in self.itens)

    def foto(self) -> dict:
        """Copia serializavel de tudo (vai pelo SSE)."""
        import copy
        with self._trava:
            return {"versao": self.versao, "rodando": self.rodando(), "agora": time.time(),
                    "itens": copy.deepcopy(self.itens), "tokens_total": self.tokens_total()}

    def _tocar(self):
        self.versao += 1
        self._mudou.notify_all()
