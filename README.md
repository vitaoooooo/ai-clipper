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
4. Claude Code (a IA usa a cota do seu plano do claude.ai, sem pagar API):
   - instale pelo site claude.com/claude-code e rode `claude` uma vez para logar com a conta do claude.ai
   - nao precisa de `ANTHROPIC_API_KEY`; se ela existir, o clipador ignora

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
- `--candidatos 15`    quantos trechos a 1a passada (so transcricao) pre-seleciona (padrao 12)
- `--sem-visao`        pula a 2a passada, em que a IA olha os prints (1 por segundo) dos candidatos
- `--sem-ia`            nao usa IA: corta nos maiores picos de audio (nao gasta cota, menos inteligente)
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
- `resposta_ia.json`: o que a IA respondeu na 1a passada (so transcricao) e quantos tokens gastou.
  Lives longas sao divididas em blocos de ~1h; se algum bloco falhar (ex: limite do plano), rode o
  mesmo comando de novo e so os blocos que faltaram serao refeitos (ficam em `ia_blocos/` ate terminar)
- `resposta_visao.json`: nota de cada candidato na 2a passada (com imagem) e tokens gastos
- `frames/`: prints dos candidatos (cache; pode apagar)

## Estrutura do codigo
```
src/clipador/
  cli.py, config.py, pipeline.py, modelos.py, util.py
  fontes/      local, youtube (yt-dlp), twitch
  analise/     transcricao (whisper), audio (picos), chat*, cenas*
  selecao/     ia (Claude via Claude Code), heuristica (sem IA), ajuste (encaixe em frases)
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
