"""Interface grafica (clipador.app): eventos do ui.py, estado da fila, gerente, presets, estimativa,
biblioteca/historico e as rotas HTTP. Nada aqui roda o pipeline de verdade nem chama o Claude."""
import json
import queue
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("tomlkit")

from starlette.testclient import TestClient  # noqa: E402

from clipador import ui  # noqa: E402
from clipador.app import biblioteca, estimativa, presets  # noqa: E402
from clipador.app.estado import Estado, etapas_previstas  # noqa: E402
from clipador.app.gerente import Gerente  # noqa: E402
from clipador.app.servidor import criar_app  # noqa: E402
from clipador.config import Config  # noqa: E402
from clipador.modelos import Corte  # noqa: E402


# ------------------------------------------------------------ eventos do ui.py

def _rodar_sequencia():
    ui.iniciar(2)
    with ui.etapa("Video"):
        ui.ok("baixado")
        ui.aviso("cuidado [x]")
    with ui.etapa("Render"):
        with ui.barra("renderizando", 10, unidade="tempo") as b:
            b.ate(5)
            b.avancar(5)
        ui.uso.comecou()
        ui.uso.terminou(100, 10)
        ui.tabela_visao([(Corte(10, 40, nota=7), Corte(8, 40, "titulo", nota=9), True, False)])
        ui.resumo([Corte(8, 40, "titulo", nota=9)], "saida/x")


def test_ouvinte_recebe_os_eventos_sem_mudar_o_terminal(capsys):
    _rodar_sequencia()
    sem_ouvinte = capsys.readouterr().out
    recebidos = []
    f = ui.ouvir(recebidos.append)
    try:
        _rodar_sequencia()
    finally:
        ui.parar_de_ouvir(f)
    com_ouvinte = capsys.readouterr().out

    def sem_tempos(t):  # o tempo de cada etapa varia entre as duas rodadas
        import re
        return re.sub(r"\d+[,.]\d+s|\d{2}:\d{2}", "T", t)
    assert sem_tempos(sem_ouvinte) == sem_tempos(com_ouvinte)

    tipos = [e["tipo"] for e in recebidos]
    for t in ("execucao", "etapa", "msg", "barra", "tokens", "candidatos", "resumo"):
        assert t in tipos, t
    etapas = [e for e in recebidos if e["tipo"] == "etapa"]
    assert [(e["titulo"], e["status"]) for e in etapas] == [
        ("Video", "rodando"), ("Video", "ok"), ("Render", "rodando"), ("Render", "ok")]
    barras = [e for e in recebidos if e["tipo"] == "barra"]
    assert barras[0]["ativa"] and barras[-1]["ativa"] is False and barras[-1]["feito"] == 10
    assert any(e["tipo"] == "msg" and e["texto"] == "cuidado [x]" and e["nivel"] == "aviso" for e in recebidos)


def test_ouvinte_com_erro_nao_derruba_e_etapa_com_erro_avisa():
    recebidos = []

    def ruim(_):
        raise ValueError("bug no ouvinte")
    ui.ouvir(ruim)
    ui.ouvir(recebidos.append)
    try:
        ui.iniciar(1)
        with pytest.raises(RuntimeError):
            with ui.etapa("Transcricao"):
                raise RuntimeError("falhou")
    finally:
        ui.parar_de_ouvir(ruim)
        ui.parar_de_ouvir(recebidos.append)
    assert recebidos[-1]["tipo"] == "etapa" and recebidos[-1]["status"] == "erro"


def test_barra_limita_eventos_por_segundo():
    recebidos = []
    ui.ouvir(recebidos.append)
    try:
        with ui.barra("x", 1000) as b:
            for _ in range(1000):
                b.avancar()
    finally:
        ui.parar_de_ouvir(recebidos.append)
    barras = [e for e in recebidos if e["tipo"] == "barra"]
    assert len(barras) < 20 and barras[-1]["feito"] == 1000


# ------------------------------------------------------------ estado

def test_etapas_previstas_seguem_o_pipeline():
    assert len(etapas_previstas(Config())) == 6
    assert etapas_previstas(Config(visao=False))[3] == "Escolha pela fala"
    assert etapas_previstas(Config(sem_ia=True))[3] == "Escolha pelos picos de audio"


