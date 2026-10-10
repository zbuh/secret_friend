import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def anon(tmp_path, monkeypatch):
    from app import db, main

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(main, "ACCESS_CODE", "segredo")
    for limit in main.LIMITS.values():
        limit.reset()
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def client(anon):
    assert anon.post("/api/login", json={"password": "segredo"}).status_code == 200
    return anon


EVENT = {
    "title": "Natal",
    "budget": "20 €",
    "participants": [{"name": "Ana", "group": "casal", "email": "ana@x.pt", "manager": True}, {"name": "Rui", "group": "casal"}, {"name": "Marta"}, {"name": "João"}],
}


def test_full_flow(client):
    from app import db

    res = client.post("/api/events", json=EVENT)
    assert res.status_code == 200
    admin = res.json()["admin_url"]
    assert client.get(admin).status_code == 200

    event, people = db.get_event_by_admin(admin.split("/")[-1])
    by_id = {p["id"]: p for p in people}
    ana = next(p for p in people if p["name"] == "Ana")

    page = client.get(f"/p/{ana['token']}")
    assert page.status_code == 200
    # Target name is not in the page until revealed
    target = by_id[ana["target_id"]]["name"]
    assert f'id="target-name">{target}' not in page.text

    revealed = client.post(f"/api/p/{ana['token']}/reveal").json()
    assert revealed["name"] == target != "Rui"

    # Once someone has seen it, no redraw
    assert client.post(f"/api{admin.replace('/e/', '/events/')}/redraw").status_code == 409
    assert client.delete(f"/api{admin.replace('/e/', '/events/')}").status_code == 200
    assert client.get(f"/p/{ana['token']}").status_code == 404


def test_share_link_claim_and_pin(client):
    from app import db

    admin = client.post("/api/events", json=EVENT).json()["admin_url"]
    admin_token = admin.split("/")[-1]
    event, people = db.get_event_by_admin(admin_token)
    share = event["share_token"]
    marta = next(p for p in people if p["name"] == "Marta")

    page = client.get(f"/s/{share}")
    assert page.status_code == 200 and "Marta" in page.text
    # The admin page no longer exposes personal links
    assert marta["token"] not in client.get(admin).text

    claim = lambda pin: client.post(f"/api/s/{share}/claim", json={"participant_id": marta["id"], "pin": pin})
    res = claim("1234")
    assert res.status_code == 200 and res.json()["url"] == f"/p/{marta['token']}"

    # Coming back from another device: right PIN works, wrong PIN doesn't
    assert claim("1234").status_code == 200
    assert claim("0000").status_code == 403
    assert claim("12ab").status_code == 422

    # Lock after too many wrong attempts
    for _ in range(4):
        claim("0000")
    assert claim("1234").status_code == 423

    # Organizer releases the name: old link dies, name can be claimed again with a new PIN
    assert client.post(f"/api/events/{admin_token}/release/{marta['id']}").status_code == 200
    assert client.get(f"/p/{marta['token']}").status_code == 404
    res = claim("9999")
    assert res.status_code == 200 and res.json()["url"] != f"/p/{marta['token']}"


def test_migrates_old_database(tmp_path, monkeypatch):
    import sqlite3

    from app import db

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, admin_token TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
            budget TEXT NOT NULL DEFAULT '', event_date TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL);
        CREATE TABLE participants (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, token TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', group_name TEXT NOT NULL DEFAULT '',
            target_id INTEGER, wishlist TEXT NOT NULL DEFAULT '', viewed_at TEXT, emailed_at TEXT);
        INSERT INTO events (admin_token, title, created_at) VALUES ('adm', 'Velho', 'x');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init()
    event, _ = db.get_event_by_admin("adm")
    assert event["share_token"]


def test_duplicate_names(client):
    body = {**EVENT, "participants": [{"name": "Ana", "email": "a@x.pt", "manager": True}, {"name": "ana"}, {"name": "Rui"}]}
    assert client.post("/api/events", json=body).status_code == 400


