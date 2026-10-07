"""Minimal bot example — bharatpe-payment-plugin.

Set the env vars below and run. The bot takes UPI payments via /pay (scan the
exact-amount QR, then send the 12-digit UTR). Admins run /login once to
authenticate the BharatPe merchant session; /admin shows recent payments.

    pip install python-telegram-bot requests pillow qrcode[pil]

Files needed alongside this script (copy from the repo root):
    payment_plugin/   bharatpe.py   qr_generator.py   database.py
"""

import os, logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from payment_plugin import PaymentConfig, register_payment_handlers, register_admin_handlers
from payment_plugin.keyboards import menu_kb, is_admin
from database import init_db

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s — %(message)s", level=logging.INFO)

cfg = PaymentConfig(
    upi_id        = os.environ["UPI_ID"],          # e.g. "yourname@yesbankltd"
    merchant_name = os.environ["MERCHANT_NAME"],   # shown on the QR card
    merchant_id   = os.environ["MERCHANT_ID"],     # BharatPe merchant ID
    admin_ids     = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()],
    db_url        = os.environ.get("DATABASE_URL", ""),   # optional — opt-in Postgres
    db_path       = os.environ.get("DB_PATH", "payments.db"),
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Persistent reply keyboard (bottom bar) + inline Pay Now button — both work.
    await update.message.reply_text(
        f"👋 Welcome to *{cfg.merchant_name}*!\nUse the buttons below or send `/pay <amount>`.",
        reply_markup=menu_kb(admin=is_admin(update.effective_user.id, cfg.admin_ids)),
        parse_mode="Markdown")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now", callback_data="pay:start")]])
    await update.message.reply_text("Quick pay:", reply_markup=kb)


async def on_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now", callback_data="pay:start")]])
    await q.message.reply_text("Main menu — choose an option:", reply_markup=kb)


def main():
    init_db(cfg)
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    register_payment_handlers(app, cfg)
    register_admin_handlers(app, cfg)
    app.add_handler(CallbackQueryHandler(on_home, pattern=r"^nav:home$"))  # register AFTER plugin handlers
    print(f"Bot starting — merchant: {cfg.merchant_name} ({cfg.merchant_id})")
    app.run_polling()


if __name__ == "__main__":
    main()