def test_estado_aplica_eventos_e_foto_e_serializavel():
    e = Estado()
    i, j = e.adicionar(["a", "b"], Config())
    e.comecar(i)
    for ev in [{"tipo": "execucao", "total": 6},
               {"tipo": "etapa", "n": 1, "total": 6, "titulo": "Video", "status": "rodando"},
               {"tipo": "video", "titulo": "Live", "duracao": 100, "pasta": "p"},
               {"tipo": "barra", "id": 1, "descricao": "baixando", "feito": 5, "total": 10, "unidade": "bytes", "ativa": True},
               {"tipo": "tokens", "entrada": 10, "saida": 2, "chamadas": 1, "falhas": 0, "rodando": 1, "custo": 0},
               {"tipo": "msg", "nivel": "ok", "texto": "oi"},
               {"tipo": "candidato", "inicio_antes": 1, "fim_antes": 2, "nota": 8},
               {"tipo": "desconhecido"}]:
        e.aplicar(i, ev)
    it = e.item(i)
    assert it["titulo"] == "Live" and it["etapas"][0]["status"] == "rodando"
    assert it["barras"]["1"]["feito"] == 5 and it["tokens"]["entrada"] == 10
    assert e.proximo()["id"] == j
    e.aplicar(i, {"tipo": "barra", "id": 1, "ativa": False, "descricao": "", "feito": 0, "total": 0, "unidade": "x"})
    assert it["barras"] == {}
    e.terminar(i, True, cortes=3)
    assert it["status"] == "ok" and it["etapas"][0]["status"] == "ok"
    json.dumps(e.foto())   # vai pelo SSE
    assert e.cancelar_pendentes() == 1 and e.item(j)["status"] == "cancelado"
    e.remover_terminados()
    assert e.itens == []


# ------------------------------------------------------------ gerente (processo falso, em thread)

class _Falso:
    def __init__(self, alvo, fonte, fila):
        self.morto = threading.Event()
        self.t = threading.Thread(target=alvo, args=(fonte, fila, self), daemon=True)
        self.t.start()

    def vivo(self):
        return self.t.is_alive()

    def matar(self):
        self.morto.set()

    def esperar(self, timeout=5):
        self.t.join(timeout)


def _roteiro(fonte, fila, proc):
    fila.put({"tipo": "execucao", "total": 6})
    fila.put({"tipo": "etapa", "n": 1, "total": 6, "titulo": "Video", "status": "rodando"})
    if fonte == "lento":
        proc.morto.wait(5)
        return   # morreu sem mandar "fim"
    if fonte == "quebrado":
        fila.put({"tipo": "fim", "ok": False, "erro": "link quebrado"})
        return
    if fonte == "mudo":
        return
    fila.put({"tipo": "fim", "ok": True, "titulo": f"T {fonte}", "pasta_cortes": f"saida/{fonte}/cortes",
              "posts": [{"arquivo": "corte_01.mp4"}]})


def _gerente(terminados=None):
    e = Estado()
    g = Gerente(e, lancar=lambda fonte, cfg, fila: _Falso(_roteiro, fonte, fila), nova_fila=queue.Queue,
                ao_terminar=(lambda it, fim: terminados.append((it["fonte"], fim["titulo"]))) if terminados is not None else None)
    return e, g


def _esperar(cond, timeout=10):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_gerente_roda_em_ordem_e_um_erro_nao_para_a_fila():
    terminados = []
    e, g = _gerente(terminados)
    try:
        ids = g.enfileirar(["a", "quebrado", "mudo", "b"], Config())
        assert _esperar(lambda: all(e.item(i)["status"] in ("ok", "falhou") for i in ids))
        st = [e.item(i)["status"] for i in ids]
        assert st == ["ok", "falhou", "falhou", "ok"]
        assert e.item(ids[1])["erro"] == "link quebrado"
        assert "sem avisar" in e.item(ids[2])["erro"]
        assert e.item(ids[0])["titulo"] == "T a" and e.item(ids[0])["cortes"] == 1
        assert terminados == [("a", "T a"), ("b", "T b")]
    finally:
        g.encerrar()


