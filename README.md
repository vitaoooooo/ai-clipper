# Clipador

Transforma um video longo (link do YouTube/Twitch ou arquivo) em cortes verticais pro TikTok,
com os momentos escolhidos por IA, legenda animada e credito do criador.

## Instalar (uma vez)
1. Python 3.10+ (python.org)
2. ffmpeg: `winget install ffmpeg` (feche e abra o terminal depois)
3. Na pasta do clipador:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Chave da API do Claude (console.anthropic.com, cobrado por uso):
   - Windows: `setx ANTHROPIC_API_KEY "sua-chave"` e abra um terminal novo

## Usar
    clipador "https://youtube.com/watch?v=XXXX" --credito "@nomedocriador"

(`python clipador.py ...` continua funcionando, mesmo sem instalar.)

Opcoes uteis:
- `--cortes 8`          quantos cortes gerar (padrao 5)
- `--min 15 --max 45`   duracao dos cortes em segundos
- `--modo crop`         preenche a tela cortando as laterais (padrao: blur, video inteiro com fundo desfocado)
- `--modo facecam --facecam 0,0,0.25,0.3`  facecam em cima e gameplay embaixo; a regiao da facecam
                        e dada em fracao do video: x, y, largura, altura
- `--whisper small`     transcricao mais rapida (padrao medium; large-v3 e mais preciso e mais lento)
- `--idioma en`         se o video for em ingles
- `--sem-ia`            nao usa a API: corta nos maiores picos de audio (gratis, menos inteligente)
- Tambem aceita arquivo: `clipador video.mp4 --credito "@canal"`

## Config por canal
Copie `config.example.toml` para `config.toml` e crie um preset por streamer:

    clipador "<link>" --canal exemplo

Prioridade: `[padrao]` < `[canais.<nome>]` < opcoes da linha de comando.

## Saida
Fica em `saida/<titulo-do-video>/`:
- `cortes/corte_01.mp4`, `corte_02.mp4`... prontos pra postar
- `cortes/posts.txt` (e `posts.json`) com legenda, hashtags e o motivo de cada escolha
- `transcricao.json` e `picos_audio.json`: cache, rodar de novo no mesmo video e bem mais rapido
- `resposta_ia.json`: o que a IA respondeu e quantos tokens gastou

## Estrutura do codigo
```
src/clipador/
  cli.py, config.py, pipeline.py, modelos.py, util.py
  fontes/      local, youtube (yt-dlp), twitch
  analise/     transcricao (whisper), audio (picos), chat*, cenas*
  selecao/     ia (Claude), heuristica (sem IA), ajuste (encaixe em frases)
  render/      layouts (blur/crop/facecam), legendas (ASS), ffmpeg
  publicacao/  posts, historico*, tiktok*
```
`*` = primeira versao pronta, ainda nao ligada ao pipeline (fases 1 a 3).

## Testes
    pip install -e .[dev]
    pytest

## Observacoes
- Whisper usa a placa de video (NVIDIA) se der; se der erro de CUDA ele cai pra CPU sozinho.
- Guarde a autorizacao do criador por escrito (print da conversa/e-mail).
- Se o criador preferir, ele pode te mandar o arquivo do video e voce passa o caminho no lugar do link.
