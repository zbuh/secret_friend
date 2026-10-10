import hashlib
import hmac
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from decouple import config
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app import db, mailer
from app.draw import DrawError, draw
from app.models import ClaimRequest, EmailRequest, EventRequest, LoginRequest
from app.ratelimit import RateLimit

ACCESS_CODE = config("token", cast=str, default="")
BASE_URL = config("base_url", cast=str, default="").rstrip("/")
HERE = Path(__file__).parent
log = logging.getLogger("uvicorn.error")
# The Docker healthcheck hits /healthz every 30s; keep it out of the access log.
logging.getLogger("uvicorn.access").addFilter(lambda record: "/healthz" not in record.getMessage())

# Per-IP (or per-event) limits; generous for a family, tight for a script.
LIMITS = {
    "login": RateLimit(10, 900),  # password guessing
    "create": RateLimit(30, 3600),
    "claim": RateLimit(20, 600),  # PIN attempts across all names
    "email": RateLimit(5, 3600),  # per event
    "participant": RateLimit(60, 60),
}

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if not ACCESS_CODE:
        log.warning("Sem 'token' definido: a área de gestão fica desligada. Define a password na variável 'token'.")
    yield


app = FastAPI(title="Amigo Secreto", version="2.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
# Cache-busting for /static: changes whenever a static file changes, so Cloudflare/browsers never serve stale JS/CSS.
templates.env.globals["asset_version"] = hashlib.sha256(
    b"".join(f.read_bytes() for f in sorted((HERE / "static").iterdir()))
).hexdigest()[:10]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if not request.url.path.startswith("/static"):
        # Pages carry secret tokens: keep them out of shared/proxy caches and back-button history.
        response.headers["Cache-Control"] = "no-store"
    return response


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


SESSION_COOKIE = "sf_session"


def session_value() -> str:
    # Derived from the password: changing the password logs everyone out.
    return hmac.new(ACCESS_CODE.encode(), b"sf-admin-session-v1", "sha256").hexdigest()


def logged_in(request: Request) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return bool(ACCESS_CODE) and hmac.compare_digest(cookie, session_value())


def require_login(request: Request) -> None:
    if not logged_in(request):
        raise HTTPException(401, "Sessão expirada. Volta à página inicial e entra com a password.")


def base_url(request: Request) -> str:
    return BASE_URL or str(request.base_url).rstrip("/")


def load_admin(admin_token: str):
    event, people = db.get_event_by_admin(admin_token)
    if not event:
        raise HTTPException(404, "Sorteio não encontrado.")
    return event, people


def is_past(event) -> bool:
    """Finished by hand, or the gift exchange day is over."""
    if event["closed_at"]:
        return True
    return bool(event["event_date"]) and date.fromisoformat(event["event_date"]) < date.today()


def require_active(event) -> None:
    if is_past(event):
        raise HTTPException(409, "Este sorteio já terminou.")


def chains(people) -> list[list]:
    """Pairs in gift order: each cycle starts with the first name and follows who gives to whom."""
    by_id = {p["id"]: p for p in people}
    seen, result = set(), []
    for start in people:
        if start["id"] in seen:
            continue
        cycle, current = [], start
        while current and current["id"] not in seen:
            seen.add(current["id"])
            cycle.append(current)
            current = by_id.get(current["target_id"])
        result.append(cycle)
    return result


def not_found(request: Request):
    return templates.TemplateResponse(request, "not_found.html", status_code=404)


# ---------- Pages ----------

@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not logged_in(request):
        return templates.TemplateResponse(request, "login.html", {"configured": bool(ACCESS_CODE)})
    events = db.list_events()
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "upcoming": [e for e in events if not is_past(e)],
            "past": sorted(
                (e for e in events if is_past(e)),
                key=lambda e: e["event_date"] or e["closed_at"][:10],
                reverse=True,
            ),
        },
    )


@app.get("/novo", response_class=HTMLResponse)
async def create_page(request: Request):
    if not logged_in(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "create.html", {"email_enabled": mailer.enabled(), "known": db.known_people()}
    )


