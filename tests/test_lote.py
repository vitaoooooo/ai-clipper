"""Varios videos de uma vez (--lista ou varios links), sem rodar o pipeline de verdade."""
import pytest

from clipador import cli, lote, pipeline
from clipador.config import Config


def test_ler_lista_ignora_vazias_e_comentarios(tmp_path):
    arq = tmp_path / "links.txt"
    arq.write_text("﻿# lives de GTA\nhttps://youtu.be/a\n\n  https://youtu.be/b  \n# fim\n", encoding="utf-8")
    assert lote.ler_lista(arq) == ["https://youtu.be/a", "https://youtu.be/b"]


def test_juntar_fontes_sem_repetir_na_ordem(tmp_path):
    arq = tmp_path / "links.txt"
    arq.write_text("b\nc\na\n", encoding="utf-8")
    assert lote.juntar_fontes(["a", "b"], arq) == ["a", "b", "c"]
    assert lote.juntar_fontes(["x"]) == ["x"]


def _pipeline_falso(falhar: set):
    def executar(fonte, cfg):
        if fonte in falhar:
            raise RuntimeError(f"link quebrado: {fonte}\ndetalhe longo")
        return {"titulo": f"titulo {fonte}", "pasta": f"saida/{fonte}/cortes", "posts": [{}, {}, {}]}
    return executar


def test_um_video_que_falha_nao_para_o_lote(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "executar", _pipeline_falso({"b"}))
    resultados = lote.executar_lote(["a", "b", "c"], Config())
    assert [r["ok"] for r in resultados] == [True, False, True]
    assert resultados[0]["cortes"] == 3 and resultados[1]["erro"] == "link quebrado: b"
    out = capsys.readouterr().out
    assert "video 2/3" in out and "resumo do lote" in out and "2 de 3 videos" in out


def test_video_unico_que_falha_mostra_o_erro_normal(monkeypatch):
    monkeypatch.setattr(pipeline, "executar", _pipeline_falso({"a"}))
    with pytest.raises(RuntimeError, match="link quebrado"):
        lote.executar_lote(["a"], Config())


def test_cli_com_falha_no_lote_sai_com_codigo_1(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                             # sem config.toml do usuario
    monkeypatch.setattr(pipeline, "executar", _pipeline_falso({"b"}))
    arq = tmp_path / "links.txt"
    arq.write_text("b\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["a", "--lista", str(arq), "--sem-ia"])
    assert e.value.code == 1


def test_cli_sem_nenhuma_fonte_reclama(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        cli.main([])
    assert "--lista" in capsys.readouterr().err
