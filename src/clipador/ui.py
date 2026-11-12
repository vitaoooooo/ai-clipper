"""Visual do terminal (rich): banner, etapas, barras de progresso, contador de tokens do Claude e resumo.

Tudo que aparece na tela passa por aqui. As mensagens sao montadas com Text (nunca com markup),
para que titulos com colchetes, vindos do video ou da IA, nao virem tags do rich.
"""
import threading
import time
from contextlib import contextmanager

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, ProgressColumn, SpinnerColumn, TaskProgressColumn,
                           TextColumn, TimeElapsedColumn, TimeRemainingColumn)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from clipador.util import fmt

ROSA = "#fe2c55"     # as duas cores do TikTok
CIANO = "#25f4ee"

TEMA = Theme({"rosa": ROSA, "ciano": CIANO, "ok": "bold green", "aviso": "yellow", "erro": "bold red",
              "fraco": "grey58", "tok": f"bold {CIANO}"})
console = Console(theme=TEMA, highlight=False)


# ---------------------------------------------------------------- tokens do Claude (tempo real)

class UsoClaude:
    """Soma o uso de todas as chamadas ao Claude Code. Thread-safe: a 2a passada roda em paralelo."""

    def __init__(self):
        self._trava = threading.Lock()
        self.zerar()

    def zerar(self):
        self.entrada = self.saida = self.chamadas = self.falhas = self.rodando = 0
        self.custo = 0.0

    def comecou(self):
        with self._trava:
            self.rodando += 1

    def terminou(self, entrada: int = 0, saida: int = 0, custo: float = 0.0, ok: bool = True):
        with self._trava:
            self.rodando -= 1
            self.chamadas += 1
            self.falhas += not ok
            self.entrada += entrada
            self.saida += saida
            self.custo += custo

    def texto(self) -> Text:
        t = Text.assemble(("Claude ", "fraco"), ("entrada ", "fraco"), (_k(self.entrada), "tok"),
                          ("  saida ", "fraco"), (_k(self.saida), "tok"))
        if self.rodando:
            t.append(f"  {self.rodando} rodando", style="aviso")
        return t


uso = UsoClaude()


def _k(n: float) -> str:
    """12345 -> '12,3k' (virgula, como no Brasil)."""
    if n < 1000:
        return str(int(n))
    if n < 1_000_000:
        return f"{n / 1000:.1f}k".replace(".", ",")
    return f"{n / 1_000_000:.2f}M".replace(".", ",")


def _dur(seg: float) -> str:
    return f"{seg:.1f}s".replace(".", ",") if seg < 60 else fmt(seg)


# ---------------------------------------------------------------- mensagens soltas

def info(msg: str, destaque: str = ""):
    console.print(Text.assemble("  ", (msg, ""), (f" {destaque}" if destaque else "", "bold")), soft_wrap=True)


def ok(msg: str):
    console.print(Text.assemble(("  ✓ ", "ok"), msg), soft_wrap=True)


def detalhe(msg: str):
    console.print(Text("    " + msg, style="fraco"), soft_wrap=True)


def aviso(msg: str):
    console.print(Text.assemble(("  ! ", "aviso"), (msg, "aviso")), soft_wrap=True)


def erro(titulo: str, msg: str):
    console.print()
    console.print(Panel(Text(msg), title=Text(titulo, style="erro"), border_style="red",
                        box=box.ROUNDED, padding=(1, 2)))


# ---------------------------------------------------------------- banner

_LETRAS = {
    "C": [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
    "L": ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    "P": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔═══╝ ", "██║     ", "╚═╝     "],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "D": ["██████╗ ", "██╔══██╗", "██║  ██║", "██║  ██║", "██████╔╝", "╚═════╝ "],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
}


def _degrade(i: int, total: int) -> str:
    """Cor da coluna i num degrade do rosa ao ciano."""
    a, b = (int(ROSA[k:k + 2], 16) for k in (1, 3, 5)), (int(CIANO[k:k + 2], 16) for k in (1, 3, 5))
    f = i / max(total - 1, 1)
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b))


def _logo() -> Text:
    linhas = ["".join(_LETRAS[c][i] for c in "CLIPADOR") for i in range(6)]
    largura = len(linhas[0])
    t = Text()
    for linha in linhas:
        for i, ch in enumerate(linha):
            t.append(ch, style=_degrade(i, largura) if ch == "█" else "grey35")
        t.append("\n")
    return t


