"""Titulo e credito do corte como uma imagem PNG transparente (1080x1920) sobreposta ao video.

Estilo "A" (escolhido em 12/11/2026, mockup no Paper): caixa branca arredondada com o titulo em
Montserrat ExtraBold preto e a palavra-chave em rosa TikTok; acima, uma pilula escura com o icone
da plataforma (Twitch/YouTube) e o credito em Inter Bold. Fica o video inteiro.

Por que imagem e nao legenda .ass: o libass (ffmpeg) nao faz canto arredondado nem emoji colorido.
O Pillow desenha o emoji com a fonte colorida do sistema (Segoe UI Emoji no Windows).
Tudo e desenhado em 2x e reduzido no fim, para as bordas ficarem suaves.
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from clipador.modelos import Credito
from clipador.render.layouts import ALTURA, LARGURA

FONTES = Path(__file__).parent / "fontes"
ESCALA = 2                       # desenha em 2x e reduz (antialias)

ROSA = (254, 44, 85)             # #FE2C55
TINTA = (17, 17, 17)             # #111111
BRANCO = (255, 255, 255)

# medidas em pixels do video final (1080x1920), o dobro do mockup de 540x960
TOPO_CREDITO = 124
TOPO_TITULO = 224
MARGEM_LADO = 72
TAM_TITULO = 58
ALTURA_LINHA = 70
PAD_X, PAD_Y = 36, 25
RAIO_CAIXA = 28
TAM_CREDITO = 30

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]+")
FONTES_EMOJI = [Path("C:/Windows/Fonts/seguiemj.ttf"),
                Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
                Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")]


def _fonte(arquivo: str, tamanho: float, peso: str) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTES / arquivo), round(tamanho * ESCALA))
    f.set_variation_by_name(peso)
    return f


def _fonte_emoji(tamanho: float) -> ImageFont.FreeTypeFont | None:
    for caminho in FONTES_EMOJI:
        if caminho.exists():
            try:
                return ImageFont.truetype(str(caminho), round(tamanho * ESCALA))
            except OSError:
                continue
    return None


def _s(v: float) -> int:
    return round(v * ESCALA)


# ------------------------------------------------------------------ titulo

def _pedacos(palavra: str) -> list[tuple[str, bool]]:
    """Separa emoji de texto dentro de uma palavra: [(texto, eh_emoji), ...]."""
    saida, pos = [], 0
    for m in EMOJI.finditer(palavra):
        if m.start() > pos:
            saida.append((palavra[pos:m.start()], False))
        saida.append((m.group(), True))
        pos = m.end()
    if pos < len(palavra):
        saida.append((palavra[pos:], False))
    return saida


def palavra_chave(palavras: list[str]) -> int:
    """Indice da palavra pintada de rosa: a ultima com letras (o desfecho costuma estar no fim)."""
    for i in range(len(palavras) - 1, -1, -1):
        if re.search(r"\w", EMOJI.sub("", palavras[i])):
            return i
    return -1


def _quebrar_linhas(palavras: list[str], larguras: list[float], espaco: float, maximo: float) -> list[list[int]]:
    linhas, atual, larg = [], [], 0.0
    for i, w in enumerate(larguras):
        extra = w if not atual else espaco + w
        if atual and larg + extra > maximo:
            linhas.append(atual)
            atual, larg = [i], w
        else:
            atual.append(i)
            larg += extra
    if atual:
        linhas.append(atual)
    return linhas


def _desenhar_titulo(img: Image.Image, titulo: str):
    fonte = _fonte("Montserrat.ttf", TAM_TITULO, "ExtraBold")
    emoji = _fonte_emoji(TAM_TITULO * 0.82)
    palavras = titulo.split()
    if emoji is None:   # sem fonte de emoji: tira o emoji em vez de desenhar um quadrado
        palavras = [p for p in (EMOJI.sub("", w) for w in palavras) if p]
    if not palavras:
        return

    def largura(p: str) -> float:
        return sum((emoji if eh else fonte).getlength(t) for t, eh in _pedacos(p))

    larguras = [largura(p) for p in palavras]
    espaco = fonte.getlength(" ")
    maximo = _s(LARGURA - 2 * MARGEM_LADO - 2 * PAD_X)
    linhas = _quebrar_linhas(palavras, larguras, espaco, maximo)
    larg_linhas = [sum(larguras[i] for i in ln) + espaco * (len(ln) - 1) for ln in linhas]
    chave = palavra_chave(palavras)

    caixa_w = max(larg_linhas) + _s(2 * PAD_X)
    caixa_h = _s(ALTURA_LINHA) * len(linhas) + _s(2 * PAD_Y) - _s(ALTURA_LINHA - TAM_TITULO * 1.22)
    x0 = (img.width - caixa_w) / 2
    y0 = _s(TOPO_TITULO)
    caixa = (x0, y0, x0 + caixa_w, y0 + caixa_h)

    # sombra suave embaixo da caixa (0 12px 40px, 28% de preto)
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((caixa[0], caixa[1] + _s(12), caixa[2], caixa[3] + _s(12)),
                                             radius=_s(RAIO_CAIXA), fill=(0, 0, 0, 72))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(_s(20))))

    d = ImageDraw.Draw(img)
    d.rounded_rectangle(caixa, radius=_s(RAIO_CAIXA), fill=BRANCO)
    base = y0 + _s(PAD_Y) + fonte.getmetrics()[0]   # linha de base da 1a linha
    for ln, larg in zip(linhas, larg_linhas):
        x = (img.width - larg) / 2
        for k, i in enumerate(ln):
            if k:
                x += espaco
            cor = ROSA if i == chave else TINTA
            for texto, eh_emoji in _pedacos(palavras[i]):
                if eh_emoji:
                    d.text((x, base), texto, font=emoji, anchor="ls", embedded_color=True)
                    x += emoji.getlength(texto)
                else:
                    d.text((x, base), texto, font=fonte, anchor="ls", fill=cor)
                    x += fonte.getlength(texto)
        base += _s(ALTURA_LINHA)


# ------------------------------------------------------------------ credito

def _icone_twitch(d: ImageDraw.ImageDraw, x: float, y: float, alt: float):
    """Logo da Twitch (balao roxo com os dois tracos), desenhado num quadro de 24x28."""
    k = alt / 28

    def pts(*p):
        return [(x + a * k, y + b * k) for a, b in p]

    roxo = (145, 70, 255)
    d.polygon(pts((3, 0), (0, 5), (0, 25), (7, 25), (7, 28), (11, 28), (14, 25), (19, 25), (24, 20), (24, 0)),
              fill=roxo)
    d.polygon(pts((4, 2), (22, 2), (22, 15), (18, 19), (12, 19), (9, 22), (9, 19), (4, 19)), fill=BRANCO)
    d.rectangle(pts((11, 6), (13.4, 13)), fill=roxo)
    d.rectangle(pts((16.5, 6), (18.9, 13)), fill=roxo)
    return 24 * k


def _icone_youtube(d: ImageDraw.ImageDraw, x: float, y: float, alt: float):
    """Logo do YouTube (retangulo vermelho arredondado com o play branco), quadro de 28x20."""
    k = alt / 20
    d.rounded_rectangle((x, y, x + 28 * k, y + 20 * k), radius=6 * k, fill=(255, 0, 0))
    d.polygon([(x + 11 * k, y + 5.5 * k), (x + 11 * k, y + 14.5 * k), (x + 19 * k, y + 10 * k)], fill=BRANCO)
    return 28 * k


def _desenhar_credito(img: Image.Image, credito: Credito):
    fonte = _fonte("Inter.ttf", TAM_CREDITO, "Bold")
    alt_icone = {"twitch": _s(36), "youtube": _s(26)}.get(credito.plataforma or "", 0)
    larg_icone = {"twitch": alt_icone * 24 / 28, "youtube": alt_icone * 28 / 20}.get(credito.plataforma or "", 0)
    gap = _s(14) if alt_icone else 0
    pad_esq = _s(16) if alt_icone else _s(26)
    larg_texto = fonte.getlength(credito.texto)
    w = pad_esq + larg_icone + gap + larg_texto + _s(26)
    h = _s(60)
    x0, y0 = (img.width - w) / 2, _s(TOPO_CREDITO)

    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=h / 2, fill=(0, 0, 0, 140))
    x = x0 + pad_esq
    if credito.plataforma == "twitch":
        _icone_twitch(d, x, y0 + (h - alt_icone) / 2, alt_icone)
    elif credito.plataforma == "youtube":
        _icone_youtube(d, x, y0 + (h - alt_icone) / 2, alt_icone)
    d.text((x + larg_icone + gap, y0 + h / 2), credito.texto, font=fonte, anchor="lm", fill=BRANCO)
    img.alpha_composite(camada)


# ------------------------------------------------------------------ imagem final

def gerar_capa(caminho: Path, titulo: str, credito: Credito | None) -> Path:
    """Grava o PNG transparente de 1080x1920 com o credito e o titulo."""
    img = Image.new("RGBA", (LARGURA * ESCALA, ALTURA * ESCALA), (0, 0, 0, 0))
    if credito is not None and credito.texto:
        _desenhar_credito(img, credito)
    if titulo and titulo.strip():
        _desenhar_titulo(img, titulo.strip())
    img.resize((LARGURA, ALTURA), Image.Resampling.LANCZOS).save(caminho)
    return caminho


if __name__ == "__main__":   # previa: python -m clipador.render.capa "Titulo" twitch mount saida.png
    t, plat, user, saida = sys.argv[1:5]
    from clipador.publicacao.credito import texto_do_credito
    gerar_capa(Path(saida), t, Credito(plat or None, user, texto_do_credito(plat or None, user)))