def test_gerente_parar_mata_o_atual_e_cancela_a_fila():
    e, g = _gerente()
    try:
        ids = g.enfileirar(["lento", "a"], Config())
        assert _esperar(lambda: e.item(ids[0])["status"] == "rodando" and e.item(ids[0])["etapas"])
        assert g.parar() == 2
        assert _esperar(lambda: e.item(ids[0])["status"] == "cancelado")
        time.sleep(0.5)
        assert e.item(ids[1])["status"] == "cancelado"
    finally:
        g.encerrar()


# ------------------------------------------------------------ presets (config.toml com comentarios)

CONFIG_COM_COMENTARIOS = """# meu config
[padrao]
cortes = 5   # quantos cortes
hashtags_extras = ["#gta6"]

# streamer principal
[canais.mount]
credito = "@mount"  # credito fixo
modo = "blur"
"""


def test_salvar_canal_preserva_comentarios_e_valida(tmp_path):
    (tmp_path / "config.toml").write_text(CONFIG_COM_COMENTARIOS, encoding="utf-8")
    presets.salvar_canal(tmp_path, "mount", {"modo": "facecam", "facecam": [0.02, 0.04, 0.26, 0.333333]})
    presets.salvar_canal(tmp_path, "rewards", {"dmin": 61, "dmax": 90})
    texto = (tmp_path / "config.toml").read_text(encoding="utf-8")
    for comentario in ("# meu config", "# quantos cortes", "# streamer principal", "# credito fixo"):
        assert comentario in texto
    cfg = presets.resolver(tmp_path, "mount")
    assert cfg.modo == "facecam" and cfg.facecam == (0.02, 0.04, 0.26, 0.3333) and cfg.credito == "@mount"
    assert presets.resolver(tmp_path, "rewards").dmin == 61
    # None apaga a chave
    presets.salvar_canal(tmp_path, "mount", {"credito": None})
    assert presets.resolver(tmp_path, "mount").credito == ""
    with pytest.raises(ValueError):
        presets.salvar_canal(tmp_path, "mount", {"modo": "facecam", "facecam": None})   # facecam sem regiao
    with pytest.raises(ValueError):
        presets.salvar_canal(tmp_path, "nome com espaco", {"cortes": 3})
    with pytest.raises(ValueError):
        presets.salvar_canal(tmp_path, "x", {"nao_existe": 1})
    assert "# meu config" in (tmp_path / "config.toml").read_text(encoding="utf-8")
    presets.apagar_canal(tmp_path, "rewards")
    assert "rewards" not in presets.ler(tmp_path)["canais"]


def test_sem_config_cria_a_partir_do_exemplo(tmp_path):
    exemplo = Path(__file__).parent.parent / "config.example.toml"
    (tmp_path / "config.example.toml").write_text(exemplo.read_text(encoding="utf-8"), encoding="utf-8")
    assert not presets.ler(tmp_path)["existe"]
    presets.salvar_canal(tmp_path, "novo", {"cortes": 3})
    texto = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert texto.startswith(exemplo.read_text(encoding="utf-8").splitlines()[0])
    assert "[canais.novo]" in texto and presets.resolver(tmp_path, "novo").cortes == 3


# ------------------------------------------------------------ estimativa

def test_estimativa_de_chamadas():
    assert estimativa.blocos(None) == 1
    assert estimativa.blocos(3600 * 1.2) == 1          # ate ~1h15: um bloco
    assert estimativa.blocos(3600 * 8) == 8
    cfg = Config(cortes=5, candidatos=12, candidatos_visuais=4)
    assert estimativa.chamadas(cfg, 3600)["total"] == 1 + 16
    assert estimativa.chamadas(Config(visao=False), 3600)["total"] == 1
    assert estimativa.chamadas(Config(reprisar_ia=True), 3600)["total"] == 0
    assert estimativa.chamadas(Config(sem_ia=True), 3600)["total"] == 0
    assert estimativa.chamadas(Config(cenas=False), 3600)["segunda"] == 12
    r = estimativa.estimar(cfg, [3600, None])
    assert r["total"] == 34 and r["aproximado"]


# ------------------------------------------------------------ biblioteca e historico