def banner(fonte: str, cfg, versao: str):
    console.print()
    if console.width >= 66:
        console.print(_logo(), end="")
    else:
        console.print(Text("CLIPADOR", style=f"bold {ROSA}"))
    console.print(Text.assemble(("  cortes verticais com IA para TikTok", "fraco"), ("  ·  ", "grey35"),
                                (f"v{versao}", "fraco")))
    console.print()

    t = Table.grid(padding=(0, 2))
    t.add_column(style="fraco", justify="right")
    t.add_column()
    t.add_row("fonte", Text(fonte, style="bold"))
    t.add_row("cortes", f"{cfg.cortes} de {cfg.dmin} a {cfg.dmax}s  ·  layout {cfg.modo}")
    if cfg.sem_ia:
        ia = Text("desligada (picos de audio)", style="aviso")
    else:
        ia = Text.assemble((cfg.modelo, "ciano"), ("  ·  ", "grey35"),
                           ("2 passadas (fala + imagem)" if cfg.visao else "so a fala", ""))
    if cfg.reprisar_ia and not cfg.sem_ia:
        ia.append("  ·  reprise (sem gastar cota)", style="aviso")
    t.add_row("IA", ia)
    sinais = ["audio"] + (["movimento"] if cfg.cenas and not cfg.sem_ia else []) \
        + (["chat"] if (cfg.chat or cfg.chat_arquivo) and not cfg.sem_ia else [])
    t.add_row("sinais", " + ".join(sinais))
    t.add_row("whisper", cfg.whisper)
    if cfg.credito:
        t.add_row("credito", cfg.credito)
    console.print(Panel(t, border_style="grey35", box=box.ROUNDED, padding=(0, 1), expand=False))


# ---------------------------------------------------------------- etapas

class _Execucao:
    total = 0
    atual = 0
    inicio = 0.0
    tempos: list[tuple[str, float]] = []


def iniciar(total_etapas: int):
    _Execucao.total, _Execucao.atual = total_etapas, 0
    _Execucao.inicio = time.monotonic()
    _Execucao.tempos = []
    uso.zerar()


@contextmanager
def etapa(titulo: str):
    """Cabecalho '2/6  Transcricao' e, no fim, quanto tempo a etapa levou."""
    _Execucao.atual += 1
    console.print()
    console.rule(Text.assemble((f" {_Execucao.atual}/{_Execucao.total} ", f"bold black on {ROSA}"),
                               (f" {titulo} ", "bold")), align="left", style="grey35")
    t0 = time.monotonic()
    yield
    dt = time.monotonic() - t0
    _Execucao.tempos.append((titulo, dt))
    console.print(Text(f"  {titulo} em {_dur(dt)}", style="fraco"))


# ---------------------------------------------------------------- barras de progresso

class _ColunaClaude(ProgressColumn):
    """Tokens do Claude somados ate agora; redesenha ~10x por segundo, entao atualiza sozinha."""

    def render(self, task):
        return uso.texto()


class _ColunaTempo(ProgressColumn):
    """'12:34 / 1:02:00' para barras medidas em segundos de video."""

    def render(self, task):
        return Text(f"{fmt(task.completed)} / {fmt(task.total or 0)}", style="ciano")


class _ColunaContagem(ProgressColumn):
    def render(self, task):
        return Text(f"{int(task.completed)}/{int(task.total or 0)}", style="ciano")


class _ColunaBytes(ProgressColumn):
    def render(self, task):
        mb = lambda b: f"{b / 1e6:.0f} MB" if b < 1e9 else f"{b / 1e9:.2f} GB".replace(".", ",")
        return Text(f"{mb(task.completed)} / {mb(task.total or 0)}", style="ciano")


class Barra:
    def __init__(self, progresso: Progress, tarefa):
        self._p, self._t = progresso, tarefa

    def avancar(self, n: float = 1, descricao: str | None = None):
        self._p.update(self._t, advance=n, **({"description": descricao} if descricao else {}))

    def ate(self, valor: float, total: float | None = None, descricao: str | None = None):
        extra = {"description": descricao} if descricao else {}
        if total is not None:
            extra["total"] = total
        self._p.update(self._t, completed=valor, **extra)


@contextmanager
def barra(descricao: str, total: float, unidade: str = "itens", claude: bool = False):
    """Barra de progresso que some no fim. unidade: itens | tempo (segundos de video) | bytes.

    claude=True mostra os tokens do Claude ao lado, atualizando enquanto as chamadas terminam.
    """
    colunas = [SpinnerColumn("dots", style="rosa"), TextColumn("{task.description}"),
               BarColumn(bar_width=28, style="grey23", complete_style="rosa", finished_style="ciano"),
               TaskProgressColumn(style="bold"),
               {"tempo": _ColunaTempo(), "bytes": _ColunaBytes()}.get(unidade, _ColunaContagem()),
               TimeElapsedColumn()]
    if unidade in ("tempo", "bytes"):
        colunas.append(TimeRemainingColumn())
    if claude:
        colunas.append(_ColunaClaude())
    with Progress(*colunas, console=console, transient=True, refresh_per_second=10) as p:
        yield Barra(p, p.add_task(f"  {descricao}", total=total))


