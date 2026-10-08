"""Admin handlers — /login (OTP), recent payments, search. Admin-only."""

import logging
from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from .database import admin_recent, admin_search
from .bharatpe import check_credentials, start_login, complete_login, has_session
from .session_monitor import session_restored
from .config import PaymentConfig
from .keyboards import admin_kb, back_admin_kb, is_admin
from .theme import UIButtons

log = logging.getLogger(__name__)


def register_admin_handlers(app, cfg: PaymentConfig):
    """Register admin-only handlers (/admin, /login, /cancel), closed over cfg."""
    _ui = getattr(cfg, "ui", None) or UIButtons()
    BTN_ADMIN, BTN_LOGIN = _ui.menu_admin, _ui.menu_login

    def _admin(uid):
        return is_admin(uid, cfg.admin_ids)

    async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _admin(update.effective_user.id):
            await update.message.reply_text("🚫 Unauthorized."); return
        await update.message.reply_text("🔐 *Admin Panel*", reply_markup=admin_kb(), parse_mode="Markdown")

    async def cmd_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _admin(update.effective_user.id):
            await update.message.reply_text("🚫 Unauthorized."); return
        ctx.user_data["input"] = "login_mobile"
        await update.message.reply_text(
            "🔑 *BharatPe Login*\nStep 1/2 — send your 10-digit mobile number.\n/cancel to abort.",
            parse_mode="Markdown")

    async def on_admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        if not _admin(q.from_user.id):
            await q.message.reply_text("🚫 Unauthorized."); return
        _, action = q.data.split(":", 1)
        if action == "panel":
            await q.message.reply_text("🔐 *Admin Panel*", reply_markup=admin_kb(), parse_mode="Markdown")
        elif action == "recent":
            rows = admin_recent(10)
            if not rows:
                await q.message.reply_text("No payments.", reply_markup=back_admin_kb()); return
            lines = ["💰 *Recent Payments*\n"]
            for r in rows:
                icon = {"SUCCESS": "✅", "FAILURE": "❌", "PENDING": "⏳"}.get(r["status"], "❓")
                utr = f" `{r['utr']}`" if r.get("utr") else ""
                lines.append(f"{icon} ₹{r['amount']:.2f} `{r['user_id']}` {r['created_at']}{utr}")
            await q.message.reply_text("\n".join(lines), reply_markup=back_admin_kb(), parse_mode="Markdown")
        elif action == "search":
            ctx.user_data["input"] = "admin_search"
            await q.message.reply_text("🔍 Enter Order ID or UTR:")
        elif action == "status":
            if not has_session(cfg):
                msg = "🔴 *Not logged in.*\nTap 🔑 Login to connect your BharatPe account."
            else:
                live = {"ok": "🟢 Logged in — BharatPe API responding.",
                        "expired": "🔴 Session expired — tap 🔑 Login to reconnect.",
                        "unknown": "🟡 Logged in, but BharatPe is unreachable right now."}[check_credentials(cfg)]
                msg = f"*BharatPe Status*\n{live}"
            await q.message.reply_text(msg, reply_markup=back_admin_kb(), parse_mode="Markdown")
        elif action == "login":
            ctx.user_data["input"] = "login_mobile"
            await q.message.reply_text(
                "🔑 *BharatPe Login*\nStep 1/2 — send your 10-digit mobile number.\n/cancel to abort.",
                parse_mode="Markdown")

    async def on_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if text in (BTN_ADMIN, BTN_LOGIN):            # reply-keyboard shortcuts (admin-only)
            if not _admin(update.effective_user.id):
                return
            if text == BTN_ADMIN:
                await update.message.reply_text("🔐 *Admin Panel*", reply_markup=admin_kb(), parse_mode="Markdown")
            else:
                await cmd_login(update, ctx)
            return
        inp = ctx.user_data.get("input", "")
        if inp not in ("login_mobile", "login_otp", "admin_search") or not _admin(update.effective_user.id):
            return
        ctx.user_data.pop("input", None)

        if inp == "login_mobile":
            try:
                ctx.user_data["login_mobile"] = text
                ctx.user_data["login_uuid"] = start_login(text, cfg)
            except Exception as e:
                await update.message.reply_text(f"❌ Could not request OTP: {e}"); return
            ctx.user_data["input"] = "login_otp"
            await update.message.reply_text("📲 Step 2/2 — enter the OTP sent to your phone.")

        elif inp == "login_otp":
            try:
                complete_login(ctx.user_data.pop("login_mobile"), ctx.user_data.pop("login_uuid"), text, cfg)
            except Exception as e:
                await update.message.reply_text(f"❌ Login failed: {e}"); return
            session_restored()      # clear the expiry alert so the next outage warns again
            state = {"ok": "🟢 Connected", "expired": "🔴 Rejected", "unknown": "🟡 Unreachable"}[check_credentials(cfg)]
            await update.message.reply_text(f"✅ Logged in. BharatPe API: {state}",
                                            reply_markup=back_admin_kb())

        elif inp == "admin_search":
            r = admin_search(text)
            if not r:
                await update.message.reply_text(f"❌ Not found: `{text}`", parse_mode="Markdown",
                                                reply_markup=back_admin_kb()); return
            icon = {"SUCCESS": "✅", "FAILURE": "❌", "PENDING": "⏳"}.get(r["status"], "❓")
            await update.message.reply_text(
                f"🔍 *Payment*\n{icon} *{r['status']}*\n📝 `{r['order_id']}`\n💰 ₹{r['amount']:.2f}\n"
                f"👤 `{r['user_id']}`\n🔗 `{r.get('utr') or '—'}`\n🕐 {r['created_at']}",
                reply_markup=back_admin_kb(), parse_mode="Markdown")

    async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if ctx.user_data.pop("input", None):
            ctx.user_data.pop("login_mobile", None); ctx.user_data.pop("login_uuid", None)
            await update.message.reply_text("❌ Cancelled.", reply_markup=back_admin_kb())

    app.add_handler(CommandHandler(cfg.cmd_admin, cmd_admin))
    app.add_handler(CommandHandler(cfg.cmd_login, cmd_login))
    app.add_handler(CommandHandler(cfg.cmd_cancel, cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_admin_button, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_text), group=2)