def _video_pronto(saida: Path, nome="live-teste", n=2) -> Path:
    cortes = saida / nome / "cortes"
    cortes.mkdir(parents=True)
    posts = []
    for i in range(1, n + 1):
        (cortes / f"corte_{i:02d}.mp4").write_bytes(bytes(range(256)) * 40)
        posts.append({"arquivo": f"corte_{i:02d}.mp4", "inicio": 10.0 * i, "fim": 10.0 * i + 30, "titulo": f"t{i}",
                      "legenda_post": "leg", "hashtags": ["gta6", "#fyp"], "nota": 7.0 + i, "motivo": "m"})
    (cortes / "posts.json").write_text(json.dumps(posts), encoding="utf-8")
    return cortes


def test_biblioteca_lista_e_marca_postado(tmp_path):
    saida = tmp_path / "saida"
    _video_pronto(saida)
    (saida / "sem-cortes").mkdir()
    vs = biblioteca.listar(saida)
    assert [v["pasta"] for v in vs] == ["live-teste"] and vs[0]["melhor_nota"] == 9 and vs[0]["postados"] == 0
    d = biblioteca.posts(saida, "live-teste")
    assert d["posts"][0]["hashtags"] == ["#gta6", "#fyp"] and d["posts"][0]["postado_em"] is None
    assert biblioteca.marcar(saida, "live-teste", "corte_02.mp4", True)
    assert biblioteca.listar(saida)[0]["postados"] == 1
    assert biblioteca.posts(saida, "live-teste")["posts"][1]["postado_em"]
    assert biblioteca.marcar(saida, "live-teste", "corte_02.mp4", False) is None
    with pytest.raises(ValueError):
        biblioteca.pasta_do_video(saida, "..")
    with pytest.raises(ValueError):
        biblioteca.marcar(saida, "live-teste", "nao_existe.mp4", True)


def test_registrar_video_usa_titulo_da_fonte(tmp_path):
    saida = tmp_path / "saida"
    cortes = _video_pronto(saida, "primeiro-dia")
    posts = json.loads((cortes / "posts.json").read_text(encoding="utf-8"))
    biblioteca.registrar_video(saida, "https://twitch.tv/videos/1", "PRIMEIRO DIA", cortes, posts)
    v = biblioteca.listar(saida)[0]
    assert v["titulo"] == "PRIMEIRO DIA" and v["fonte"] == "https://twitch.tv/videos/1"


# ------------------------------------------------------------ rotas HTTP

class _GerenteFalso:
    def __init__(self):
        self.estado = Estado()
        self.enfileirados = []
        self._ao_terminar = None

    def enfileirar(self, fontes, cfg, canal=""):
        self.enfileirados.append((fontes, cfg, canal))
        return self.estado.adicionar(fontes, cfg, canal)

    def parar(self):
        return self.estado.cancelar_pendentes()

    def encerrar(self):
        self.parar()


@pytest.fixture
def cliente(tmp_path):
    (tmp_path / "config.toml").write_text(CONFIG_COM_COMENTARIOS, encoding="utf-8")
    _video_pronto(tmp_path / "saida")
    g = _GerenteFalso()
    return TestClient(criar_app(tmp_path, gerente=g)), g, tmp_path


def test_api_basica(cliente):
    c, g, raiz = cliente
    assert c.get("/api/saude").json()["app"] == "clipador"
    assert "Clipador" in c.get("/").text
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/icone.ico").status_code == 200
    cfg = c.get("/api/config?canal=mount").json()
    assert cfg["resolvido"]["credito"] == "@mount" and "mount" in cfg["presets"]["canais"]
    assert c.get("/api/config?canal=naoexiste").json()["erro"]