# ---------------------------------------------------------------- tabelas

def tabela_visao(linhas: list):
    """Resultado da 2a passada: (candidato_antes, candidato_depois, avaliado, falta_contexto)."""
    tab = Table(box=box.SIMPLE_HEAD, header_style="bold", border_style="grey35", pad_edge=False)
    tab.add_column("candidato", style="fraco", no_wrap=True)
    tab.add_column("nota", justify="right", no_wrap=True)
    tab.add_column("limites corrigidos", style="ciano", no_wrap=True)
    tab.add_column("", overflow="fold")
    for antes, depois, avaliado, falta in sorted(linhas, key=lambda l: -l[1].nota):
        nota = Text.assemble((f"{antes.nota:g} → ", "fraco"), (f"{depois.nota:g}", f"bold {_cor_nota(depois.nota)}"))
        mudou = (depois.inicio, depois.fim) != (antes.inicio, antes.fim)
        limites = f"{fmt(depois.inicio)} → {fmt(depois.fim)}" if mudou else Text("igual", style="fraco")
        obs = Text("falhou (sem imagem)", style="erro") if not avaliado else \
            Text("falta contexto antes da janela", style="aviso") if falta else Text(depois.titulo or "")
        tab.add_row(f"{fmt(antes.inicio)} → {fmt(antes.fim)}", nota, limites, obs)
    console.print(tab)


# ---------------------------------------------------------------- resumo final

def _cor_nota(nota: float) -> str:
    return "ok" if nota >= 8 else "aviso" if nota >= 6 else "erro"


def resumo(cortes: list, pasta, com_nota: bool = True):
    console.print()
    tab = Table(box=box.SIMPLE_HEAD, header_style="bold", border_style="grey35", pad_edge=False,
                title=Text("cortes prontos", style=f"bold {ROSA}"), title_justify="left")
    tab.add_column("#", style="fraco", justify="right")
    tab.add_column("trecho", style="ciano", no_wrap=True)
    tab.add_column("dur.", justify="right")
    if com_nota:     # sem IA a "nota" e o volume do pico em dB, nao uma nota de 0 a 10
        tab.add_column("nota", justify="right")
    tab.add_column("titulo", overflow="fold")
    for i, c in enumerate(cortes, 1):
        nota = [Text(f"{c.nota:g}", style=_cor_nota(c.nota))] if com_nota else []
        tab.add_row(f"{i:02d}", f"{fmt(c.inicio)} → {fmt(c.fim)}", f"{c.duracao:.0f}s", *nota,
                    Text(c.titulo or ""))
    console.print(tab)

    # tempo de cada etapa num mini grafico de barras
    total = time.monotonic() - _Execucao.inicio
    maior = max((dt for _, dt in _Execucao.tempos), default=1) or 1
    graf = Table.grid(padding=(0, 1))
    graf.add_column(style="fraco", justify="right")
    graf.add_column()
    graf.add_column(justify="right", style="fraco")
    for titulo, dt in _Execucao.tempos:
        n = max(1, round(24 * dt / maior))
        graf.add_row(titulo, Text("".join("█" for _ in range(n)), style=_degrade(n, 25)), _dur(dt))

    linhas = [Text.assemble(("tempo total  ", "fraco"), (_dur(total), "bold"))]
    if uso.chamadas:
        t = Text.assemble(("Claude       ", "fraco"), (f"{uso.chamadas} chamadas", "bold"),
                          ("  ·  entrada ", "fraco"), (_k(uso.entrada), "tok"),
                          ("  ·  saida ", "fraco"), (_k(uso.saida), "tok"))
        if uso.falhas:
            t.append(f"  ·  {uso.falhas} falharam", style="aviso")
        linhas.append(t)
        if uso.custo:
            linhas.append(Text(f"             equivale a ~US$ {uso.custo:.2f} na API; aqui sai da cota do plano"
                               .replace(".", ",", 1), style="fraco"))
    linhas += [Text.assemble(("pasta        ", "fraco"), (str(pasta), "bold"))]
    console.print(Panel(Group(graf, Text(""), *linhas), title=Text("pronto!", style="ok"),
                        title_align="left", border_style="ciano", box=box.ROUNDED, padding=(1, 2),
                        expand=False))
