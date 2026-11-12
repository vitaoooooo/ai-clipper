"""1a passada em blocos de ~1h para lives longas (sem chamar a IA de verdade)."""
import json
import re

import pytest

from clipador.selecao import ia


def segs_de(segundos, passo=10):
    return [{"start": float(t), "end": float(t + passo), "text": f"fala {t}", "words": []}
            for t in range(0, int(segundos), passo)]


def test_video_curto_fica_num_bloco_so():
    segs = segs_de(4000)                       # ~1h07: cabe em 1 bloco (sobra < 15 min)
    [(ini, fim, s)] = ia.dividir_em_blocos(segs)
    assert (ini, fim) == (0.0, 4000.0) and len(s) == len(segs)


def test_live_longa_vira_blocos_com_sobreposicao():
    blocos = ia.dividir_em_blocos(segs_de(8 * 3600))
    assert len(blocos) == 8
    assert blocos[0][:2] == (0.0, 3600.0)
    assert blocos[1][0] == 3600 - ia.SOBREPOSICAO_SEG          # emenda coberta pelos dois
    assert blocos[-1][1] == 8 * 3600                          # ultimo vai ate o fim
    assert all(s["end"] > ini and s["start"] < fim for ini, fim, ss in blocos for s in ss)


def test_sobra_pequena_e_absorvida():
    blocos = ia.dividir_em_blocos(segs_de(2 * 3600 + 600))    # sobra de 10 min
    assert len(blocos) == 2 and blocos[-1][1] == 2 * 3600 + 600


def _falsa_ia(chamadas, falhar_em=None):
    def chamar(prompt, schema, modelo):
        m = re.search(r"parte (\d+) de \d+", prompt)
        parte = int(m.group(1)) if m else 1
        chamadas.append(parte)
        if parte == falhar_em:
            raise RuntimeError("limite atingido")
        n = int(re.search(r"Escolha os (\d+) melhores", prompt).group(1))
        # devolve trechos dentro do bloco, com o tempo do 1o segmento do prompt
        t0 = float(prompt.split("<transcricao>\n[")[1].split("-")[0])
        cortes = [{"inicio": t0 + 100 * k, "fim": t0 + 100 * k + 30, "titulo": "t", "legenda_post": "",
                   "hashtags": [], "nota": 5, "motivo": "m"} for k in range(n)]
        return {"cortes": cortes}, {"modelo": modelo, "uso": {"entrada": 10, "saida": 2}}
    return chamar


def test_live_longa_pede_por_bloco_e_junta(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(ia, "chamar_ia", _falsa_ia(chamadas))
    saida = tmp_path / "resposta_ia.json"
    cortes = ia.escolher_com_ia(segs_de(3 * 3600), [], "live", 6, 20, 60, "m", salvar_em=saida)

    assert len(chamadas) == 3
    assert len(cortes) >= 6                                   # cada bloco pede um pouco a mais
    assert {int(c.inicio // 3600) for c in cortes} == {0, 1, 2}   # tem candidato de todas as horas
    registro = json.loads(saida.read_text(encoding="utf-8"))
    assert len(registro["blocos"]) == 3 and registro["uso"] == {"entrada": 30, "saida": 6}
    assert not (tmp_path / "ia_blocos").exists()              # cache apagado quando tudo deu certo


def test_falha_num_bloco_retoma_so_ele(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(ia, "chamar_ia", _falsa_ia(chamadas, falhar_em=2))
    saida = tmp_path / "resposta_ia.json"
    with pytest.raises(RuntimeError, match="1 de 3 blocos falharam"):
        ia.escolher_com_ia(segs_de(3 * 3600), [], "live", 6, 20, 60, "m", salvar_em=saida)
    assert len(list((tmp_path / "ia_blocos").glob("*.json"))) == 2   # os que deram certo ficaram

    chamadas.clear()
    monkeypatch.setattr(ia, "chamar_ia", _falsa_ia(chamadas))
    ia.escolher_com_ia(segs_de(3 * 3600), [], "live", 6, 20, 60, "m", salvar_em=saida)
    assert chamadas == [2]                                    # so o bloco que faltou foi refeito


def test_video_curto_mantem_um_pedido_sem_cache(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(ia, "chamar_ia", _falsa_ia(chamadas))
    cortes = ia.escolher_com_ia(segs_de(1800), [], "video", 5, 20, 60, "m",
                                salvar_em=tmp_path / "resposta_ia.json")
    assert len(chamadas) == 1 and len(cortes) == 5
    assert not (tmp_path / "ia_blocos").exists()
