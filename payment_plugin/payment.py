"""Payment handler — /pay flow: pick amount, show exact-amount QR, then verify
the user-submitted 12-digit UTR against BharatPe transactions."""

import re
import time
import logging
from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from .bharatpe import find_by_utr, CredentialsExpiredError
from .qr_generator import make_qr
from .database import insert_payment, get_payment, claim_utr, fail_payment, queue_utr
from .config import PaymentConfig
from .keyboards import amounts_kb, result_kb, BTN_PAY
from .session_monitor import session_healthy

_GATEWAY_DOWN = "🛠 Payment gateway is temporarily down. Please try again in a few minutes."

log = logging.getLogger(__name__)


def register_payment_handlers(app, cfg: PaymentConfig):
    """Register the payment handlers, closed over cfg."""

    async def _start_payment(message, ctx, amount: float, user_id: int):
        if not session_healthy():          # don't take money we can't verify — no QR
            await message.reply_text(_GATEWAY_DOWN)
            return
        if not (cfg.min_amount <= amount <= cfg.max_amount):
            await message.reply_text(f"❌ Amount must be ₹{cfg.min_amount:.0f}–₹{cfg.max_amount:,.0f}")
            return
        order_id = f"TG{int(time.time())}{int(amount * 100):05d}"
        insert_payment(order_id, user_id, amount)
        ctx.user_data["await_utr"] = order_id
        log.info(f"NEW | {order_id} | ₹{amount} | user={user_id}")
        await message.reply_photo(
            photo=make_qr(amount, order_id, cfg),
            caption=(f"💳 *Pay exactly ₹{amount:.2f}*\n📱 Scan with any UPI app\n\n"
                     f"Then send me the *12-digit UTR* from your payment app.\n📝 `{order_id}`"),
            parse_mode="Markdown",
        )

    async def cmd_pay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if ctx.args:
            try:
                await _start_payment(update.message, ctx, float(ctx.args[0]), update.effective_user.id)
                return
            except ValueError:
                pass
        await update.message.reply_text("Select amount or enter custom:", reply_markup=amounts_kb())

    async def on_pay_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        _, action = q.data.split(":", 1)
        if action in ("start", "custom"):
            ctx.user_data["input"] = "pay_amount"
            await q.message.reply_text("Enter the amount (₹):")
        else:
            await _start_payment(q.message, ctx, float(action), q.from_user.id)

    async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if text == BTN_PAY:                           # reply-keyboard "💳 Pay"
            await update.message.reply_text("Select amount or enter custom:", reply_markup=amounts_kb())
            return
        # UTR submission takes priority if we're awaiting one.
        order_id = ctx.user_data.get("await_utr")
        if order_id:
            await _verify_utr(update.message, ctx, order_id, text)
            return
        if ctx.user_data.get("input") == "pay_amount":
            ctx.user_data.pop("input", None)
            try:
                amount = float(text.replace("₹", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text("❌ Enter a valid number. Example: `100`", parse_mode="Markdown")
                return
            await _start_payment(update.message, ctx, amount, update.effective_user.id)

    async def _verify_utr(message, ctx, order_id: str, text: str):
        utr = text.replace(" ", "")
        if not re.fullmatch(r"\d{12}", utr):          # trust boundary: validate before any lookup
            await message.reply_text("❌ A UTR is 12 digits. Check your UPI app and resend.")
            return
        pay = get_payment(order_id)
        if not pay or pay["status"] != "PENDING":
            ctx.user_data.pop("await_utr", None)
            await message.reply_text("⚠️ This order is no longer pending. Start a new /pay.")
            return
        if not session_healthy():          # known outage — queue without hitting BharatPe
            queue_utr(order_id, utr)
            ctx.user_data.pop("await_utr", None)
            await message.reply_text(
                "🛠 Payment gateway is temporarily down. Your payment is *saved* — "
                "I'll notify you here as soon as it's verified.", parse_mode="Markdown")
            return
        try:
            match = find_by_utr(utr, pay["amount"], cfg)
        except CredentialsExpiredError:
            # Queue it — the monitor verifies and notifies the user once the session is back.
            queue_utr(order_id, utr)
            ctx.user_data.pop("await_utr", None)
            await message.reply_text(
                "🛠 Payment gateway is temporarily down. Your payment is *saved* — "
                "I'll notify you here as soon as it's verified.", parse_mode="Markdown")
            return
        except Exception as e:
            log.error(f"UTR lookup failed: {e}")
            await message.reply_text("⚠️ Couldn't reach BharatPe. Try again in a moment.")
            return
        if not match:
            await message.reply_text("❌ Not found yet (or amount/time mismatch). Wait a moment and resend.")
            return
        if not claim_utr(order_id, utr):              # guard #4: UNIQUE blocks reuse
            await message.reply_text("❌ This UTR was already used for another order.")
            return
        ctx.user_data.pop("await_utr", None)
        payer = match["payer_name"] or match["vpa"] or "N/A"
        await message.reply_text(
            f"✅ *Payment Verified!*\n💰 ₹{match['amount']:.2f}\n🔗 `{utr}`\n👤 {payer}\n📝 `{order_id}`",
            reply_markup=result_kb(), parse_mode="Markdown")
        log.info(f"OK | {order_id} | UTR={utr}")

    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CallbackQueryHandler(on_pay_button, pattern=r"^pay:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text), group=1)
