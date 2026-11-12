# Clipador

Ferramenta de linha de comando que transforma um video longo (VOD/live do YouTube ou Twitch, ou arquivo
local) em cortes verticais 9:16 para TikTok: escolhe os melhores trechos com IA (Claude), monta o layout
vertical, queima legendas animadas e gera o texto do post (legenda, hashtags e credito).

O foco e conteudo de **GTA 6** (lancamento previsto para 19/11/2026). O objetivo e postar no TikTok para  
gerar receita: campanhas de clipes pagas por view.

O usuario fala portugues (Brasil). Responda em portugues.

## Comandos

```
.venv\Scripts\activate            # ambiente virtual (Windows)
pip install -e .[dev]             # instala o pacote + pytest
pytest                            # testes (os de render precisam de ffmpeg no PATH)
clipador "<link ou arquivo>" --credito "@canal"   # ou: python clipador.py ...
clipador "<link>" --canal <nome>  # usa o preset [canais.<nome>] do config.toml
clipador "<link>" --sem-visao     # so a 1a passada (escolhe pela transcricao, sem olhar os prints)
clipador "<link>" --candidatos 15 # quantos trechos a 1a passada pre-seleciona para a 2a (padrao 12)
clipador "<link>" --sem-ia        # sem IA (corta pelos picos de audio)
```

Dependencias externas: `ffmpeg`/`ffprobe` no PATH e o Claude Code (`claude`) no PATH, logado com a conta do
claude.ai (so quando nao for `--sem-ia`). Nao ha chamada direta a API nem `ANTHROPIC_API_KEY`.
O Whisper roda local (faster-whisper): usa a GPU NVIDIA se puder, senao cai para a CPU.

## Fluxo (src/clipador/pipeline.py)

1. `fontes/`: obtem o video. Arquivo local, Twitch ou qualquer outro link (yt-dlp). Salva em `saida/<slug>/original.mp4`
2. `analise/transcricao.py`: Whisper com tempo por palavra. Cache em `transcricao.json`
3. Sinais (cada um so entra no prompt se existir):
   - `analise/audio.py`: picos de volume. Cache em `picos_audio.json`.
   - `analise/cenas.py`: movimento na tela por segundo. O ffmpeg decodifica so os keyframes
     (`-skip_frame nokey`), em quadros de 64x36 em cinza, e o numpy faz a diferenca entre segundos.
     Cache em `atividade_visual.json`; 8h de live levam ~3 min. `picos_visuais` soma janelas de 10s,
     zera tela preta/loading e devolve janelas com mais de 1,5x a mediana. Ligado por padrao (`cenas`,
     `--sem-cenas`); nao roda com `--sem-ia`.
   - `analise/chat.py`: picos de chat, **opcional e desligado por padrao** (`--chat` ou `--chat-arquivo`;
     escolha do usuario). YouTube via yt-dlp (so lives passadas), Twitch via `TwitchDownloaderCLI` no PATH.
     Qualquer falha so imprime um aviso e segue sem chat: o chat nunca derruba a execucao.
4. Escolha em duas passadas (ou `selecao/heuristica.py` com `--sem-ia`):
   - 1a: `selecao/ia.py` escolhe `candidatos` (padrao 12) pela transcricao + sinais; `ajuste.py` os encaixa,
     tira repetidos e fica com os de maior nota. Video com mais de ~1h15 e dividido em blocos de 1h
     (`BLOCO_SEG`, com `SOBREPOSICAO_SEG` = 90s), um pedido por bloco (`PARALELO_BLOCOS` = 2), e cada bloco
     pede a sua parte proporcional + 1. Nesse caso cada bloco fica em cache em `ia_blocos/`: se algum falhar,
     rodar de novo refaz so ele. A pasta e apagada quando todos dao certo, entao a proxima execucao pede
     escolhas novas. `resposta_ia.json` = `{modelo, uso, blocos: [...]}`.
   - Candidatos visuais (`heuristica.candidatos_visuais`): ate `candidatos_visuais` (padrao 4) picos de
     movimento que **nao** se sobrepoem aos candidatos da fala viram candidatos extras, comecando 25% antes
     do pico. Motivo: acao sem fala nunca vira candidato na 1a passada, e a 2a e quem filtra menu/troca de cena.
   - A 1a passada devolve tambem `climax` (segundo do momento principal) e `contexto` (o que o espectador
     precisa saber), que vao para o `Corte` e para o prompt da 2a passada.
   - 2a: `selecao/visao.py` tira prints 1/s de cada candidato **com `MARGEM_ANTES` = 40s antes e
     `MARGEM_DEPOIS` = 20s depois** (o problema mais comum era faltar contexto no comeco)
     (`analise/frames.py`, JPEG de 480px, cache em `frames/<ini>-<fim>/`, marcas `t=` em tempo absoluto do
     video) e roda um `claude -p` por candidato (imagens + transcricao + sinais da janela). A IA devolve a
     nota **e o inicio/fim corrigidos**, porque a 1a passada nao ve a tela e erra os limites (feedback real:
     cortou antes de a briga acabar, faltou contexto no comeco). Os limites sao presos a janela vista e
     depois passam por `ajustar_cortes` (encaixe, min/max, sobreposicao: a maior nota ganha). Um pedido por candidato
     por causa do limite de imagens por pedido (`MAX_FRAMES`); `PARALELO` deles ao mesmo tempo. Candidato
     que falhar fica com nota <= 5 e nao derruba os outros. `--sem-visao` pula a 2a (`visao = false`).
     Se o contexto comeca antes da janela vista, a IA marca `falta_contexto` (vai para o
     `resposta_visao.json` e imprime um aviso; ainda nao muda nada no corte).
