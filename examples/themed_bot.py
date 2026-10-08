"""Fully rebranded bot — shows every UI customization knob.

A neon "GlowStore" theme: custom QR colours/tagline, renamed buttons, custom
amount presets, and rewritten messages. Compare with minimal_bot.py (defaults).

    pip install bharatpe-pg python-dotenv

Env (see .env.example): BOT_TOKEN, UPI_ID, MERCHANT_NAME, ADMIN_IDS.
"""

import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bharatpe_pg import (
    PaymentConfig, init_db, register_payment_handlers, register_admin_handlers,
    start_session_monitor, load_persisted_session,
    QRTheme, UIButtons, Messages,
)
from bharatpe_pg.keyboards import menu_kb, is_admin

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s — %(message)s", level=logging.INFO)


async def on_verified(bot, order):
    await bot.send_message(
        order["user_id"],
        f"🎉 ₹{order['amount']:.2f} received — your order `{order['order_id']}` is unlocked!",
        parse_mode="Markdown")


cfg = PaymentConfig(
    upi_id        = os.environ["UPI_ID"],
    merchant_name = os.environ.get("MERCHANT_NAME", "GlowStore"),
    admin_ids     = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()],
    on_verified   = on_verified,

    # ── 1. QR card — neon purple/pink ──
    qr_theme = QRTheme(
        bg_top="#2d1b4e", bg_bottom="#0f0524", accent="#ff6b9d",
        qr_dark="#1a0b2e", tagline="PAY & GLOW ✨", footer_hint="UPI only",
        accent_dots=["#ff6b9d", "#c56cf0", "#786fa6"],
    ),
    # ── 2. Buttons + amount grid ──
    amount_presets = [49, 99, 199, 499],
    ui = UIButtons(menu_pay="🛒 Buy", pay_again="🔁 Buy More",
                   custom_label="💬 Other", amounts_per_row=2),
    # ── 3. Messages ──
    messages = Messages(
        pay_caption="🧾 Pay exactly *₹{amount:.2f}* to the QR above,\nthen paste the *12-digit UTR*.\n`{order_id}`",
        verified="✨ *Unlocked!* ₹{amount:.2f} from {payer}\n🔗 `{utr}`",
        amount_picker="How much would you like to top up?",
    ),
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = is_admin(update.effective_user.id, cfg.admin_ids)
    await update.message.reply_text(
        f"✨ *Welcome to {cfg.merchant_name}* ✨\nTap 🛒 Buy or send `/pay <amount>`.",
        reply_markup=menu_kb(admin=admin, cfg=cfg), parse_mode="Markdown")


def main():
    init_db(cfg)
    load_persisted_session(cfg)
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    register_payment_handlers(app, cfg)
    register_admin_handlers(app, cfg)
    start_session_monitor(app, cfg)
    print(f"Themed bot up — {cfg.merchant_name}")
    app.run_polling()


if __name__ == "__main__":
    main()
