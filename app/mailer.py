import smtplib
from email.message import EmailMessage
from html import escape

from decouple import config

from app import ics

SMTP_SERVER = config("smtp_server_domain_name", cast=str, default="smtp.gmail.com")
SMTP_PORT = config("smtp_port", cast=int, default=587)
SENDER = config("sender_mail", cast=str, default="")
PASSWORD = config("smtp_password", cast=str, default="")


def enabled() -> bool:
    return bool(SENDER and PASSWORD)


def build_message(
    to_name: str,
    to_email: str,
    event,
    link: str,
    admin_link: str | None = None,
    share_link: str | None = None,
) -> EmailMessage:
    """link: the person's own secret link. admin_link/share_link: only for the manager."""
    title = event["title"]
    msg = EmailMessage()
    msg["Subject"] = f"🎁 {title} — descobre o teu amigo secreto"
    msg["From"] = f"Amigo Secreto <{SENDER}>"
    msg["To"] = to_email

    text = (
        f"Olá {to_name}!\n\n"
        f"O sorteio do «{title}» já foi feito.\n"
        f"Abre o teu link pessoal para descobrires quem te calhou:\n\n{link}\n\n"
        "Este link é só teu: não o reencaminhes 🤫\n"
    )
    manager_html = ""
    if admin_link:
        text += (
            f"\n---\nÉs o gestor deste sorteio. Para veres quem já viu, reenviar emails ou libertar nomes:\n{admin_link}\n"
            "Este link também é só para ti.\n"
        )
        manager_html = f"""<hr style="border:0;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:14px">És o <b>gestor</b> deste sorteio. Para veres quem já viu, reenviar emails ou libertar nomes:</p>
  <p><a href="{escape(admin_link)}" style="color:#b3261e;font-weight:600">Gerir o sorteio</a></p>"""
    if share_link:
        text += f"\nHá participantes sem email. Envia-lhes este link geral (escolhem o nome e um PIN):\n{share_link}\n"
        manager_html += f"""
  <p style="font-size:14px">Há participantes sem email. Envia-lhes este link geral — escolhem o nome e um PIN:<br>
  <a href="{escape(share_link)}" style="color:#b3261e">{escape(share_link)}</a></p>"""
    if admin_link:
        manager_html += """
  <p style="color:#777;font-size:13px">O link de gestão é só para ti.</p>"""

    msg.set_content(text)
    msg.add_alternative(
        f"""<div style="font-family:system-ui,sans-serif;max-width:480px;margin:auto;padding:24px;text-align:center">
  <div style="font-size:48px">🎁</div>
  <h2 style="margin:8px 0">{escape(title)}</h2>
  <p>Olá <b>{escape(to_name)}</b>! O sorteio já foi feito.</p>
  <p><a href="{escape(link)}" style="display:inline-block;background:#b3261e;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600">Descobrir o meu amigo secreto</a></p>
  <p style="color:#777;font-size:13px">Este link é só teu: não o reencaminhes 🤫</p>
  {manager_html}
</div>""",
        subtype="html",
    )
    calendar = ics.make_ics(event)
    if calendar:
        msg.add_attachment(
            calendar, subtype="calendar", charset="utf-8", cte="quoted-printable", filename="amigo-secreto.ics",
            params={"method": "PUBLISH"},
        )
    return msg


def send(messages: list[EmailMessage]) -> list[bool]:
    """Send all messages over one SMTP session. Returns per-message success."""
    results = []
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(SENDER, PASSWORD)
        for msg in messages:
            try:
                refused = smtp.send_message(msg)
                results.append(not refused)
            except smtplib.SMTPException:
                results.append(False)
    return results
