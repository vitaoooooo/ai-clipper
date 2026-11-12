"""Envio ao TikTok (FASE 3 - nao implementado).

Plano:
- Usar a Content Posting API oficial (developers.tiktok.com), enviando como RASCUNHO
  (o video aparece no app do TikTok e voce so revisa e publica).
- Apps sem auditoria do TikTok so conseguem postar como privado (SELF_ONLY).
- Precisa de login OAuth da conta (client_key, client_secret, token de acesso).
- NAO usar automacao de navegador: risco de banir a conta.

Ate la: poste manualmente usando os arquivos de saida/<video>/cortes/ e o posts.txt.
"""
from pathlib import Path


def enviar_rascunho(video: Path, legenda: str) -> str:
    """Envia o video como rascunho e retorna o id da publicacao."""
    raise NotImplementedError("Envio ao TikTok e da fase 3. Por enquanto, poste manualmente.")
