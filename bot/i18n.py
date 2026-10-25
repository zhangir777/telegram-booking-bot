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


def booking_details(lang: str, b, service_name: str | None = None) -> str:
    return t(
        lang,
        "details",
        service=service_name or b.service.name,
        master=b.master.name,
        date=b.start.strftime("%d.%m.%Y"),
        time=b.start.strftime("%H:%M"),
        price=f"{b.service.price:,}".replace(",", " "),
    )
