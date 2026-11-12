# 🎬 AI Clipper (Clipador)

Transforma VODs e lives longas (YouTube, Twitch ou arquivo local) em **cortes verticais 9:16 prontos
para o TikTok**: a IA escolhe os melhores momentos, monta o layout vertical, queima legendas animadas
e escreve o texto do post.

Feito com foco em conteúdo de **GTA 6**, mas funciona com qualquer gameplay ou live.

## ✨ Como funciona

```
vídeo ──► transcrição (Whisper) ──► sinais (áudio, movimento, chat)
      ──► 1ª passada: Claude lê a fala e pré-seleciona candidatos
      ──► 2ª passada: Claude vê os prints da tela, dá a nota e corrige início/fim
      ──► render 1080x1920 com legendas ──► posts.txt (legenda, hashtags, crédito)
```

- **Escolha em duas passadas:** primeiro pela fala, depois olhando as imagens. Assim o corte começa no
  contexto e termina depois do desfecho.
- **Ação sem fala também vira corte:** os picos de movimento na tela entram como candidatos.
- **Cortes que não interrompem frases:** os limites se encaixam no fim das falas.
- **3 layouts:** `blur` (vídeo inteiro com fundo desfocado), `crop` (tela cheia) e `facecam`
  (câmera em cima, gameplay embaixo).
- **Sem custo de API:** a IA roda pelo [Claude Code](https://claude.com/claude-code) usando a cota do
  plano do claude.ai. O Whisper roda local (com GPU NVIDIA, se houver).

## 🚀 Instalação

Requisitos: Python 3.10+, [ffmpeg](https://ffmpeg.org) no PATH e o Claude Code logado (`claude`).

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt # inclui CUDA para o Whisper; sem NVIDIA use: pip install -e .
```

## 🎯 Uso

```bash
clipador "https://youtube.com/watch?v=XXXX" --credito "@criador"
clipador video.mp4 --cortes 8 --modo crop
clipador "<link>" --min 61 --max 90      # cortes com mais de 1 min (Creator Rewards)
clipador "<link>" --sem-ia               # sem IA: corta nos picos de áudio
```

| Opção | O que faz |
|---|---|
| `--cortes N` | quantos cortes gerar (padrão 5) |
| `--min` / `--max` | duração dos cortes em segundos (padrão 20 a 60) |
| `--modo blur\|crop\|facecam` | layout vertical (`--facecam x,y,w,h` em frações do vídeo) |
| `--canal nome` | usa um preset do `config.toml` (veja `config.example.toml`) |
| `--chat` | usa os picos do chat da live como sinal (opcional) |
| `--sem-visao` | pula a 2ª passada (gasta menos cota) |
| `--whisper small` / `--idioma en` | modelo e idioma da transcrição |

O resultado fica em `saida/<video>/cortes/`: os `corte_XX.mp4` e o `posts.txt` com a legenda,
as hashtags e o motivo de cada escolha.

## 🧪 Testes

```bash
pip install -e .[dev]
pytest
```

## 🗺️ Roteiro

- [x] Cortes com IA em duas passadas, legendas e layouts
- [x] Sinais de áudio, movimento na tela e chat
- [ ] Histórico, vários links de uma vez e fila de posts
- [ ] Envio ao TikTok como rascunho pela Content Posting API oficial

> Use só vídeos que você tem autorização para cortar e guarde a autorização do criador.
