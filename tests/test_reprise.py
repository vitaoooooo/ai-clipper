"""--reprisar-ia: reusa as respostas salvas sem chamar o Claude."""
import json

import pytest

from clipador.selecao import ia, reprise as mod_reprise
from clipador.selecao.reprise import Reprise


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(mod_reprise, "PAUSA_SEG", 0)
    yield
    ia.reprise = None


def _salvar(pasta, visao=True):
    corte = {"inicio": 100, "fim": 130, "titulo": "t", "legenda_post": "", "hashtags": [], "nota": 7, "motivo": "m"}
    (pasta / "resposta_ia.json").write_text(json.dumps({"modelo": "m", "uso": {}, "blocos": [
        {"inicio": 0, "fim": 600, "modelo": "m", "uso": {"entrada": 900, "saida": 90},
         "resposta": {"cortes": [corte]}}]}), encoding="utf-8")
    if visao:
        resp = {"inicio": 95, "fim": 140, "nota": 9, "titulo": "novo", "legenda_post": "", "hashtags": [],
                "motivo": "m", "falta_contexto": False}
        (pasta / "resposta_visao.json").write_text(json.dumps({"modelo": "m", "candidatos": [
            {"inicio_1a_passada": 100, "fim_1a_passada": 130, "uso": {"entrada": 5000, "saida": 50},
             "resposta": resp}]}), encoding="utf-8")


def test_reprise_devolve_as_respostas_salvas_sem_chamar_o_claude(tmp_path, monkeypatch):
    _salvar(tmp_path)
    monkeypatch.setattr(ia.subprocess, "run", lambda *a, **k: pytest.fail("chamou o Claude"))
    ia.reprise = Reprise(tmp_path, com_visao=True)

    dados, info = ia.chamar_ia(ia.montar_prompt([], [], "v", 3, 20, 60), ia.SCHEMA, "m")
    assert dados["cortes"][0]["inicio"] == 100 and info["uso"]["entrada"] == 900

    # limites um pouco diferentes (ajuste mudou): acha pela sobreposicao
    dados, info = ia.chamar_ia("Trecho sugerido: 101.5s a 129.0s (x)", {}, "m")
    assert dados["titulo"] == "novo" and info["uso"]["entrada"] == 5000


def test_reprise_sem_arquivo_explica(tmp_path):
    with pytest.raises(RuntimeError, match="Rode uma vez com a IA"):
        Reprise(tmp_path, com_visao=False)
    _salvar(tmp_path, visao=False)
    Reprise(tmp_path, com_visao=False)                      # sem visao so precisa da 1a passada
    with pytest.raises(RuntimeError, match="--sem-visao"):
        Reprise(tmp_path, com_visao=True)


def test_reprise_candidato_novo_falha_so_ele(tmp_path):
    _salvar(tmp_path)
    ia.reprise = Reprise(tmp_path, com_visao=True)
    with pytest.raises(RuntimeError, match="nenhuma resposta salva"):
        ia.chamar_ia("Trecho sugerido: 500.0s a 530.0s", {}, "m")
