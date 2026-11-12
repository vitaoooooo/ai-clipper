import json
import subprocess

import pytest

from clipador.selecao import ia


def _fake_run(saida_result: dict, capturado: dict):
    def run(cmd, **kw):
        capturado["cmd"] = cmd
        capturado["kw"] = kw
        linhas = [json.dumps({"type": "system", "subtype": "init"}), json.dumps(saida_result)]
        return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(linhas), stderr="")
    return run


def test_chamar_ia_usa_claude_code_sem_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-nao-deve-vazar")
    monkeypatch.setattr(ia.shutil, "which", lambda _: "claude")
    cap = {}
    resultado = {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn",
                 "structured_output": {"cortes": []}, "modelUsage": {"claude-sonnet-5-5": {}},
                 "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 3}}
    monkeypatch.setattr(ia.subprocess, "run", _fake_run(resultado, cap))

    dados, info = ia.chamar_ia("oi", ia.SCHEMA, "claude-sonnet-5-5")

    assert dados == {"cortes": []}
    assert info == {"modelo": "claude-sonnet-5-5", "uso": {"entrada": 15, "saida": 3}}
    assert "ANTHROPIC_API_KEY" not in cap["kw"]["env"]
    assert "--json-schema" in cap["cmd"] and "-p" in cap["cmd"]
    i = cap["cmd"].index("--setting-sources")                 # abre limpo, sem precisar de opcao
    assert cap["cmd"][i + 1] == "" and "--strict-mcp-config" in cap["cmd"]
    assert "--disable-slash-commands" in cap["cmd"]
    msg = json.loads(cap["kw"]["input"])
    assert msg["message"]["content"] == [{"type": "text", "text": "oi"}]


def test_chamar_ia_erro_do_claude_code(monkeypatch):
    monkeypatch.setattr(ia.shutil, "which", lambda _: "claude")
    resultado = {"type": "result", "subtype": "error_during_execution", "is_error": True,
                 "result": "limite atingido"}
    monkeypatch.setattr(ia.subprocess, "run", _fake_run(resultado, {}))
    with pytest.raises(RuntimeError, match="limite atingido"):
        ia.chamar_ia("oi", ia.SCHEMA, "claude-sonnet-5-5")


def test_chamar_ia_sem_claude_instalado(monkeypatch):
    monkeypatch.setattr(ia.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Claude Code nao encontrado"):
        ia.chamar_ia("oi", ia.SCHEMA, "claude-sonnet-5-5")
