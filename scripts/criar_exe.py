"""Gera o Clipador.exe (lancador da interface) na raiz do projeto. So Windows.

Uso (na raiz do projeto, com o .venv ja instalado):  python scripts\\criar_exe.py

O .exe e pequeno: so abre o `.venv\\Scripts\\clipador-ui.exe` sem janela de terminal.
Nao empacota o Python nem o Whisper (isso daria varios GB). Por isso ele precisa do projeto
instalado nesta maquina. Compila com o csc.exe do .NET Framework, que ja vem no Windows.
O Clipador.exe fica fora do git (.gitignore): rode este script de novo em cada PC.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTE = RAIZ / "scripts" / "Clipador.cs"
ICONE = RAIZ / "src" / "clipador" / "app" / "static" / "icone.ico"
SAIDA = RAIZ / "Clipador.exe"


def achar_csc() -> Path:
    base = Path(r"C:\Windows\Microsoft.NET")
    for pasta in ("Framework64", "Framework"):
        candidatos = sorted((base / pasta).glob("v4*/csc.exe"), reverse=True)
        if candidatos:
            return candidatos[0]
    sys.exit("csc.exe nao encontrado (vem com o .NET Framework 4 do Windows).")


def main():
    if sys.platform != "win32":
        sys.exit("o Clipador.exe e so para Windows")
    if not (RAIZ / ".venv" / "Scripts" / "clipador-ui.exe").exists():
        sys.exit("instale antes: .venv\\Scripts\\activate e pip install -r requirements.txt")
    codigo = FONTE.read_text(encoding="utf-8").replace("__RAIZ__", str(RAIZ))
    with tempfile.TemporaryDirectory() as tmp:
        cs = Path(tmp) / "Clipador.cs"
        cs.write_text(codigo, encoding="utf-8")
        cmd = [str(achar_csc()), "/nologo", "/target:winexe", "/optimize+", f"/out:{SAIDA}",
               "/reference:System.Windows.Forms.dll", str(cs)]
        if ICONE.exists():
            cmd.insert(3, f"/win32icon:{ICONE}")
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        sys.exit(f"falhou ao compilar:\n{r.stdout}\n{r.stderr}")
    print(f"pronto: {SAIDA}")


if __name__ == "__main__":
    main()
