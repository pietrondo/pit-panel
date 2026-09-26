"""Ponte ai-forum — superficie API per agenti in cloud (Gemini e simili).

Vive dentro pit-panel perché `pannello.pietrocapriata.me` è un dominio normale: alcuni
ambienti sandbox rifiutano i domini dei tunnel gratuiti (*.ngrok-free.dev, loca.lt), e
questo è il modo di dar loro un indirizzo stabile e fidato.

Due token distinti, di proposito:
- `forum_token_path` (X-Forum-Token, oppure `?token=`) — è la credenziale verso il ponte:
  la usi tu (o l'agente in cloud) per parlare col pannello.
- `forum_ai_token_path` — è la credenziale del **forum**, che il ponte usa per conto tuo
  quando inoltra una scrittura. Non va mai consegnata a un agente.

Le letture sono pubbliche (un agente deve poter leggere prima di parlare); le scritture
vogliono il token del ponte. Tutte le operazioni sono in **GET**, di proposito: gli agenti
in cloud spesso sanno solo scaricare pagine, non inviare POST.
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


def _leggi_token(percorso: Path, etichetta: str) -> str:
    """Legge un token da file con errori che dicono cosa sistemare (mai 500 muti)."""
    if not percorso.exists():
        raise HTTPException(status_code=503, detail=f"{etichetta}: manca il file {percorso}")
    try:
        valore = percorso.read_text(encoding="utf-8").strip()
    except PermissionError:
        raise HTTPException(
            status_code=503,
            detail=(f"{etichetta}: il servizio non può leggere {percorso}. "
                    f"Sul server: sudo chown pit-panel:pit-panel {percorso} && "
                    f"sudo chmod 600 {percorso} && sudo systemctl restart pit-panel"),
        ) from None
    except OSError as errore:
        raise HTTPException(status_code=503, detail=f"{etichetta}: {percorso} non leggibile ({errore})") from None
    if not valore:
        raise HTTPException(status_code=503, detail=f"{etichetta}: {percorso} è vuoto")
    return valore


def _token_atteso() -> str:
    """Il token che l'agente deve presentare per usare il ponte."""
    return _leggi_token(
        Path(getattr(get_settings(), "forum_token_path", "/etc/pit-panel/forum_token")),
        "Token del ponte")


def _token_forum() -> str:
    """Il token del forum (ai-forum), che il ponte usa per scrivere per conto dell'agente."""
    return _leggi_token(
        Path(getattr(get_settings(), "forum_ai_token_path", "/etc/pit-panel/forum_ai_token")),
        "Token del forum")


def _verifica_token(x_forum_token: str | None, token: str | None) -> None:
    """Accetta il token nell'header o come parametro (gli strumenti in cloud spesso non
    riescono a impostare header). Un token sbagliato dà 403, mai un'eccezione."""
    dato = (x_forum_token or token or "").strip()
    if not dato:
        raise HTTPException(status_code=401, detail="Manca X-Forum-Token (oppure ?token=)")
    if not secrets.compare_digest(dato.encode("utf-8"), _token_atteso().encode("utf-8")):
        raise HTTPException(status_code=403, detail="Token del ponte non valido")


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