def test_login_required(anon):
    # Without a session: no list of events, no creating
    assert 'id="login-form"' in anon.get("/").text
    assert anon.get("/novo", follow_redirects=False).status_code == 303
    assert anon.post("/api/events", json=EVENT).status_code == 401
    assert anon.post("/api/login", json={"password": "errada"}).status_code == 403

    anon.post("/api/login", json={"password": "segredo"})
    assert anon.post("/api/events", json=EVENT).status_code == 200
    assert "Natal" in anon.get("/").text

    anon.post("/api/logout")
    assert 'id="login-form"' in anon.get("/").text


def test_admin_link_works_without_login(client):
    admin = client.post("/api/events", json=EVENT).json()["admin_url"]
    client.post("/api/logout")
    page = client.get(admin)
    assert page.status_code == 200 and "Todos os sorteios" not in page.text


def test_emails_carry_personal_links(client, monkeypatch):
    from app import db, mailer

    sent = []
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda msgs: sent.extend(msgs) or [True] * len(msgs))
    body = {**EVENT, "participants": EVENT["participants"][:2] + [{"name": "Marta", "email": "m@x.pt"}, {"name": "João"}]}
    admin = client.post("/api/events", json=body).json()["admin_url"]
    admin_token = admin.split("/")[-1]
    api = f"/api/events/{admin_token}"
    assert client.post(f"{api}/email", json={}).json() == {"sent": 2, "failed": []}

    event, people = db.get_event_by_admin(admin_token)
    by_name = {p["name"]: p for p in people}
    mails = {m["To"]: m.get_body(("plain",)).get_content() for m in sent}
    share = f"/s/{event['share_token']}"

    # Everyone gets their own link; only the manager gets the admin link and the general link
    assert f"/p/{by_name['Marta']['token']}" in mails["m@x.pt"]
    assert admin not in mails["m@x.pt"] and share not in mails["m@x.pt"]
    assert f"/p/{by_name['Ana']['token']}" in mails["ana@x.pt"]
    assert admin in mails["ana@x.pt"] and share in mails["ana@x.pt"]

    # Emailed names can't be claimed through the general link; others still can
    claim = lambda name: client.post(f"/api/s/{event['share_token']}/claim", json={"participant_id": by_name[name]["id"], "pin": "1234"})
    assert claim("Marta").status_code == 403
    assert claim("João").status_code == 200
    assert "recebeu link por email" in client.get(share).text

    # Releasing kills the old personal link and lets the email be sent again with a new one
    old = by_name["Marta"]["token"]
    client.post(f"{api}/release/{by_name['Marta']['id']}")
    assert client.get(f"/p/{old}").status_code == 404
    sent.clear()
    assert client.post(f"{api}/email", json={}).json()["sent"] == 1
    assert old not in sent[0].get_body(("plain",)).get_content()


def test_exactly_one_manager_with_email(client):
    people = EVENT["participants"]
    for participants in (
        [{**p, "manager": True} for p in people],  # several
        [{**p, "manager": False} for p in people],  # none
        [{**p, "manager": p["name"] == "Marta"} for p in people],  # manager without email
    ):
        assert client.post("/api/events", json={**EVENT, "participants": participants}).status_code == 400


def test_participant_pages_link_home_to_their_event(client):
    from app import db

    admin = client.post("/api/events", json=EVENT).json()["admin_url"]
    event, _ = db.get_event_by_admin(admin.split("/")[-1])
    assert f'href="/s/{event["share_token"]}" class="brand"' in client.get(f"/s/{event['share_token']}").text


def test_healthz(anon):
    assert anon.get("/healthz").json() == {"ok": True}


def test_security_headers(client):
    res = client.get("/")
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["cache-control"] == "no-store"


def test_rate_limit_on_password_guessing(anon):
    codes = [anon.post("/api/login", json={"password": str(i)}).status_code for i in range(12)]
    assert codes[:10] == [403] * 10
    assert codes[10:] == [429, 429]


def test_rate_limit_on_pin_guessing(client):
    from app import db

    admin = client.post("/api/events", json=EVENT).json()["admin_url"]
    event, people = db.get_event_by_admin(admin.split("/")[-1])
    share = event["share_token"]
    statuses = [
        client.post(f"/api/s/{share}/claim", json={"participant_id": people[i % 4]["id"], "pin": "1111"}).status_code
        for i in range(25)
    ]
    assert 429 in statuses


