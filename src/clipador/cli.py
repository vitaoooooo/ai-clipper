"""Linha de comando. As opcoes que nao forem passadas vem da config (ou do padrao)."""
import argparse
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
    p.add_argument("--modelo", default=None, help="Modelo do Claude (padrao claude-sonnet-5-5)")
    p.add_argument("--sem-ia", action="store_true", default=None,
                   help="Nao usa a API; corta pelos picos de audio")
    p.add_argument("--saida", default=None, help="Pasta onde tudo e salvo (padrao saida)")
    return p


def main(argv=None):
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