@app.get("/e/{admin_token}", response_class=HTMLResponse)
async def admin_page(request: Request, admin_token: str):
    event, people = db.get_event_by_admin(admin_token)
    if not event:
        return not_found(request)
    if is_past(event):
        return templates.TemplateResponse(
            request,
            "memory.html",
            {
                "event": event,
                "people": people,
                "chains": chains(people),
                "can_reopen": not is_past({**dict(event), "closed_at": None}),
                "logged_in": logged_in(request),
            },
        )
    root = base_url(request)
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "event": event,
            "people": people,
            "share_url": f"{root}/s/{event['share_token']}",
            "admin_url": f"{root}/e/{admin_token}",
            "claimed": sum(1 for p in people if p["claimed_at"]),
            "viewed": sum(1 for p in people if p["viewed_at"]),
            "email_enabled": mailer.enabled(),
            "has_emails": any(p["email"] for p in people),
            "logged_in": logged_in(request),
        },
    )


@app.get("/s/{share_token}", response_class=HTMLResponse)
async def share_page(request: Request, share_token: str):
    event, people = db.get_event_by_share(share_token)
    if not event:
        return not_found(request)
    return templates.TemplateResponse(
        request, "share.html", {"event": event, "people": people, "home_url": f"/s/{share_token}"}
    )


@app.get("/p/{token}", response_class=HTMLResponse)
async def participant_page(request: Request, token: str):
    me, event, target = db.get_participant(token)
    if not me:
        return not_found(request)
    return templates.TemplateResponse(
        request,
        "participant.html",
        {"me": me, "event": event, "target": target, "home_url": f"/s/{event['share_token']}"},
    )


# ---------- API ----------

@app.post("/api/login")
async def login(request: Request, body: LoginRequest):
    LIMITS["login"].check(client_ip(request))
    if not ACCESS_CODE:
        raise HTTPException(503, "A password não está configurada no servidor (variável 'token').")
    if not secrets.compare_digest(body.password, ACCESS_CODE):
        raise HTTPException(403, "Password errada.")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        SESSION_COOKIE,
        session_value(),
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@app.post("/api/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/api/events")
async def create_event(request: Request, body: EventRequest):
    require_login(request)
    LIMITS["create"].check(client_ip(request))
    managers = [p for p in body.participants if p.manager]
    if len(managers) != 1:
        raise HTTPException(400, "Marca quem é o gestor 👑 (só pode haver um).")
    if not managers[0].email:
        raise HTTPException(400, "O gestor precisa de email, para receber o link de gestão.")

    names = [p.name.casefold() for p in body.participants]
    if len(set(names)) != len(names):
        raise HTTPException(400, "Há nomes repetidos. Usa nomes diferentes (ex.: «Ana S.» e «Ana M.»).")

    ids = [str(i) for i in range(len(body.participants))]
    groups = {str(i): p.group.casefold() or None for i, p in enumerate(body.participants)}
    try:
        pairs = draw(ids, groups)
    except DrawError as e:
        raise HTTPException(400, str(e))

    admin_token = db.create_event(
        body.title.strip(),
        body.budget.strip(),
        body.event_date,
        body.event_time if body.event_date else "",
        body.message.strip(),
        [p.model_dump() for p in body.participants],
        {int(g): int(r) for g, r in pairs.items()},
    )
    return {"admin_url": f"/e/{admin_token}"}


@app.post("/api/events/{admin_token}/redraw")
async def redraw_event(admin_token: str):
    event, people = load_admin(admin_token)
    require_active(event)
    if any(p["viewed_at"] for p in people):
        raise HTTPException(409, "Alguém já viu o seu amigo secreto — já não é possível refazer o sorteio.")
    ids = [str(p["id"]) for p in people]
    groups = {str(p["id"]): p["group_name"].casefold() or None for p in people}
    try:
        pairs = draw(ids, groups)
    except DrawError as e:
        raise HTTPException(400, str(e))
    db.redraw(event["id"], {int(g): int(r) for g, r in pairs.items()})
    return {"ok": True}


