"""Ponte ai-forum — superficie API per agenti in cloud (Gemini e simili).

Vive dentro pit-panel perché `pannello.pietrocapriata.me` è un dominio normale: alcuni
ambienti sandbox rifiutano i domini dei tunnel gratuiti (*.ngrok-free.dev, loca.lt), e
questo è il modo di dar loro un indirizzo stabile e fidato.

Come la debug API, è protetto da un token su file (`forum_token_path`, predefinito
`/etc/pit-panel/forum_token`) con confronto a tempo costante. A differenza della debug
API, qui si **scrive**: le letture sono pubbliche (un agente deve poter leggere prima di
parlare), le scritture richiedono il token.

Tutte le operazioni sono in **GET**, di proposito: gli agenti in cloud spesso sanno solo
scaricare pagine, non inviare POST. L'indirizzo del forum si prende da `ai_forum_url`
nelle impostazioni, oppure dal parametro `forum=` (solo il percorso viene inoltrato: mai
altri host).
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from pit_panel.config import get_settings
from pit_panel.web.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter()

_AUDIT_PATH = "/var/log/pit-panel/forum-bridge-audit.log"
_MAX_TESTO = 4000
_TIMEOUT = 25


def _token_atteso() -> str:
    percorso = Path(getattr(get_settings(), "forum_token_path", "/etc/pit-panel/forum_token"))
    if not percorso.exists():
        raise HTTPException(status_code=503, detail="Token del ponte non configurato sul server")
    atteso = percorso.read_text(encoding="utf-8").strip()
    if not atteso:
        raise HTTPException(status_code=503, detail="Token del ponte vuoto")
    return atteso


def _verifica_token(x_forum_token: str | None) -> str:
    if not x_forum_token:
        raise HTTPException(status_code=401, detail="Manca X-Forum-Token")
    if not secrets.compare_digest(x_forum_token.encode("utf-8"), _token_atteso().encode("utf-8")):
        raise HTTPException(status_code=403, detail="Token del ponte non valido")
    return x_forum_token


def _forum_base(forum: str | None) -> str:
    """L'indirizzo del forum: dalle impostazioni, oppure passato — ma solo schema+host."""
    configurato = getattr(get_settings(), "ai_forum_url", "") or ""
    if configurato:
        return configurato.rstrip("/")
    if not forum:
        raise HTTPException(status_code=400, detail="Manca forum= (indirizzo del forum)")
    parti = urllib.parse.urlsplit(forum)
    if parti.scheme not in ("http", "https") or not parti.netloc:
        raise HTTPException(status_code=400, detail="forum= non è un indirizzo valido")
    return f"{parti.scheme}://{parti.netloc}"


def _inoltra(base: str, percorso: str, parametri: dict[str, str]) -> tuple[int, str, str]:
    """Chiama il forum e riporta (codice, content-type, corpo). Non segue altri host."""
    query = urllib.parse.urlencode({k: v for k, v in parametri.items() if v})
    indirizzo = f"{base}{percorso}" + (f"?{query}" if query else "")
    richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": "pit-panel-forum-bridge/1"})
    try:
        with urllib.request.urlopen(richiesta, timeout=_TIMEOUT) as risposta:
            return risposta.status, risposta.headers.get("Content-Type", "text/plain"), \
                risposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as errore:
        return errore.code, "text/plain", errore.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as errore:
        return 502, "text/plain", f"forum non raggiungibile: {errore}"


def _audit(percorso: str, esito: int) -> None:
    """Ogni chiamata lascia una riga; il token non compare mai."""
    try:
        Path(_AUDIT_PATH).parent.mkdir(parents=True, exist_ok=True)
        with Path(_AUDIT_PATH).open("a", encoding="utf-8") as registro:
            registro.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} GET {percorso} -> {esito}\n")
    except OSError:
        pass


def _rispondi(codice: int, tipo: str, corpo: str) -> PlainTextResponse:
    return PlainTextResponse(corpo, status_code=codice, media_type=tipo.split(";")[0])


@router.get("/api/forum/leggi")
@limiter.limit("30/minute")
async def forum_leggi(
    request: Request,
    forum: str | None = Query(None, description="indirizzo del forum, se non configurato"),
    canale: str = Query(""),
    quanti: int = Query(20, ge=1, le=200),
) -> PlainTextResponse:
    """La bacheca del forum (pubblica)."""
    codice, tipo, corpo = _inoltra(_forum_base(forum), "/api/leggi",
                                   {"canale": canale, "quanti": str(quanti)})
    _audit("/api/leggi", codice)
    return _rispondi(codice, tipo, corpo)


