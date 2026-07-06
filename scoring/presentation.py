from __future__ import annotations

from datetime import datetime
from typing import Any


MONTHS_GENITIVE = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def format_datetime_parts(value: Any) -> dict[str, str]:
    original = "" if value is None else str(value)
    if not original.strip():
        return {"date": "", "time": "", "text": "", "iso": original}

    text = original.strip()
    parse_value = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError:
        return {"date": text, "time": "", "text": text, "iso": original}

    date_text = f"{parsed.day} {MONTHS_GENITIVE[parsed.month - 1]} {parsed.year}"
    time_text = "" if "T" not in text and " " not in text else f"{parsed.hour:02d}:{parsed.minute:02d}"
    human_text = f"{date_text}, {time_text}" if time_text else date_text
    return {"date": date_text, "time": time_text, "text": human_text, "iso": original}
