from bot.db.models import Service
from bot.i18n import LANGS, money, t, title


def test_title_uses_translation_with_fallback():
    s = Service(name="Маникюр", names={"en": "Manicure"}, price=6000, duration_min=60)
    assert title(s, "en") == "Manicure"
    assert title(s, "kk") == "Маникюр"
    assert title(Service(name="Борода", price=1, duration_min=1), "en") == "Борода"


def test_money_currency_per_language():
    assert money("ru", 20000) == "20 000 ₸"
    assert money("en", 20000) == "20 000 KZT"


def test_all_locales_have_same_keys():
    keys = {lang: set(t.__globals__["_load"](lang)) for lang in LANGS}
    assert keys["kk"] == keys["ru"] == keys["en"]
