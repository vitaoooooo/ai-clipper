"""Interface grafica do Clipador: servidor local (Starlette) + pagina no navegador/janela (pywebview).

- estado.py: fila de videos e o progresso de cada um, montado a partir dos eventos do ui.py
- gerente.py: roda um video por vez num processo filho (da para parar matando o processo)
- presets.py: le e grava os canais do config.toml sem perder os comentarios (tomlkit)
- estimativa.py: quantas chamadas ao Claude uma execucao vai fazer
- midia.py: dados de um link/arquivo (titulo, duracao) e prints para marcar a facecam
- biblioteca.py: videos ja processados (saida/) e o historico de postados
- servidor.py: as rotas HTTP e o SSE
- lancador.py: comando `clipador-ui` (sobe o servidor em segundo plano e abre a janela)
"""