5. `selecao/ajuste.py`: so mexe num limite que cai **dentro de uma fala** (`encaixar_inicio`/`encaixar_fim`,
   tolerancia de 0.5s). Limite em silencio fica onde esta, porque pode ter vindo da imagem (fim da briga).
   E **idempotente**: roda depois da 1a e da 2a passada, e ajustar duas vezes da o mesmo resultado
   (testado em 15 mil casos aleatorios; arredonda para 2 casas ANTES de decidir). Abaixo de `dmin`,
   estica ate o **primeiro fim de frase** depois de `dmin`. Acima de `dmax`, recua ate o **ultimo fim de
   frase** antes de `dmax`; se nao houver, ate a ultima palavra com pontuacao e, por ultimo, ate o fim de
   qualquer palavra. Nunca corta no meio da fala, se houver alternativa. Cortes de mais de 1 min para o
   Creator Rewards: `--min 61 --max 90` (preset `[canais.rewards]` no exemplo); o padrao continua 20-60.
6. `render/`: `legendas.py` gera o `.ass`, `layouts.py` monta o filtro (blur | crop | facecam), `ffmpeg.py` renderiza
7. `publicacao/posts.py`: grava `cortes/posts.json` e `cortes/posts.txt`

## Estrutura

- `cli.py`: argparse. Toda opcao tem `default=None`, para so sobrescrever a config quando for passada.
- `config.py`: dataclass `Config`. Prioridade: padrao < `config.toml [padrao]` < `[canais.X]` < CLI.
  O `config.toml` e lido automaticamente se existir no diretorio atual. Ele fica fora do git; o modelo e o `config.example.toml`.
- `modelos.py`: `Video` e `Corte` sao dataclasses. Segmentos e palavras continuam `TypedDict` (dict) para
  manter compativel o cache `transcricao.json`. Nao converta para dataclass sem migrar o cache.
- Modulos que ja existem mas **ainda nao estao ligados ao pipeline**:
  `publicacao/historico.py` (SQLite) e `publicacao/tiktok.py` (so um esboco).

## Convencoes e armadilhas

- O codigo e as mensagens sao em portugues, **sem acentos** nas strings e nos identificadores. Mantenha o padrao.
- Python >= 3.10 (`X | None`, `list[str]`). O PC do usuario roda 3.14, no Windows.
- O ffmpeg roda com `cwd=pasta_cortes` e recebe so o **nome** do `.ass` no filtro `subtitles`, porque
  caminhos do Windows (`C:\...`) quebram o filtro. Nao troque por caminho absoluto.
- Resolucao fixa de 1080x1920 (`render/layouts.py`). As posicoes das legendas no `.ass` dependem dela.
- `selecao/ia.py`: a IA e **exclusivamente o Claude Code** (`claude -p`), para consumir a cota do plano
  do usuario e nao pagar API. Nao volte a usar o SDK `anthropic`. `chamar_ia` manda o conteudo (texto e
  imagens base64) por stdin em `--input-format stream-json`, pede `--json-schema` e le `structured_output`
  do evento `result`. Remove `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` do ambiente (senao cobra por API),
  roda com `cwd` fora do projeto (nao carregar este CLAUDE.md), `--tools ""` e `--system-prompt` =
  `GUIA_CLIPAGEM` (o criterio de bom corte: mini-historia contexto -> escalada -> climax -> desfecho,
  o que funciona em GTA, escala de nota, regras dos textos). O guia e compartilhado pelas duas passadas;
  os prompts de cada passada (`ia.PROMPT`, `visao.PROMPT`) so descrevem a tarefa, em tags XML.
  Sempre abre "limpo" (`ISOLAMENTO`: `--setting-sources ""`, `--strict-mcp-config`,
  `--disable-slash-commands`), sem settings, CLAUDE.md, MCP e skills do usuario. Medido: ~9.000 -> ~1.100
  tokens de entrada por chamada, e o login do plano continua valendo. Isso e fixo no codigo, nao e opcao da CLI.
  Nao use `--bare` (ele so aceita API key). Sempre verifique `is_error`/`subtype` e `stop_reason`.
  O modelo padrao e `claude-sonnet-5-5` (escolha do usuario).
  - `chamar_ia(conteudo, schema, modelo)` devolve `(dados, info)`, com
    `info = {"modelo": ..., "uso": {"entrada": ..., "saida": ...}}` (dict, nao o objeto de resposta do SDK).
    Nao tem `max_tokens`. E esse `info` que vai para `resposta_ia.json` e `resposta_visao.json`.
  - O plano tem limite de uso por janela de tempo. A 2a passada (`visao.py`, ate `MAX_FRAMES` imagens por
    candidato, `PARALELO` processos do `claude` ao mesmo tempo) e o que mais gasta cota. Limite estourado
    vira `RuntimeError`; a saida e esperar ou usar `--sem-visao`/`--sem-ia`.
  - Os testes nunca chamam o Claude de verdade: trocam `subprocess.run`/`shutil.which` em `ia.py`
    (`tests/test_ia_claude_code.py`) ou o `chamar_ia` em `visao.py` (`tests/test_visao.py`) via monkeypatch.