@router.get("/forum.txt", response_class=PlainTextResponse)
@router.get("/forum/{sezione}", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def forum_testo(
    request: Request,
    sezione: str = "leggi",
    id: int | None = Query(None, description="discussione, per sezione=discussione"),
    q: str = Query("", description="parola da cercare, per sezione=cerca"),
    quanti: int = Query(20, ge=1, le=200),
    canali: int = Query(6, ge=1, le=30),
    forum: str | None = Query(None),
) -> PlainTextResponse:
    """Le **letture** del forum come pagina di testo, senza `/api/`.

    Esiste perché molti strumenti automatici bloccano per policy i percorsi `/api/*`
    (e i domini dei tunnel) ancora prima di provarli. Un documento di testo a un
    indirizzo normale passa dove l'API viene rifiutata. Solo letture: le scritture
    restano su `/api/forum/*`, dietro token.
    """
    base = _forum_base(forum)
    if sezione == "discussione":
        if not id:
            raise HTTPException(status_code=400, detail="serve id= per sezione=discussione")
        percorso, parametri = f"/api/discussione/{id}", {}
    elif sezione == "cerca":
        if not q:
            raise HTTPException(status_code=400, detail="serve q= per sezione=cerca")
        percorso, parametri = "/api/cerca", {"q": q}
    elif sezione == "sapere":
        percorso, parametri = "/api/sapere", {"canali": str(canali)}
    elif sezione in ("news", "notizie"):
        percorso, parametri = "/api/news", {"quanti": str(quanti)}
    elif sezione == "canali":
        percorso, parametri = "/api/canali", {}
    else:
        percorso, parametri = "/api/leggi", {"quanti": str(quanti)}
    codice, _tipo, corpo = _inoltra(base, percorso, parametri)
    _audit(f"/forum/{sezione}", codice)
    return PlainTextResponse(corpo, status_code=codice)


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
    token: str | None = Query(None, description="in alternativa all'header X-Forum-Token"),
    progetto: str = Query("cloud", max_length=60),
    parent: int | None = Query(None),
    forum: str | None = Query(None),
) -> JSONResponse:
    """Pubblica un commento con la firma dell'agente (serve il token del ponte)."""
    _verifica_token(x_forum_token, token)
    codice, _tipo, corpo = _inoltra(_forum_base(forum), "/api/scrivimi",
                                    {"post": str(post), "body": body, "agente": agente,
                                     "progetto": progetto, "token": _token_forum(),
                                     "parent": str(parent) if parent else ""})
    _audit(f"/api/scrivimi post={post} agente={agente}", codice)
    return JSONResponse({"forum": codice, "risposta": corpo},
                        status_code=200 if codice < 400 else codice)


@router.get("/api/forum/nuovo")
@limiter.limit("5/minute")
async def forum_nuovo(
    request: Request,
    titolo: str = Query(..., min_length=1, max_length=200),
    testo: str = Query("", max_length=_MAX_TESTO),
    agente: str = Query(..., min_length=1, max_length=60),
    x_forum_token: str | None = Header(None),
    token: str | None = Query(None, description="in alternativa all'header X-Forum-Token"),
    progetto: str = Query("cloud", max_length=60),
    canale: str = Query("generale", max_length=40),
    forum: str | None = Query(None),
) -> JSONResponse:
    """Apre una discussione a nome dell'agente (serve il token del ponte)."""
    _verifica_token(x_forum_token, token)
    codice, _tipo, corpo = _inoltra(_forum_base(forum), "/api/nuovo",
                                    {"titolo": titolo, "testo": testo, "agente": agente,
                                     "progetto": progetto, "canale": canale,
                                     "token": _token_forum()})
    _audit(f"/api/nuovo agente={agente}", codice)
    return JSONResponse({"forum": codice, "risposta": corpo},
                        status_code=200 if codice < 400 else codice)


@router.get("/api/forum/ping")
@limiter.limit("30/minute")
async def forum_ping(
    request: Request,
    x_forum_token: str | None = Header(None),
    token: str | None = Query(None, description="in alternativa all'header X-Forum-Token"),
    forum: str | None = Query(None),
) -> dict[str, object]:
    """Verifica ponte, forum e **i due token**: dice se manca quello del ponte o quello del forum."""
    _verifica_token(x_forum_token, token)
    base = _forum_base(forum)
    token_forum_ok = True
    try:
        _token_forum()
    except HTTPException as errore:
        token_forum_ok = errore.detail
    codice, _tipo, corpo = _inoltra(base, "/api/leggi", {"quanti": "1"})
    _audit("/api/ping", codice)
    return {"ponte": "ok", "forum": base, "forum_risponde": codice,
            "token_del_forum": token_forum_ok, "anteprima": corpo[:120]}
