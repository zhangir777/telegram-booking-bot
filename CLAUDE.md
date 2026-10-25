# telegram-booking-bot

## Commands
- `uv sync`, `uv run pytest -q`, `uv run ruff format . && uv run ruff check --fix .`
- Run: `uv run python -m bot.main` (needs `.env`), demo data: `uv run seed-demo`

## Rules
- aiogram 3 only (Router, F, CallbackData, FSMContext). Never aiogram 2 syntax.
- Business logic in `bot/services/` without aiogram imports; test it there.
- All user-facing texts in `bot/locales/{ru,kk,en}.yaml`; same keys in every file.
- Times are naive datetimes in `settings.timezone` (Asia/Almaty).
- Every booking write goes through `services/booking.py` (lock + transaction + unique index).
- Callback data: typed `CallbackData` classes; always re-check that the booking belongs to the user.
- Secrets: `BOT_TOKEN` only in `.env`. Never print or log it, never ask the user to paste it in chat.
- SQLite: WAL + timeout=30 (see `db/session.py`).

## New client
Edit `business.yaml`, locales if needed, then add masters/services (seed script copy or `/addservice`).
