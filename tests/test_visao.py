"""2a passada (visao): amostragem de frames e escolha dos N melhores, sem chamar a IA."""
import shutil

import pytest

from clipador.analise.frames import amostrar, extrair_frames
from clipador.modelos import Corte
from clipador.selecao import visao
from clipador.util import rodar


def test_amostrar_respeita_maximo():
    frames = [f"f{i}" for i in range(200)]
    escolhidos = amostrar(frames, 90)
    assert len(escolhidos) == 90
    assert escolhidos[0] == (0, "f0")
    assert all(frames[i] == f for i, f in escolhidos)
    assert amostrar(frames[:10], 90) == list(enumerate(frames[:10]))


def test_escolhe_os_melhores_so_entre_candidatos(tmp_path, monkeypatch):
    candidatos = [Corte(0, 20, "a", nota=9), Corte(30, 50, "b", nota=8), Corte(60, 80, "c", nota=7)]
    notas_visao = {0: 4, 30: 9, 60: 8}
    vistos = []

    def falso_extrair(video, ini, fim, pasta, **kw):
        f = tmp_path / f"{ini}.jpg"
        f.write_bytes(b"\xff\xd8jpeg")
        return [f] * int(fim - ini)

    def falso_chamar(conteudo, schema, modelo):
        texto = conteudo[0]["text"]
        ini = next(c.inicio for c in candidatos if f"Trecho: {c.inicio:.1f}s" in texto)
        vistos.append(sum(1 for b in conteudo if b["type"] == "image"))
        dados = {"nota": notas_visao[ini], "titulo": f"novo {ini}", "legenda_post": "x",
                 "hashtags": ["#gta6"], "motivo": "m"}
        return dados, {"modelo": modelo, "uso": {"entrada": 1, "saida": 1}}

    monkeypatch.setattr(visao, "extrair_frames", falso_extrair)
    monkeypatch.setattr(visao, "chamar_ia", falso_chamar)
    saida = tmp_path / "resposta_visao.json"
    cortes = visao.escolher_com_visao(candidatos, [], tmp_path / "v.mp4", tmp_path / "frames",
                                      "video", 2, "modelo", salvar_em=saida)

    assert [c.inicio for c in cortes] == [30, 60]          # a nota da imagem decide
    assert cortes[0].titulo == "novo 30"
    assert vistos == [20, 20, 20]                          # 1 print por segundo
    assert saida.exists()


def _sem_frames(video, ini, fim, pasta, **kw):
    return []


def test_todos_falharam_para_com_erro(tmp_path, monkeypatch):
    def falha(conteudo, schema, modelo):
        raise RuntimeError("limite atingido")

    monkeypatch.setattr(visao, "extrair_frames", _sem_frames)
    monkeypatch.setattr(visao, "chamar_ia", falha)
    with pytest.raises(RuntimeError, match="falhou em todos os 2"):
        visao.escolher_com_visao([Corte(0, 20, nota=9), Corte(30, 50, nota=8)], [], tmp_path / "v.mp4",
                                 tmp_path / "frames", "video", 1, "modelo")


def test_falha_parcial_avisa_e_prefere_avaliados(tmp_path, monkeypatch, capsys):
    def metade(conteudo, schema, modelo):
        if "Trecho: 0.0s" in conteudo[0]["text"]:
            raise RuntimeError("limite atingido")
        dados = {"nota": 6, "titulo": "t", "legenda_post": "x", "hashtags": [], "motivo": "m"}
        return dados, {"modelo": modelo, "uso": {}}

    monkeypatch.setattr(visao, "extrair_frames", _sem_frames)
    monkeypatch.setattr(visao, "chamar_ia", metade)
    [c] = visao.escolher_com_visao([Corte(0, 20, nota=9), Corte(30, 50, nota=8)], [], tmp_path / "v.mp4",
                                   tmp_path / "frames", "video", 1, "modelo")
    assert c.inicio == 30                      # o que falhou (nota 9 -> 5) perde para o avaliado (6)
    assert "1 de 2 candidatos" in capsys.readouterr().out


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg nao instalado")
def test_extrair_frames_1_por_segundo(tmp_path):
    v = tmp_path / "v.mp4"
    rodar(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
           "testsrc2=size=1280x720:rate=30:duration=8", "-c:v", "libx264",
           "-preset", "ultrafast", str(v)])
    frames = extrair_frames(v, 2, 7, tmp_path / "frames")
    assert len(frames) == 5
    assert extrair_frames(v, 2, 7, tmp_path / "frames") == frames   # cache
