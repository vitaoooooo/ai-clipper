"""Sinais da fase 1: movimento na tela, candidatos visuais, chat opcional e prompts."""
import json

from clipador.analise import chat
from clipador.analise.cenas import picos_visuais
from clipador.modelos import Corte
from clipador.selecao.heuristica import candidatos_visuais
from clipador.selecao.ia import montar_prompt
from clipador.selecao.visao import _sinais_do_trecho


def ativ_com_acao(total=600, acao=(300, 320), preto=(100, 130)):
    mov = [1.0] * total
    brilho = [120.0] * total
    for s in range(*acao):
        mov[s] = 8.0
    for s in range(*preto):       # loading: muda muito (fade) mas e tela preta
        mov[s], brilho[s] = 9.0, 5.0
    return {"movimento": mov, "brilho": brilho}


def test_picos_visuais_acha_acao_e_ignora_tela_preta():
    picos = picos_visuais(ativ_com_acao())
    assert picos, "deveria achar o trecho de acao"
    assert all(290 <= p["segundo"] <= 320 for p in picos)     # so a acao, nao o loading
    assert picos[0]["movimento_x_media"] > 1.5


def test_video_parado_nao_tem_pico():
    assert picos_visuais({"movimento": [1.0] * 300, "brilho": [100.0] * 300}) == []


def test_ruido_em_video_quase_parado_nao_vira_pico():
    mov = [0.0] * 300
    mov[50] = 0.02                          # ruido de compressao
    for s in range(150, 170):
        mov[s] = 6.0                        # acao de verdade
    picos = picos_visuais({"movimento": mov, "brilho": [100.0] * 300})
    assert len(picos) == 1 and 145 <= picos[0]["segundo"] <= 170
    assert picos[0]["movimento_x_media"] < 50      # numero com sentido, nao 99730x


def segs_de(total, passo=6):
    return [{"start": float(t), "end": float(t + passo), "text": "x", "words": []} for t in range(0, total, passo)]


def test_candidatos_visuais_nao_repetem_candidatos_da_fala():
    picos = [{"segundo": 100, "movimento_x_media": 3.0}, {"segundo": 400, "movimento_x_media": 2.0}]
    existentes = [Corte(inicio=90, fim=130, nota=8)]       # a fala ja pegou o pico de 100s
    extras = candidatos_visuais(picos, existentes, segs_de(600), 600, 4, 20, 40)
    assert len(extras) == 1
    c = extras[0]
    assert c.inicio < 400 < c.fim and 20 <= c.duracao <= 40
    assert "movimento" in c.motivo


def test_candidatos_visuais_desligado():
    assert candidatos_visuais([{"segundo": 100, "movimento_x_media": 3.0}], [], segs_de(600), 600, 0, 20, 40) == []


def test_prompt_so_mostra_chat_e_movimento_quando_existem():
    segs = segs_de(60)
    picos = [{"segundo": 10, "acima_da_media_db": 12.0}]
    sem = montar_prompt(segs, picos, "v", 3, 20, 60)
    assert "PICOS DE AUDIO" in sem and "CHAT" not in sem and "MOVIMENTO" not in sem
    com = montar_prompt(segs, picos, "v", 3, 20, 60,
                        picos_chat=[{"segundo": 30, "mensagens": 80, "vezes_a_media": 6.0}],
                        picos_vis=[{"segundo": 40, "movimento_x_media": 2.5}])
    assert "30s (80 msgs, 6.0x)" in com and "40s (2.5x)" in com
    assert "o chat da live explode" in com


def test_sinais_do_trecho_para_a_visao():
    sinais = {"audio": [{"segundo": 15, "acima_da_media_db": 10.0}],
              "chat": [{"segundo": 99, "mensagens": 50, "vezes_a_media": 4.0}],
              "visual": [{"segundo": 5, "movimento_x_media": 2.0}]}
    txt = _sinais_do_trecho(sinais, 10, 40)
    assert "15s: audio alto" in txt and "movimento" in txt   # janela 5-15s encosta no trecho
    assert "chat" not in txt                                 # 99s fica fora
    assert _sinais_do_trecho(None, 0, 10) == "(nenhum)"


def test_chat_le_arquivo_twitch_e_youtube(tmp_path):
    tw = tmp_path / "tw.json"
    tw.write_text(json.dumps({"comments": [{"content_offset_seconds": 1.5}, {"content_offset_seconds": 9}]}),
                  encoding="utf-8")
    assert chat.obter_tempos_chat("qualquer", tmp_path, tw) == [1.5, 9.0]

    yt = tmp_path / "live_chat.json"
    linha = {"replayChatItemAction": {"videoOffsetTimeMsec": "4200",
                                      "actions": [{"addChatItemAction": {}}]}}
    yt.write_text(json.dumps(linha) + "\n" + json.dumps(linha) + "\n", encoding="utf-8")
    assert chat.obter_tempos_chat("qualquer", tmp_path, yt) == [4.2, 4.2]


def test_chat_video_local_sem_arquivo_segue_sem_chat(tmp_path, capsys):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    assert chat.obter_tempos_chat(str(video), tmp_path) == []
    assert "--chat-arquivo" in capsys.readouterr().out


def test_chat_twitch_sem_downloader_segue_sem_chat(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(chat.shutil, "which", lambda _: None)
    assert chat.obter_tempos_chat("https://www.twitch.tv/videos/123456", tmp_path) == []
    assert "TwitchDownloaderCLI" in capsys.readouterr().out


def test_chat_erro_nao_derruba(tmp_path, monkeypatch, capsys):
    def explode(url, pasta):
        raise OSError("sem internet")
    monkeypatch.setattr(chat, "baixar_chat_youtube", explode)
    assert chat.obter_tempos_chat("https://youtube.com/watch?v=x", tmp_path) == []
    assert "seguindo sem ele" in capsys.readouterr().out