- A IA costuma por emoji no titulo e na legenda. O console do Windows (cp1252) quebrava no `print` desses
  textos; `cli._console_utf8()` reconfigura stdout/stderr para UTF-8 no inicio do `main`. Os arquivos sao
  gravados sempre em UTF-8.
- 2a passada: se TODOS os candidatos falharem, `escolher_com_visao` levanta `RuntimeError` (nada e
  renderizado); se so alguns falharem, imprime um aviso e eles ficam com nota <= 5.
- Whisper: o audio e decodificado pelo ffmpeg (`transcricao.carregar_audio`) e passado como array ao
  faster-whisper, porque o PyAV 19+ quebrou a decodificacao interna dele (`metadata_errors`). Nao volte a
  passar o caminho do arquivo. GPU (RTX 2060 do usuario): as DLLs do CUDA vem do extra `gpu`
  (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) e `_registrar_dlls_cuda()` as poe no caminho de busca do Windows.
  Sem elas, cai para a CPU, que e muito mais lenta.
- Antes de mexer em `ajuste.py`, `legendas.py` ou `layouts.py`, rode `pytest`. Os testes de render
  geram um video sintetico e confirmam 1080x1920 nos tres modos.
- Nao automatize postagem no TikTok via navegador (risco de banir a conta). O plano e usar a Content Posting API oficial, enviando como rascunho.

## Roteiro

- **Fase 0 (feita):** separar o script em modulos sem mudar o comportamento, structured output, modo facecam, config por canal, testes.
- **Feito (12/11/2026):** a IA passou da API paga (SDK `anthropic`) para o Claude Code com a cota do plano;
  o `anthropic` saiu das dependencias.
- **Feito (12/11/2026):** escolha em duas passadas (transcricao -> candidatos; prints + transcricao -> nota
  final). Opcoes `candidatos` e `visao` na config (`--candidatos`, `--sem-visao`).
- **Fase 1 (feita em 12/11/2026):** chat como sinal opcional (`--chat`); movimento na tela como sinal
  e como fonte de candidatos visuais para a 2a passada; sinais do trecho no prompt da visao; `ajuste.py`
  termina em fim de frase; suporte a cortes de 61 a 90s. Ainda falta validar numa live real de GTA.
- **Feito (12/11/2026):** a 2a passada corrige inicio/fim olhando a tela; `ajuste.py` idempotente;
  prompts reescritos com o `GUIA_CLIPAGEM` como prompt de sistema, `climax`/`contexto` da 1a passada,
  margem de 40s antes e `falta_contexto`. Ideia: refazer o candidato com janela maior quando `falta_contexto`.
- **Fase 2:** ligar o `historico.py`, processar varios links de uma vez, fila de posts com horarios.
- **Fase 3:** envio ao TikTok como rascunho (`tiktok.py`) e metricas de desempenho dos cortes.

## Notas do projeto (Obsidian)

O vault do Obsidian do projeto fica em `C:\obsidian\Projeto Clipador` (liberado como diretorio extra em
`.claude/settings.local.json`). Divisao: este CLAUDE.md e a fonte da verdade **tecnica**; o vault guarda
planejamento, decisoes, historico e ideias. As notas do vault sao escritas em portugues **com** acentos
(a regra de "sem acentos" vale so para o codigo).

- `Clipador.md`: nota inicial, com links para as outras
- `Roteiro.md`: fases com checkboxes (`- [ ]` / `- [x]`)
- `Decisoes.md` (o arquivo se chama `Decisões.md`): decisoes com data, motivo e consequencia; a mais nova em cima
- `Log.md`: diario com data (DD/MM/AAAA); a entrada mais nova em cima
- `Ideias.md`: caixa de entrada do usuario. Leia, mas so mexa se ele pedir

Como usar:
- No inicio de uma tarefa grande, leia `Roteiro.md` e `Decisões.md` para ter o contexto.
- Ao terminar uma tarefa que mudou o comportamento, adicione uma entrada no `Log.md` e marque o item no `Roteiro.md`.
- Decisao de arquitetura ou de produto nova: registre no `Decisões.md` (e, se for armadilha tecnica, aqui tambem).
- Use links do Obsidian (`[[Roteiro]]`, `[[Decisões]]`) entre as notas. Nao apague notas do vault sem pedir.
- O vault nao afeta o pipeline: o `claude -p` de `selecao/ia.py` roda isolado e nao le nada disso.
