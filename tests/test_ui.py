"""Visual do terminal: contador de tokens do Claude e resumo final."""
import threading

from clipador import ui
from clipador.modelos import Corte
from clipador.selecao import ia


def test_contador_de_tokens_soma_chamadas_em_paralelo():
    u = ui.UsoClaude()

    def chamada():
        u.comecou()
        u.terminou(100, 10, 0.01)

    threads = [threading.Thread(target=chamada) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (u.chamadas, u.entrada, u.saida, u.rodando) == (50, 5000, 500, 0)
    assert "5,0k" in u.texto().plain


def test_chamar_ia_alimenta_o_contador(monkeypatch):
    import json
    import subprocess
    ui.uso.zerar()
    monkeypatch.setattr(ia.shutil, "which", lambda _: "claude")
    resultado = {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn",
                 "structured_output": {"cortes": []}, "total_cost_usd": 0.02,
                 "usage": {"input_tokens": 1500, "output_tokens": 200}}
    monkeypatch.setattr(ia.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(resultado), ""))
    ia.chamar_ia("oi", ia.SCHEMA, "m")
    assert (ui.uso.chamadas, ui.uso.entrada, ui.uso.saida, ui.uso.rodando) == (1, 1500, 200, 0)
    assert ui.uso.custo == 0.02


def test_falha_do_claude_conta_como_falha(monkeypatch):
    ui.uso.zerar()
    monkeypatch.setattr(ia.shutil, "which", lambda _: None)
    try:
        ia.chamar_ia("oi", ia.SCHEMA, "m")
    except RuntimeError:
        pass
    # sem o claude instalado o erro vem antes de comecar a chamada: nada fica "rodando"
    assert ui.uso.rodando == 0


def test_resumo_e_tabela_nao_quebram_com_colchetes_e_emoji(capsys):
    ui.iniciar(1)
    with ui.etapa("Render"):
        pass
    c = Corte(5, 50, "[BUG] fugi da policia 🚓", nota=8.5)
    ui.tabela_visao([(Corte(10, 40, nota=7), c, True, False)])
    ui.resumo([c], "saida/x")
    out = capsys.readouterr().out
    assert "[BUG] fugi da policia" in out and "pronto!" in out
