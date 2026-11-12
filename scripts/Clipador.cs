// Lancador do Clipador para Windows: abre a interface (clipador-ui) sem janela de terminal.
// Gerado por scripts/criar_exe.py, que troca __RAIZ__ pela pasta do projeto.
// Procura o projeto (pasta com .venv) primeiro ao lado do .exe e depois em __RAIZ__,
// entao o Clipador.exe pode ser copiado para a area de trabalho.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Clipador
{
    const string RAIZ_DO_BUILD = @"__RAIZ__";

    static string AcharRaiz()
    {
        string[] candidatas = { AppDomain.CurrentDomain.BaseDirectory, RAIZ_DO_BUILD };
        foreach (string pasta in candidatas)
        {
            if (File.Exists(Path.Combine(pasta, ".venv", "Scripts", "clipador-ui.exe")))
                return pasta;
        }
        return null;
    }

    [STAThread]
    static void Main(string[] args)
    {
        string raiz = AcharRaiz();
        if (raiz == null)
        {
            MessageBox.Show("Nao achei o projeto do Clipador (a pasta com .venv).\n\n" +
                            "Rode scripts\\criar_exe.py de novo dentro do projeto, ou deixe o " +
                            "Clipador.exe na pasta do projeto.", "Clipador",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        var info = new ProcessStartInfo
        {
            FileName = Path.Combine(raiz, ".venv", "Scripts", "clipador-ui.exe"),
            Arguments = string.Join(" ", args),
            WorkingDirectory = raiz,      // o config.toml e a saida/ ficam aqui
            UseShellExecute = false,
            CreateNoWindow = true,        // sem janela preta de terminal
        };
        try
        {
            Process.Start(info);
        }
        catch (Exception e)
        {
            MessageBox.Show("Nao consegui abrir o Clipador:\n\n" + e.Message, "Clipador",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
