from datetime import date, datetime, timedelta, timezone

DURATION = timedelta(hours=3)


def _bounds(event_date: str, event_time: str) -> tuple[str, str, bool]:
    """Returns (start, end, all_day) in iCalendar basic format."""
    day = date.fromisoformat(event_date)
    if event_time:
        start = datetime.combine(day, datetime.strptime(event_time, "%H:%M").time())
        end = start + DURATION
        return start.strftime("%Y%m%dT%H%M%S"), end.strftime("%Y%m%dT%H%M%S"), False
    return day.strftime("%Y%m%d"), (day + timedelta(days=1)).strftime("%Y%m%d"), True


def _description(event) -> str:
    parts = ["Troca de prendas do amigo secreto 🎁"]
    if event["budget"]:
        parts.append(f"Valor da prenda: {event['budget']}")
    if event["message"]:
        parts.append(event["message"])
    return "\n\n".join(parts)


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold lines longer than 75 octets, as RFC 5545 requires."""
    out, current = [], b""
    for ch in line:
        encoded = ch.encode()
        if len(current) + len(encoded) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += encoded
    out.append(current.decode())
    return "\r\n ".join(out)


def make_ics(event) -> str | None:
    if not event["event_date"]:
        return None
    start, end, all_day = _bounds(event["event_date"], event["event_time"])
    kind = ";VALUE=DATE" if all_day else ""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Amigo Secreto//PT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event['share_token']}@amigo-secreto",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART{kind}:{start}",
        f"DTEND{kind}:{end}",
        f"SUMMARY:{_escape('🎁 ' + event['title'])}",
        f"DESCRIPTION:{_escape(_description(event))}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_escape('Não te esqueças da prenda! 🎁')}",
        "TRIGGER:-P1D",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
