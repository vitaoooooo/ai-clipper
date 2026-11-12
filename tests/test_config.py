import pytest

from clipador.config import Config, carregar, parse_facecam

TOML = """
[padrao]
cortes = 3
modo = "blur"
hashtags_extras = ["#gta6"]

[canais.streamer]
credito = "@streamer"
modo = "facecam"
facecam = [0.0, 0.0, 0.25, 0.3]
"""


@pytest.fixture
def arq(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(TOML, encoding="utf-8")
    return p


def test_padroes_sem_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # garante que nao existe ./config.toml
    assert carregar() == Config()


def test_prioridade_padrao_canal_cli(arq):
    cfg = carregar(arq, "streamer", {"cortes": 8, "credito": None})
    assert cfg.cortes == 8                     # linha de comando ganha
    assert cfg.credito == "@streamer"          # None na linha de comando nao sobrescreve
    assert cfg.modo == "facecam"               # canal ganha do [padrao]
    assert cfg.facecam == (0.0, 0.0, 0.25, 0.3)
    assert cfg.hashtags_extras == ["#gta6"]


def test_canal_inexistente(arq):
    with pytest.raises(ValueError, match="nao existe"):
        carregar(arq, "outro")


def test_opcao_desconhecida(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[padrao]\ncortez = 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cortez"):
        carregar(p)


def test_facecam_obrigatoria_no_modo_facecam(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="facecam"):
        carregar(sobrescritas={"modo": "facecam"})


def test_parse_facecam():
    assert parse_facecam("0, 0.5, 0.25,0.3") == (0.0, 0.5, 0.25, 0.3)
    with pytest.raises(ValueError):
        parse_facecam("1,2,3")
