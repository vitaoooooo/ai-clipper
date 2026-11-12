from clipador.modelos import Corte
from clipador.selecao.ajuste import ajustar_cortes
from clipador.selecao.heuristica import escolher_sem_ia


def seg(start, end, text="fala"):
    return {"start": start, "end": end, "text": text, "words": []}


SEGS = [seg(0, 5), seg(5, 12), seg(12, 20), seg(20, 31), seg(31, 40), seg(40, 55), seg(55, 70)]


def test_encaixa_no_inicio_e_fim_de_frase():
    [c] = ajustar_cortes([Corte(inicio=6, fim=29, nota=9)], SEGS, 100, 1, 10, 60)
    assert c.inicio == 4.8          # inicio da frase (5) - 0.2
    assert c.fim == 31.4            # fim da frase (31) + 0.4


def test_estica_ate_duracao_minima():
    [c] = ajustar_cortes([Corte(inicio=0, fim=4, nota=1)], SEGS, 100, 1, 20, 60)
    assert c.fim - c.inicio >= 20


def test_limita_duracao_maxima_terminando_em_fim_de_frase():
    [c] = ajustar_cortes([Corte(inicio=0, fim=70, nota=1)], SEGS, 100, 1, 10, 30)
    assert c.fim - c.inicio <= 30
    assert c.fim == 20.4                  # fim da frase 12-20 (+0.4), e nao 30 no meio da frase 20-31


def test_estica_ate_fim_de_frase():
    [c] = ajustar_cortes([Corte(inicio=0, fim=4, nota=1)], SEGS, 100, 1, 15, 60)
    assert c.fim == 20.4                  # 1o fim de frase depois de 15s, nao 15 no meio da fala


def test_frase_longa_corta_na_palavra_com_pontuacao():
    palavras = [{"start": t, "end": t + 0.5, "word": "isso!" if t == 24 else "mano"} for t in range(0, 59)]
    segs = [{"start": 0, "end": 60, "text": "monologo", "words": palavras}]
    [c] = ajustar_cortes([Corte(inicio=0, fim=60, nota=1)], segs, 100, 1, 10, 30)
    assert c.fim == 24.6                  # ultima palavra com pontuacao antes de 30s


def test_duracao_minima_61s_para_creator_rewards():
    segs = [seg(t, t + 7) for t in range(0, 200, 7)]
    [c] = ajustar_cortes([Corte(inicio=10, fim=40, nota=1)], segs, 300, 1, 61, 90)
    assert 61 <= c.fim - c.inicio <= 90


def test_remove_sobreposicao_mantendo_maior_nota():
    cortes = [Corte(inicio=5, fim=30, nota=5), Corte(inicio=12, fim=40, nota=9)]
    prontos = ajustar_cortes(cortes, SEGS, 100, 5, 10, 60)
    assert len(prontos) == 1
    assert prontos[0].nota == 9


def test_respeita_quantidade_e_ordena_por_inicio():
    cortes = [Corte(inicio=40, fim=55, nota=3), Corte(inicio=0, fim=12, nota=8),
              Corte(inicio=20, fim=31, nota=5)]
    prontos = ajustar_cortes(cortes, SEGS, 100, 2, 5, 60)
    assert [c.nota for c in prontos] == [8, 5]
    assert prontos[0].inicio < prontos[1].inicio


def test_sem_ia_gera_cortes_em_volta_dos_picos():
    picos = [{"segundo": 100, "acima_da_media_db": 12.0}, {"segundo": 300, "acima_da_media_db": 20.0}]
    cortes = escolher_sem_ia(picos, n=1, dmin=20, dmax=40)
    assert cortes[0].nota == 20.0                       # maior pico primeiro
    assert cortes[0].inicio < 300 < cortes[0].fim
