import pytest

from template.bot import CONFIG, menu_kb, normalize_phone


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("8 777 123 45 67", "+77771234567"),
        ("+7 (777) 123-45-67", "+77771234567"),
        ("77771234567", "+77771234567"),
        ("7771234567", "+77771234567"),
        ("12345", None),
        ("", None),
    ],
)
def test_normalize_phone(raw, phone):
    assert normalize_phone(raw) == phone


def test_menu_has_all_faq_and_lead_button():
    rows = menu_kb().inline_keyboard
    assert len(rows) == len(CONFIG["faq"]) + 1
    assert rows[-1][0].callback_data == "faq:-1"
