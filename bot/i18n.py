from functools import cache
from pathlib import Path

import yaml

LOCALES = Path(__file__).parent / "locales"
LANGS = ("ru", "kk", "en")
DEFAULT = "ru"


@cache
def _load(lang: str) -> dict[str, str]:
    return yaml.safe_load((LOCALES / f"{lang}.yaml").read_text(encoding="utf-8"))


def t(lang: str, key: str, **kwargs) -> str:
    texts = _load(lang if lang in LANGS else DEFAULT)
    text = texts.get(key) or _load(DEFAULT)[key]
    return text.format(**kwargs) if kwargs else text


def title(obj, lang: str) -> str:
    """Translated name of a master or service; falls back to the base name."""
    return (obj.names or {}).get(lang) or obj.name


def money(lang: str, amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " " + t(lang, "currency")


def booking_details(lang: str, b, service_name: str | None = None) -> str:
    return t(
        lang,
        "details",
        service=service_name or title(b.service, lang),
        master=title(b.master, lang),
        date=b.start.strftime("%d.%m.%Y"),
        time=b.start.strftime("%H:%M"),
        price=money(lang, b.service.price),
    )
