"""Professional reference bot — bharatpe-payment-plugin.

Shows every feature wired together:
  • /start with inline + persistent reply keyboards
  • /pay flow (QR → UTR → verify) via the plugin
  • /login (OTP) + /admin, locked to ADMIN_IDS
  • on_verified delivery hook (demo: credit wallet)
  • /balance to read the demo wallet
  • background session monitor (outage detection + queued auto-verify)
  • Unicode small-caps UI text via sc()

    pip install git+https://github.com/AshuXD-X/bharatpe-payment-plugin python-dotenv

Env (see .env.example): BOT_TOKEN, UPI_ID, MERCHANT_NAME, ADMIN_IDS,
optional DATABASE_URL / DB_PATH.
"""

import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root on path
from dotenv import load_dotenv; load_dotenv()
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from payment_plugin import (
    PaymentConfig, init_db, register_payment_handlers,
    register_admin_handlers, start_session_monitor, load_persisted_session,
)
from payment_plugin.keyboards import menu_kb, is_admin

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s — %(message)s", level=logging.INFO)


# ── Unicode small-caps for bot text ──────────────────────────────────────────
_SC = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘqʀꜱᴛᴜᴠᴡxʏᴢ")   # ponytail: a-z→small caps; q/x have none, pass through


def sc(text: str) -> str:
    """Render lowercase letters as Unicode small caps (keeps *markdown*, digits, emoji)."""
    return text.translate(_SC)


# ── Demo wallet (replace with your real DB in production) ─────────────────────
_balances: dict[int, int] = {}
CREDIT_RATE = 1   # ₹1 → 1 credit


async def on_verified(bot, order):
    """Delivery hook — fires once per verified payment (instant or post-outage)."""
    credits = int(order["amount"] * CREDIT_RATE)
    _balances[order["user_id"]] = _balances.get(order["user_id"], 0) + credits
    await bot.send_message(
        order["user_id"],
        f"🎉 *{sc('payment received')}*\n"
        f"💰 ₹{order['amount']:.2f}  →  +{credits} {sc('credits')}\n"
        f"💼 {sc('balance')}: {_balances[order['user_id']]}",
        parse_mode="Markdown")


cfg = PaymentConfig(
    upi_id        = os.environ["UPI_ID"],
    merchant_name = os.environ["MERCHANT_NAME"],
    merchant_id   = os.environ.get("MERCHANT_ID", ""),
    admin_ids     = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()],
    db_url        = os.environ.get("DATABASE_URL", ""),
    db_path       = os.environ.get("DB_PATH", "payments.db"),
    on_verified   = on_verified,
)


def _home_inline():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💳 ᴩᴀʏ ɴᴏᴡ", callback_data="pay:start")]])


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = is_admin(update.effective_user.id, cfg.admin_ids)
    await update.message.reply_text(
        f"👋 *{sc('welcome to')} {cfg.merchant_name}*\n\n"
        f"{sc('tap a button below or send')} `/pay <amount>`\n"
        f"{sc('check credits with')} /balance",
        reply_markup=menu_kb(admin=admin), parse_mode="Markdown")
    await update.message.reply_text(sc("quick pay") + ":", reply_markup=_home_inline())


async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bal = _balances.get(update.effective_user.id, 0)
    await update.message.reply_text(
        f"💼 *{sc('your balance')}*: {bal} {sc('credits')}\n{sc('top up with')} `/pay <amount>`",
        parse_mode="Markdown")


async def on_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(sc("main menu") + ":", reply_markup=_home_inline())


def main():
    init_db(cfg)
    load_persisted_session(cfg)           # stay logged in across redeploys
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("balance", cmd_balance))
    register_payment_handlers(app, cfg)
    register_admin_handlers(app, cfg)
    start_session_monitor(app, cfg)
    app.add_handler(CallbackQueryHandler(on_home, pattern=r"^nav:home$"))  # AFTER plugin handlers
    print(f"Bot up — {cfg.merchant_name} | admins={cfg.admin_ids} | rate={CREDIT_RATE} credit/₹")
    app.run_polling()


if __name__ == "__main__":
    main()