def test_api_executar_valida_e_enfileira(cliente):
    c, g, raiz = cliente
    assert c.post("/api/executar", json={"fontes": []}).status_code == 400
    r = c.post("/api/executar", json={"fontes": ["x"], "opcoes": {"modo": "facecam"}})
    assert r.status_code == 400 and "facecam" in r.json()["erro"]
    assert c.post("/api/executar", json={"fontes": ["x"], "opcoes": {"hackear": 1}}).status_code == 400
    r = c.post("/api/executar", json={"fontes": ["a", "a", "b"], "canal": "mount",
                                      "opcoes": {"reprisar_ia": True, "cortes": 3, "facecam": None}})
    assert r.status_code == 200 and len(r.json()["ids"]) == 2
    fontes, cfg, canal = g.enfileirados[0]
    assert fontes == ["a", "b"] and cfg.reprisar_ia and cfg.cortes == 3 and cfg.credito == "@mount"
    assert Path(cfg.saida).is_absolute()
    foto = c.get("/api/estado").json()
    assert [i["fonte"] for i in foto["itens"]] == ["a", "b"] and foto["rodando"]
    assert c.post("/api/parar").json()["cancelados"] == 2
    c.post("/api/limpar")
    assert c.get("/api/estado").json()["itens"] == []


def test_api_estimativa_e_presets(cliente):
    c, g, raiz = cliente
    r = c.post("/api/estimativa", json={"fontes": ["a"], "opcoes": {"reprisar_ia": True}}).json()
    assert r["total"] == 0 and r["reprise"]
    r = c.post("/api/estimativa", json={"fontes": ["a", "b"], "opcoes": {}}).json()
    assert r["total"] == 2 * (1 + 12 + 4) and r["aproximado"]
    assert c.put("/api/canais/novo", json={"valores": {"cortes": 4}}).json()["ok"]
    assert c.put("/api/canais/novo", json={"valores": {"modo": "xpto"}}).status_code == 400
    assert "# meu config" in (raiz / "config.toml").read_text(encoding="utf-8")
    assert c.delete("/api/canais/novo").json()["ok"]


def test_api_videos_postado_e_midia_com_range(cliente):
    c, g, raiz = cliente
    vs = c.get("/api/videos").json()["videos"]
    assert vs[0]["pasta"] == "live-teste"
    assert c.get("/api/videos/nao-existe").status_code == 404
    d = c.get("/api/videos/live-teste").json()
    assert len(d["posts"]) == 2
    r = c.post("/api/videos/live-teste/postado", json={"arquivo": "corte_01.mp4", "postado": True}).json()
    assert r["postado_em"]
    assert c.get("/api/videos/live-teste").json()["posts"][0]["postado_em"]
    m = c.get("/midia/live-teste/corte_01.mp4", headers={"Range": "bytes=0-99"})
    assert m.status_code == 206 and len(m.content) == 100
    assert c.get("/midia/live-teste/..%2F..%2Fconfig.toml").status_code == 404
    assert c.get("/midia/live-teste/posts.json").status_code == 200   # so arquivos da pasta cortes


def test_servidor_nao_sobe_de_dentro_da_raiz(monkeypatch, tmp_path):
    """Com `python -m`, subir de dentro da raiz poria o clipador.py dela na frente do pacote."""
    from clipador.app import lancador
    capturado = {}

    def popen(cmd, **kw):
        capturado.update(kw, cmd=cmd)

    monkeypatch.setattr(lancador.subprocess, "Popen", popen)
    monkeypatch.setattr(lancador, "saude", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(lancador, "LOG", tmp_path / "ui.log")
    lancador.subir_servidor(8765, tmp_path)
    assert capturado["cwd"] != tmp_path and "--raiz" in capturado["cmd"]


def test_mensagem_fechar_sem_nada_rodando():
    from clipador.app.lancador import mensagem_fechar
    assert mensagem_fechar(None) == ("Fechar o Clipador?", False)
    texto, aviso = mensagem_fechar({"itens": [{"status": "ok", "titulo": "x"}]})
    assert not aviso and texto == "Fechar o Clipador?"


def test_mensagem_fechar_avisa_o_que_esta_em_andamento():
    from clipador.app.lancador import mensagem_fechar
    foto = {"itens": [
        {"status": "rodando", "titulo": "Live GTA", "etapas": [
            {"titulo": "Baixando", "status": "ok"}, {"titulo": "Transcrevendo", "status": "rodando"}]},
        {"status": "fila", "fonte": "https://x"}, {"status": "fila", "fonte": "https://y"},
    ]}
    texto, aviso = mensagem_fechar(foto)
    assert aviso
    assert "Live GTA (transcrevendo)" in texto
    assert "2 video(s) esperando na fila" in texto