@app.post("/api/events/{admin_token}/email")
async def email_event(request: Request, admin_token: str, body: EmailRequest):
    if not mailer.enabled():
        raise HTTPException(400, "O envio de emails não está configurado no servidor.")
    event, people = load_admin(admin_token)
    require_active(event)
    LIMITS["email"].check(admin_token)
    if body.ids is None:
        targets = [p for p in people if p["email"] and not p["emailed_at"]]
    else:
        targets = [p for p in people if p["id"] in body.ids and p["email"]]
    if not targets:
        return {"sent": 0, "failed": []}

    root = base_url(request)
    admin_url = f"{root}/e/{admin_token}"
    share_url = f"{root}/s/{event['share_token']}" if any(not p["email"] for p in people) else None
    messages = [
        mailer.build_message(
            p["name"],
            p["email"],
            event,
            f"{root}/p/{p['token']}",
            admin_link=admin_url if p["is_manager"] else None,
            share_link=share_url if p["is_manager"] else None,
        )
        for p in targets
    ]
    try:
        results = await run_in_threadpool(mailer.send, messages)
    except Exception as e:
        raise HTTPException(502, f"Erro ao ligar ao servidor de email: {e}")

    failed = []
    for p, ok in zip(targets, results):
        if ok:
            db.mark_emailed(p["id"])
        else:
            failed.append(p["name"])
    return {"sent": len(targets) - len(failed), "failed": failed}


@app.post("/api/events/{admin_token}/release/{participant_id}")
async def release_name(admin_token: str, participant_id: int):
    event, _ = load_admin(admin_token)
    require_active(event)
    db.release(event["id"], participant_id)
    return {"ok": True}


@app.post("/api/events/{admin_token}/close")
async def close_event(admin_token: str):
    event, _ = load_admin(admin_token)
    db.set_closed(event["id"], True)
    return {"ok": True}


@app.post("/api/events/{admin_token}/reopen")
async def reopen_event(admin_token: str):
    event, _ = load_admin(admin_token)
    if is_past({**dict(event), "closed_at": None}):
        raise HTTPException(409, "A data da troca já passou: não dá para reabrir.")
    db.set_closed(event["id"], False)
    return {"ok": True}


@app.delete("/api/events/{admin_token}")
async def delete_event(admin_token: str):
    event, _ = load_admin(admin_token)
    db.delete_event(event["id"])
    return {"ok": True}


@app.post("/api/s/{share_token}/claim")
async def claim_name(request: Request, share_token: str, body: ClaimRequest):
    LIMITS["claim"].check(client_ip(request))
    event, people = db.get_event_by_share(share_token)
    me = next((p for p in people if p["id"] == body.participant_id), None)
    if not event or not me:
        raise HTTPException(404, "Participante não encontrado.")

    if not me["claimed_at"]:
        if me["emailed_at"]:
            raise HTTPException(403, f"{me['name']} recebeu um link pessoal por email. Usa esse link.")
        db.claim(me["id"], body.pin)
    else:
        if me["failed_pins"] >= db.MAX_PIN_ATTEMPTS:
            raise HTTPException(423, "Demasiadas tentativas erradas. Pede ao organizador para libertar o teu nome.")
        ok = db.check_pin(body.pin, me["pin_hash"])
        db.record_pin_attempt(me["id"], ok)
        if not ok:
            left = db.MAX_PIN_ATTEMPTS - me["failed_pins"] - 1
            raise HTTPException(403, f"PIN errado. {'Restam ' + str(left) + ' tentativas.' if left else 'Nome bloqueado: fala com o organizador.'}")
    return {"url": f"/p/{me['token']}", "name": me["name"]}


@app.post("/api/p/{token}/reveal")
async def reveal(request: Request, token: str):
    LIMITS["participant"].check(client_ip(request))
    # Marked on click, not on page load, so WhatsApp/iMessage link previews don't count as "seen".
    me, _, target = db.get_participant(token)
    if not me:
        raise HTTPException(404)
    db.mark_viewed(me["id"])
    return {"name": target["name"]}
