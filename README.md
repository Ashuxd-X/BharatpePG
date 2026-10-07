# bharatpe-payment-plugin

Drop-in UPI payments for any [python-telegram-bot](https://docs.python-telegram-bot.org) project, backed by your own BharatPe merchant account. A user pays the exact amount by scanning a QR, then sends you the 12-digit UTR; the bot verifies it against your BharatPe transactions and marks the order paid.

> **Honest caveat — read this first.** This talks to **unofficial / private BharatPe endpoints** (the ones the enterprise dashboard uses). There is no public BharatPe API. Endpoints can change or break without notice — they already changed domains once, which is why every host here is **configurable, not hard-coded**. Use it only with **your own KYC-verified merchant account**. You are responsible for complying with BharatPe's terms.

## What you get

- `/pay [amount]` — amount picker → exact-amount UPI QR → user submits UTR → verified.
- `/login` — admin authenticates the BharatPe session with mobile + OTP (OTP typed manually, never auto-read).
- `/admin` — recent payments + search by order ID / UTR.
- Zero database setup by default (stdlib sqlite file). Postgres is an opt-in extra.

## 5-minute quickstart

Install straight from GitHub — it's a single importable package, nothing to copy:

```bash
pip install git+https://github.com/AshuXD-X/bharatpe-payment-plugin
# Postgres instead of the default sqlite file store:
# pip install "bharatpe-payment-plugin[postgres] @ git+https://github.com/AshuXD-X/bharatpe-payment-plugin"
```

Add it to any existing `python-telegram-bot` app with three calls — your own
handlers are untouched:

```python
from telegram.ext import Application
from payment_plugin import PaymentConfig, init_db, register_payment_handlers, register_admin_handlers

cfg = PaymentConfig(
    upi_id="yourname@yesbankltd",
    merchant_name="My Store",
    admin_ids=[123456789],       # your Telegram user ID(s)
    # merchant_id is optional — auto-discovered when the admin runs /login
)

app = Application.builder().token("BOT_TOKEN").build()
init_db(cfg)                     # sqlite file store — no DB server needed
register_payment_handlers(app, cfg)
register_admin_handlers(app, cfg)   # optional: /admin + /login
app.run_polling()
```

A runnable version with `/start` + `nav:home` is in [`examples/minimal_bot.py`](examples/minimal_bot.py).

## Configuration

`PaymentConfig` is a dataclass — pass values directly or read them from env vars. Only `upi_id` and `merchant_name` are required (plus `admin_ids` if you want `/login` and `/admin`).

| Field | Default | Meaning |
|---|---|---|
| `upi_id` | — (required) | Your UPI VPA, encoded into the QR |
| `merchant_name` | — (required) | Shown on the QR card |
| `merchant_id` | `""` (optional) | Usually unneeded — BharatPe scopes by your login token; omitted from the request when blank |
| `admin_ids` | `[]` | Telegram user IDs allowed to run `/login` and `/admin` |
| `auth_host` | `https://enterprise.bharatpe.in` | Login/OTP host |
| `api_host` | `https://api-enterprise.bharatpe.in` | Transactions API host |
| `bharatpe_api` | derived from `api_host` | Full transactions URL (override only if needed) |
| `db_url` | `""` | Set to a `postgres://…` DSN to use Postgres instead of sqlite |
| `db_path` | `payments.db` | sqlite file path (used when `db_url` is empty) |
| `utr_window_sec` | `1800` | UTR recency guard — reject UTRs older than this |
| `min_amount` / `max_amount` | `1` / `50000` | Allowed payment range (₹) |
| `user_agent` | mobile Chrome UA | Sent on BharatPe requests |

## The `/login` OTP flow

BharatPe login is phone number + OTP (no password). An admin runs it once:

1. Admin sends `/login` → bot asks for the 10-digit mobile.
2. Bot calls BharatPe `requestotp`; BharatPe texts the OTP to the admin's phone.
3. Admin types the OTP into the chat → bot calls `verifyotp` and stores the `accessToken` + session cookies in memory.

The OTP is **entered manually every time**. The bot never reads SMS. If the session later expires, just run `/login` again.

## The payment + verify flow

1. User sends `/pay 500` (or taps an amount) → bot creates an order and shows a QR for **exactly ₹500**.
2. User pays with any UPI app and copies the **12-digit UTR** (bank reference number).
3. User sends the UTR to the bot. Before marking the order paid, the UTR must clear five guards:
   1. **exists** in your BharatPe transactions,
   2. type `PAYMENT_RECV` and status `SUCCESS`,
   3. amount matches the order,
   4. not already used by another order (`utr` column is `UNIQUE` — reuse is rejected at the storage layer),
   5. recent, within `utr_window_sec`.

   The submitted value is validated as 12 digits before any lookup.

## Security

- **Never commit the Burp capture or any session.** The raw capture contains a live token/cookies; it is gitignored and must stay out of the repo.
- Credentials come from the live `/login` session (or `api_token`/`api_cookie` seeds you inject) — not from source.
- The `utr UNIQUE` constraint makes "one UTR, one order" a storage invariant, so a copied UTR can't be replayed against a second order.
- `/login` and `/admin` are locked to `admin_ids`.

## Deploy — Railway / Render / VPS

Default is zero-DB: the sqlite file lives next to the bot, so a plain worker/process just works.

- **Railway / Render:** add a service running `python examples/minimal_bot.py`, set `BOT_TOKEN`, `UPI_ID`, `MERCHANT_NAME`, `MERCHANT_ID`, `ADMIN_IDS`. For sqlite to survive restarts, mount a persistent volume and point `DB_PATH` at it.
- **VPS:** run under `systemd` or `pm2`; same env vars.
- **Postgres (opt-in):** `pip install "bharatpe-payment-plugin[postgres]"` (or `psycopg2-binary`) and set `DATABASE_URL=postgres://…`. The same schema (`utr UNIQUE`) is created automatically — recommended if you run multiple processes.

## License

MIT — see [LICENSE](LICENSE).
