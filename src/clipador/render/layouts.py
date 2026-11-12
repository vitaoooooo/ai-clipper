"""Filtros do ffmpeg que montam a tela vertical 9:16.

- blur:    video inteiro no meio, com o proprio video desfocado de fundo
- crop:    corta o centro e preenche a tela (perde as laterais)
- facecam: facecam em cima (40% da tela) e gameplay embaixo (60%) - formato de clipe de live
"""
LARGURA, ALTURA = 1080, 1920
ALTURA_CAM = 768  # 40% de 1920


def montar_filtro(modo: str, legenda: str,
                  facecam: tuple[float, float, float, float] | None = None, capa: bool = False) -> str:
    """`legenda` e o nome do arquivo .ass (relativo a pasta onde o ffmpeg roda).

    capa=True poe por cima a 2a entrada do ffmpeg ([1:v], o PNG do titulo e do credito).
    """
    filtro = _filtro_base(modo, legenda, facecam)
    if capa:   # a imagem parada continua na tela ate o fim (eof_action=repeat e o padrao do overlay)
        filtro = filtro[:-len("[v]")] + "[base];[base][1:v]overlay=0:0[v]"
    return filtro


def _filtro_base(modo: str, legenda: str, facecam: tuple[float, float, float, float] | None) -> str:
    if modo == "crop":
        return f"[0:v]scale=-2:{ALTURA},crop={LARGURA}:{ALTURA},subtitles={legenda}[v]"

    if modo == "blur":
        return (f"[0:v]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
                f"crop={LARGURA}:{ALTURA},boxblur=25:2[bg];"
                f"[0:v]scale={LARGURA}:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles={legenda}[v]")

    if modo == "facecam":
        if facecam is None:
            raise ValueError("modo facecam precisa da regiao da facecam")
        x, y, w, h = facecam
        alt_jogo = ALTURA - ALTURA_CAM
        return (f"[0:v]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},"
                f"scale={LARGURA}:{ALTURA_CAM}:force_original_aspect_ratio=increase,"
                f"crop={LARGURA}:{ALTURA_CAM}[cam];"
                f"[0:v]scale={LARGURA}:{alt_jogo}:force_original_aspect_ratio=increase,"
                f"crop={LARGURA}:{alt_jogo}[jogo];"
                f"[cam][jogo]vstack,subtitles={legenda}[v]")

    raise ValueError(f"modo desconhecido: {modo}")