def test_home_and_create_pages(client):
    assert "Criar novo sorteio" in client.get("/").text
    assert 'id="create-form"' in client.get("/novo").text


def test_calendar_event_in_email(client, monkeypatch):
    from app import mailer

    sent = []
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda msgs: sent.extend(msgs) or [True] * len(msgs))
    body = {**EVENT, "event_date": "2026-12-24", "event_time": "20:00", "message": "Em casa da avó, às 20h; tragam fome"}
    admin = client.post("/api/events", json=body).json()["admin_url"]
    client.post(f"/api{admin.replace('/e/', '/events/')}/email", json={})

    (msg,) = sent
    (attachment,) = list(msg.iter_attachments())
    assert attachment.get_content_type() == "text/calendar"
    ics = attachment.get_content()
    assert "DTSTART:20261224T200000" in ics and "DTEND:20261224T230000" in ics
    assert "SUMMARY:🎁 Natal" in ics
    assert r"avó\, às 20h\; tragam fome" in ics.replace("\n ", "")
    assert all(len(line.encode()) <= 75 for line in ics.splitlines())
    # On the wire (as smtplib sends it) the attachment has CRLF line endings
    from email import message_from_bytes, policy

    wire = message_from_bytes(msg.as_bytes(policy=msg.policy.clone(linesep="\r\n")), policy=policy.default)
    raw = next(wire.iter_attachments()).get_payload(decode=True)
    assert raw.startswith(b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert "Google Calendar" not in msg.get_body(("html",)).get_content()


def test_all_day_event_and_no_date(client, monkeypatch):
    from app import ics

    event = {"title": "Natal", "budget": "", "message": "", "share_token": "x", "event_date": "2026-12-24", "event_time": ""}
    assert "DTSTART;VALUE=DATE:20261224" in ics.make_ics(event)
    assert "DTEND;VALUE=DATE:20261225" in ics.make_ics(event)
    assert ics.make_ics({**event, "event_date": ""}) is None
    assert client.post("/api/events", json={**EVENT, "event_time": "25:00"}).status_code == 422


def test_past_event_becomes_a_memory(client):
    from app import db

    admin = client.post("/api/events", json={**EVENT, "event_date": "2020-12-24"}).json()["admin_url"]
    api = f"/api{admin.replace('/e/', '/events/')}"
    _, people = db.get_event_by_admin(admin.split("/")[-1])
    by_id = {p["id"]: p for p in people}

    page = client.get(admin).text
    assert "Quem ofereceu a quem" in page and "Enviar links" not in page
    for p in people:  # every pair is shown
        assert p["name"] in page and by_id[p["target_id"]]["name"] in page

    # No more sending, releasing or redrawing; can't reopen a date in the past
    assert client.post(f"{api}/email", json={}).status_code in (400, 409)
    assert client.post(f"{api}/release/{people[0]['id']}").status_code == 409
    assert client.post(f"{api}/redraw").status_code == 409
    assert client.post(f"{api}/reopen").status_code == 409
    assert 'id="reopen"' not in page

    home = client.get("/").text
    assert "Lembranças" in home and "2020" in home


def test_close_and_reopen_by_hand(client):
    admin = client.post("/api/events", json=EVENT).json()["admin_url"]
    api = f"/api{admin.replace('/e/', '/events/')}"
    assert "Enviar" in client.get(admin).text

    assert client.post(f"{api}/close").status_code == 200
    page = client.get(admin).text
    assert "Quem ofereceu a quem" in page and 'id="reopen"' in page
    assert client.post(f"{api}/redraw").status_code == 409

    assert client.post(f"{api}/reopen").status_code == 200
    assert "Quem ofereceu a quem" not in client.get(admin).text


def test_chains_follow_who_gives_to_whom():
    from app.main import chains

    people = [
        {"id": 1, "name": "A", "target_id": 2},
        {"id": 2, "name": "B", "target_id": 1},
        {"id": 3, "name": "C", "target_id": 4},
        {"id": 4, "name": "D", "target_id": 5},
        {"id": 5, "name": "E", "target_id": 3},
    ]
    assert [[p["name"] for p in c] for c in chains(people)] == [["A", "B"], ["C", "D", "E"]]
