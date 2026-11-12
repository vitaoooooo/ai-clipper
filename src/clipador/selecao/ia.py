"""Escolha dos cortes pelo Claude, com resposta em JSON garantido pelo schema (structured output)."""
import json
from pathlib import Path

from clipador.modelos import Corte, Pico, Segmento

PROMPT = """Voce e editor de cortes virais para TikTok. Abaixo esta a transcricao de um video do YouTube
chamado "{titulo}", com tempos em segundos, e os momentos em que o audio fica bem mais alto que o normal
(costumam ser reacoes, gritos, explosoes, risadas).

Escolha os {n} melhores trechos para virar cortes independentes de TikTok. Regras:
- Cada corte deve ter entre {dmin} e {dmax} segundos.
- Precisa fazer sentido sozinho, sem contexto do resto do video.
- Comece num gancho forte (algo engracado, chocante, uma pergunta, uma reacao) nos primeiros 2 segundos.
- Termine num ponto natural (fim de frase, desfecho, punchline). Nunca no meio de uma fala.
- Prefira momentos engracados, absurdos, epicos, surpreendentes ou polemicos.
- Os cortes nao podem se sobrepor.

Para cada corte, preencha:
- inicio / fim: em segundos, conforme a transcricao
- titulo: texto curto que aparece no topo do video (max 6 palavras)
- legenda_post: legenda para o post do TikTok
- hashtags: lista de hashtags com # (ex: "#gta6")
- nota: de 0 a 10, quanto potencial viral o trecho tem
- motivo: por que esse trecho funciona

PICOS DE AUDIO (segundo e quantos dB acima da media):
{picos}

TRANSCRICAO:
{transcricao}
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "cortes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "number"},
                    "fim": {"type": "number"},
                    "titulo": {"type": "string"},
                    "legenda_post": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "nota": {"type": "number"},
                    "motivo": {"type": "string"},
                },
                "required": ["inicio", "fim", "titulo", "legenda_post", "hashtags", "nota", "motivo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cortes"],
    "additionalProperties": False,
}

# Se o modelo recusar o pedido por engano (falso positivo de seguranca), a API refaz em outro
# modelo automaticamente. So existe para alguns modelos.
BETA_FALLBACK = "server-side-fallback-2026-07-01"
MODELOS_COM_FALLBACK = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5",
                        "claude-fable-5-1", "claude-fable-5-2"}


def montar_prompt(segs: list[Segmento], picos: list[Pico], titulo: str,
                  n: int, dmin: int, dmax: int) -> str:
    linhas = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segs)
    txt_picos = "\n".join(f"{p['segundo']}s (+{p['acima_da_media_db']} dB)" for p in picos) or "nenhum"
    return PROMPT.format(titulo=titulo, n=n, dmin=dmin, dmax=dmax, picos=txt_picos, transcricao=linhas)


def escolher_com_ia(segs: list[Segmento], picos: list[Pico], titulo: str, n: int,
                    dmin: int, dmax: int, modelo: str, salvar_em: Path | None = None) -> list[Corte]:
    import anthropic

    prompt = montar_prompt(segs, picos, titulo, n, dmin, dmax)
    pedido = dict(
        model=modelo,
        max_tokens=16000,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    print(f"Pedindo pra IA escolher os {n} melhores momentos...")
    cliente = anthropic.Anthropic()
    if modelo in MODELOS_COM_FALLBACK:
        resp = cliente.beta.messages.create(betas=[BETA_FALLBACK], fallbacks="default", **pedido)
    else:
        resp = cliente.messages.create(**pedido)

    if resp.stop_reason == "refusal":
        raise RuntimeError("A IA recusou o pedido. Tente de novo ou use --sem-ia.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("A resposta da IA foi cortada (max_tokens). Peca menos cortes.")

    texto = "".join(b.text for b in resp.content if b.type == "text")
    dados = json.loads(texto)

    if salvar_em is not None:
        registro = {
            "modelo": resp.model,
            "uso": {"entrada": resp.usage.input_tokens, "saida": resp.usage.output_tokens},
            "resposta": dados,
        }
        salvar_em.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")

    return [Corte.de_dict(c) for c in dados["cortes"]]
