from clipador.render.legendas import blocos_de_palavras, gerar_ass, limpar_ass, tempo_ass


def palavras(*itens):
    return [{"start": a, "end": b, "word": w} for a, b, w in itens]


def test_tempo_ass():
    assert tempo_ass(0) == "0:00:00.00"
    assert tempo_ass(75.5) == "0:01:15.50"
    assert tempo_ass(3725.25) == "1:02:05.25"
    assert tempo_ass(-3) == "0:00:00.00"


def test_limpar_ass_remove_comandos():
    assert limpar_ass("{\\b1}oi\nmundo") == "(b1)oi mundo"


def test_blocos_quebram_em_3_palavras_ou_pontuacao():
    segs = [{"start": 0, "end": 5, "text": "",
             "words": palavras((0, 1, "eu"), (1, 2, "nao"), (2, 3, "acredito"),
                               (3, 3.5, "mano!"), (3.5, 4, "olha"))}]
    blocos = blocos_de_palavras(segs, 0, 5)
    assert [[w["word"] for w in b] for b in blocos] == [["eu", "nao", "acredito"], ["mano!"], ["olha"]]


def test_gerar_ass_tem_titulo_credito_e_legendas(tmp_path):
    segs = [{"start": 10, "end": 12, "text": "", "words": palavras((10, 11, "que"), (11, 12, "isso"))}]
    arq = tmp_path / "x.ass"
    gerar_ass(arq, segs, 10, 20, "Titulo do corte", "@canal")
    txt = arq.read_text(encoding="utf-8")
    assert "Credito,,0,0,0,,@canal" in txt
    assert "TITULO DO CORTE" in txt
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Legenda,,0,0,0,,QUE ISSO" in txt
