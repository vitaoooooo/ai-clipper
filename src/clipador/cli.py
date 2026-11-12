"""Linha de comando. As opcoes que nao forem passadas vem da config (ou do padrao)."""
import argparse
import sys
from pathlib import Path

from clipador import config, pipeline
from clipador.config import MODOS, parse_facecam


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clipador",
                                description="Gera cortes de TikTok a partir de um video longo, com IA.")
    p.add_argument("fonte", help="Link do YouTube/Twitch ou caminho de um arquivo de video")
    p.add_argument("--config", type=Path, help="Arquivo de config (padrao: ./config.toml se existir)")
    p.add_argument("--canal", help="Preset de [canais.<nome>] da config")
    # default=None em tudo: so sobrescreve a config quando o usuario passa a opcao
    p.add_argument("--credito", default=None, help='Texto de credito no topo, ex: "@canal"')
    p.add_argument("--cortes", type=int, default=None, help="Quantos cortes gerar (padrao 5)")
    p.add_argument("--min", type=int, default=None, dest="dmin", help="Duracao minima em segundos (padrao 20)")
    p.add_argument("--max", type=int, default=None, dest="dmax", help="Duracao maxima em segundos (padrao 60)")
    p.add_argument("--modo", choices=MODOS, default=None,
                   help="blur = video inteiro com fundo desfocado (padrao); crop = corta o centro; "
                        "facecam = facecam em cima e gameplay embaixo")
    p.add_argument("--facecam", type=parse_facecam, default=None,
                   help="Regiao da facecam em fracao do video: x,y,largura,altura (ex: 0,0,0.25,0.3)")
    p.add_argument("--whisper", default=None, help="Modelo do Whisper: small, medium (padrao), large-v3")
    p.add_argument("--idioma", default=None, help="Idioma do video (pt, en...). Vazio = detectar")
    p.add_argument("--modelo", default=None, help="Modelo do Claude usado pelo Claude Code (padrao claude-sonnet-5-5)")
    p.add_argument("--sem-ia", action="store_true", default=None,
                   help="Nao usa IA; corta pelos picos de audio")
    p.add_argument("--candidatos", type=int, default=None,
                   help="Quantos trechos a 1a passada (so transcricao) pre-seleciona para a IA "
                        "olhar as imagens (padrao 12)")
    p.add_argument("--sem-visao", action="store_false", default=None, dest="visao",
                   help="Pula a 2a passada (prints do video); escolhe so pela transcricao")
    p.add_argument("--chat", action="store_true", default=None,
                   help="Usa o chat da live como sinal (YouTube: baixa sozinho; Twitch: precisa do "
                        "TwitchDownloaderCLI no PATH). Desligado por padrao")
    p.add_argument("--chat-arquivo", default=None,
                   help="Arquivo de chat ja baixado (live_chat.json do YouTube ou JSON do TwitchDownloader); "
                        "liga o chat")
    p.add_argument("--sem-cenas", action="store_false", default=None, dest="cenas",
                   help="Nao mede o movimento na tela (sinal visual e candidatos visuais)")
    p.add_argument("--candidatos-visuais", type=int, default=None,
                   help="Trechos de muito movimento na tela (sem fala) que vao direto para a 2a passada "
                        "(padrao 4; 0 desliga)")
    p.add_argument("--saida", default=None, help="Pasta onde tudo e salvo (padrao saida)")
    return p


def _console_utf8():
    """O console do Windows (cp1252) quebra no print de emoji que a IA poe nos titulos."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # fluxo substituido (ex: pytest) ou ja fechado
            pass


def main(argv=None):
    _console_utf8()
    parser = criar_parser()
    a = parser.parse_args(argv)
    sobrescritas = {k: v for k, v in vars(a).items() if k not in ("fonte", "config", "canal")}
    try:
        cfg = config.carregar(a.config, a.canal, sobrescritas)
    except (ValueError, OSError) as e:
        parser.error(str(e))
    pipeline.executar(a.fonte, cfg)


if __name__ == "__main__":
    main()