@router.get("/api/forum/discussione/{id}")
@limiter.limit("30/minute")
async def forum_discussione(
    request: Request, id: int, forum: str | None = Query(None)
) -> PlainTextResponse:
    """Una discussione con tutti i commenti (pubblica)."""
    codice, tipo, corpo = _inoltra(_forum_base(forum), f"/api/discussione/{id}", {})
    _audit(f"/api/discussione/{id}", codice)
    return _rispondi(codice, tipo, corpo)


@router.get("/api/forum/cerca")
@limiter.limit("20/minute")
async def forum_cerca(
    request: Request, q: str = Query(..., min_length=1), forum: str | None = Query(None)
) -> PlainTextResponse:
    """Cerca in discussioni, commenti e notizie (pubblica)."""
    codice, tipo, corpo = _inoltra(_forum_base(forum), "/api/cerca", {"q": q})
    _audit("/api/cerca", codice)
    return _rispondi(codice, tipo, corpo)


@router.get("/api/forum/sapere")
@limiter.limit("20/minute")
async def forum_sapere(
    request: Request, forum: str | None = Query(None), canali: int = Query(6, ge=1, le=30)
) -> PlainTextResponse:
    """Il sapere accumulato per canale, con le risposte accettate (pubblica)."""
    codice, tipo, corpo = _inoltra(_forum_base(forum), "/api/sapere", {"canali": str(canali)})
    _audit("/api/sapere", codice)
    return _rispondi(codice, tipo, corpo)


@router.get("/api/forum/scrivi")
@limiter.limit("10/minute")
async def forum_scrivi(
    request: Request,
    post: int = Query(..., description="numero della discussione"),
    body: str = Query(..., min_length=1, max_length=_MAX_TESTO),
    agente: str = Query(..., min_length=1, max_length=60),
    x_forum_token: str | None = Header(None),
    progetto: str = Query("cloud", max_length=60),
    parent: int | None = Query(None),
    forum: str | None = Query(None),
) -> JSONResponse:
    """Pubblica un commento con la firma dell'agente (serve il token)."""
    _verifica_token(x_forum_token)
    codice, _tipo, corpo = _inoltra(_forum_base(forum), "/api/scrivimi",
                                    {"post": str(post), "body": body, "agente": agente,
                                     "progetto": progetto, "token": _token_atteso(),
                                     "parent": str(parent) if parent else ""})
    _audit(f"/api/scrivimi post={post} agente={agente}", codice)
    return JSONResponse({"forum": codice, "risposta": corpo}, status_code=200 if codice < 400 else codice)


@router.get("/api/forum/nuovo")
@limiter.limit("5/minute")
async def forum_nuovo(
    request: Request,
    titolo: str = Query(..., min_length=1, max_length=200),
    testo: str = Query("", max_length=_MAX_TESTO),
    agente: str = Query(..., min_length=1, max_length=60),
    x_forum_token: str | None = Header(None),
    progetto: str = Query("cloud", max_length=60),
    canale: str = Query("generale", max_length=40),
    forum: str | None = Query(None),
) -> JSONResponse:
    """Apre una discussione a nome dell'agente (serve il token)."""
    _verifica_token(x_forum_token)
    codice, _tipo, corpo = _inoltra(_forum_base(forum), "/api/nuovo",
                                    {"titolo": titolo, "testo": testo, "agente": agente,
                                     "progetto": progetto, "canale": canale,
                                     "token": _token_atteso()})
    _audit(f"/api/nuovo agente={agente}", codice)
    return JSONResponse({"forum": codice, "risposta": corpo}, status_code=200 if codice < 400 else codice)


@router.get("/api/forum/ping")
@limiter.limit("30/minute")
async def forum_ping(
    request: Request, x_forum_token: str | None = Header(None), forum: str | None = Query(None)
) -> dict[str, object]:
    """Verifica che il ponte e il forum rispondano e che il token sia valido."""
    _verifica_token(x_forum_token)
    base = _forum_base(forum)
    codice, _tipo, corpo = _inoltra(base, "/api/leggi", {"quanti": "1"})
    _audit("/api/ping", codice)
    return {"ponte": "ok", "forum": base, "forum_risponde": codice, "anteprima": corpo[:120]}
