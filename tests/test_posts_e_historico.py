import json

from clipador.analise.chat import picos_de_chat
from clipador.modelos import Corte
from clipador.publicacao.historico import Historico
from clipador.publicacao.posts import montar_post, salvar_posts


def test_montar_post_credito_e_hashtags_sem_repetir():
    c = Corte(inicio=1, fim=30, legenda_post="olha isso", hashtags=["#GTA6", "#fyp"], nota=9)
    post = montar_post(c, "corte_01.mp4", "@canal", ["#gta6", "#gtavi"])
    assert post["legenda_post"] == "olha isso\n\nCredito: @canal"
    assert post["hashtags"] == ["#GTA6", "#fyp", "#gtavi"]
    assert post["arquivo"] == "corte_01.mp4"


def test_salvar_posts(tmp_path):
    post = montar_post(Corte(inicio=65, fim=95, legenda_post="x", nota=9), "corte_01.mp4")
    salvar_posts(tmp_path, [post])
    assert json.loads((tmp_path / "posts.json").read_text(encoding="utf-8"))[0]["inicio"] == 65
    assert "=== corte_01.mp4  (01:05-01:35, nota 9)" in (tmp_path / "posts.txt").read_text(encoding="utf-8")


def test_historico(tmp_path):
    h = Historico(tmp_path / "h.db")
    assert not h.ja_processada("url")
    h.registrar_fonte("url", "titulo", tmp_path)
    h.registrar_corte("url", tmp_path / "c1.mp4", {"inicio": 0, "fim": 30, "nota": 5})
    h.registrar_corte("url", tmp_path / "c2.mp4", {"inicio": 40, "fim": 70, "nota": 9})
    assert h.ja_processada("url")
    assert [r["nota"] for r in h.pendentes()] == [9, 5]
    h.marcar_postado(tmp_path / "c2.mp4", "https://tiktok.com/...")
    assert len(h.pendentes()) == 1
    h.fechar()


def test_picos_de_chat_acha_explosao_de_mensagens():
    tempos = [float(t) for t in range(0, 300, 10)] + [150 + i * 0.1 for i in range(40)]
    picos = picos_de_chat(tempos, quantidade=1)
    assert 145 <= picos[0]["segundo"] <= 160
