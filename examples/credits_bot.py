"""Credits top-up bot — real example of the on_verified hook.

Use case: a bot that sells credits. User pays ₹100 → gets 100 credits
(rate set by you). Pay with /pay, scan the QR, send the UTR; the moment the
payment verifies, on_verified runs and the credits land in the user's balance.
Works the same if the payment verifies instantly OR after a gateway outage —
the plugin fires on_verified once per paid order either way.

    pip install git+https://github.com/AshuXD-X/BharatpePG python-dotenv

Env: BOT_TOKEN, UPI_ID, MERCHANT_NAME, ADMIN_IDS  (see .env.example)
"""

import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bharatpe_pg import (
    PaymentConfig, init_db, register_payment_handlers,
    register_admin_handlers, start_session_monitor, load_persisted_session,
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s — %(message)s", level=logging.INFO)

CREDIT_RATE = 1          # 1 credit per ₹1 — change to whatever you want (2, 10, ...)
_balances: dict[int, int] = {}   # demo wallet; use your real DB in production


def add_credits(user_id: int, n: int) -> int:
    _balances[user_id] = _balances.get(user_id, 0) + n
    return _balances[user_id]


# ── The hook: runs once when a payment is verified (instant OR post-outage) ──
async def on_verified(bot, order):
    credits = int(order["amount"] * CREDIT_RATE)
    total = add_credits(order["user_id"], credits)
    await bot.send_message(
        order["user_id"],
        f"🎉 Added *{credits}* credits for ₹{order['amount']:.0f}.\n"
        f"💼 Balance: *{total}* credits.",
        parse_mode="Markdown")


cfg = PaymentConfig(
    upi_id        = os.environ["UPI_ID"],
    merchant_name = os.environ["MERCHANT_NAME"],
    admin_ids     = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()],
    on_verified   = on_verified,          # ← the whole integration is this one line + the function
)


async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bal = _balances.get(update.effective_user.id, 0)
    await update.message.reply_text(f"💼 Your balance: {bal} credits.\nTop up with /pay <amount>.")


def main():
    init_db(cfg)
    load_persisted_session(cfg)           # stay logged in across redeploys
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("balance", cmd_balance))
    register_payment_handlers(app, cfg)   # /pay flow fires on_verified on success
    register_admin_handlers(app, cfg)     # /login (OTP) + /admin
    start_session_monitor(app, cfg)       # outage detection + queued-payment auto-verify
    print(f"Credits bot up — {cfg.merchant_name}, rate {CREDIT_RATE} credit/₹")
    app.run_polling()


if __name__ == "__main__":
    main()
