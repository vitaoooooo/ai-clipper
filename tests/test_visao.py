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
        c = next(c for c in candidatos if f"Trecho sugerido: {c.inicio:.1f}s" in texto)
        ini = c.inicio
        vistos.append(sum(1 for b in conteudo if b["type"] == "image"))
        dados = {"inicio": c.inicio, "fim": c.fim, "nota": notas_visao[ini], "titulo": f"novo {ini}",
                 "legenda_post": "x",
                 "hashtags": ["#gta6"], "motivo": "m"}
        return dados, {"modelo": modelo, "uso": {"entrada": 1, "saida": 1}}

    monkeypatch.setattr(visao, "extrair_frames", falso_extrair)
    monkeypatch.setattr(visao, "chamar_ia", falso_chamar)
    saida = tmp_path / "resposta_visao.json"
    cortes = visao.escolher_com_visao(candidatos, [], tmp_path / "v.mp4", tmp_path / "frames",
                                      "video", 2, "modelo", salvar_em=saida)

    assert [c.inicio for c in cortes] == [30, 60]          # a nota da imagem decide
    assert cortes[0].titulo == "novo 30"
    assert vistos == [40, 70, 80]                          # 1 print/s, 40s antes e 20s depois (0 no inicio)
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
        if "Trecho sugerido: 0.0s" in conteudo[0]["text"]:
            raise RuntimeError("limite atingido")
        dados = {"inicio": 30, "fim": 50, "nota": 6, "titulo": "t", "legenda_post": "x", "hashtags": [],
                 "motivo": "m"}
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


def _ia_com_limites(limites: dict, notas: dict, capturado: list | None = None):
    """IA falsa: para o candidato que comeca em X devolve os limites limites[X] e a nota notas[X]."""
    def chamar(conteudo, schema, modelo):
        texto = conteudo[0]["text"]
        ini = float(texto.split("Trecho sugerido: ")[1].split("s")[0])
        if capturado is not None:
            capturado.append([b["text"] for b in conteudo if b["type"] == "text"][1:4])
        a, b = limites[ini]
        return ({"inicio": a, "fim": b, "nota": notas[ini], "titulo": "t", "legenda_post": "x",
                 "hashtags": [], "motivo": "m"}, {"modelo": modelo, "uso": {}})
    return chamar


def _frames_falsos(tmp_path):
    def extrair(video, ini, fim, pasta, **kw):
        f = tmp_path / "f.jpg"
        f.write_bytes(bytes([0xFF, 0xD8]) + b"jpeg")
        return [f] * int(fim - ini)
    return extrair


def test_ia_corrige_os_limites_briga_que_acabou_depois(tmp_path, monkeypatch):
    """Caso do corte 3: a triagem cortou antes do fim da briga e comecou tarde."""
    marcas = []
    monkeypatch.setattr(visao, "extrair_frames", _frames_falsos(tmp_path))
    monkeypatch.setattr(visao, "chamar_ia", _ia_com_limites({100.0: (92, 148)}, {100.0: 8}, marcas))
    [c] = visao.escolher_com_visao([Corte(100, 130, nota=7)], [], tmp_path / "v.mp4", tmp_path / "fr",
                                   "video", 1, "modelo", dmin=20, dmax=60, total=600)
    assert (c.inicio, c.fim) == (92, 148)
    assert marcas[0] == ["t=60s", "t=61s", "t=62s"]          # tempos absolutos, comecando 40s antes


def test_limites_fora_da_janela_sao_presos_a_ela(tmp_path, monkeypatch):
    monkeypatch.setattr(visao, "extrair_frames", _frames_falsos(tmp_path))
    monkeypatch.setattr(visao, "chamar_ia", _ia_com_limites({100.0: (10, 400)}, {100.0: 8}))
    [c] = visao.escolher_com_visao([Corte(100, 130, nota=7)], [], tmp_path / "v.mp4", tmp_path / "fr",
                                   "video", 1, "modelo", dmin=20, dmax=60, total=600)
    assert c.inicio == 60                                    # 100 - margem de 40 antes
    assert c.fim - c.inicio <= 60                            # o maximo continua valendo


def test_limites_que_crescem_e_se_sobrepoem_fica_a_maior_nota(tmp_path, monkeypatch):
    monkeypatch.setattr(visao, "extrair_frames", _frames_falsos(tmp_path))
    limites = {100.0: (95, 140), 145.0: (132, 170)}         # os dois cresceram e agora se cruzam
    monkeypatch.setattr(visao, "chamar_ia", _ia_com_limites(limites, {100.0: 6, 145.0: 8}))
    cortes = visao.escolher_com_visao([Corte(100, 130, nota=7), Corte(145, 165, nota=7)], [],
                                      tmp_path / "v.mp4", tmp_path / "fr", "video", 2, "modelo",
                                      dmin=20, dmax=60, total=600)
    assert [(c.inicio, c.fim) for c in cortes] == [(132, 170)]


def test_prompt_da_visao_leva_climax_e_contexto_da_triagem(tmp_path, monkeypatch):
    textos = []

    def chamar(conteudo, schema, modelo):
        textos.append(conteudo[0]["text"])
        return ({"inicio": 100, "fim": 130, "falta_contexto": True, "nota": 6, "titulo": "t",
                 "legenda_post": "x", "hashtags": [], "motivo": "m"}, {"modelo": modelo, "uso": {}})

    monkeypatch.setattr(visao, "extrair_frames", _sem_frames)
    monkeypatch.setattr(visao, "chamar_ia", chamar)
    saida = tmp_path / "resposta_visao.json"
    c = Corte(100, 130, nota=7, climax=118, contexto="ele roubou o carro do chefe")
    visao.escolher_com_visao([c], [], tmp_path / "v.mp4", tmp_path / "fr", "video", 1, "modelo",
                             salvar_em=saida, total=600)
    assert "Climax indicado pela triagem: 118.0s" in textos[0]
    assert "ele roubou o carro do chefe" in textos[0]
    assert "40s antes" in textos[0] and "20s" in textos[0]
    import json
    assert json.loads(saida.read_text(encoding="utf-8"))["candidatos"][0]["falta_contexto"] is True
