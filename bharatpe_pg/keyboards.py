"""Keyboard layouts — labels and amount presets are configurable via cfg.ui
(see theme / UIButtons). Callback_data stays fixed (internal routing)."""

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)

# Default reply-keyboard labels (buttons send these as plain text, so the
# payment/admin on_text routers match against the SAME strings via cfg.ui).
BTN_PAY, BTN_ADMIN, BTN_LOGIN = "💳 Pay", "📊 Admin", "🔑 Login"


def is_admin(user_id: int, admin_ids: list) -> bool:
    return user_id in admin_ids


def _ui(cfg):
    from .theme import UIButtons
    return getattr(cfg, "ui", None) or UIButtons()


def menu_kb(admin: bool = False, cfg=None):
    """Persistent reply keyboard. Labels come from cfg.ui when provided."""
    u = _ui(cfg) if cfg else None
    pay = u.menu_pay if u else BTN_PAY
    rows = [[KeyboardButton(pay)]]
    if admin:
        rows.append([KeyboardButton(u.menu_admin if u else BTN_ADMIN),
                     KeyboardButton(u.menu_login if u else BTN_LOGIN)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def amounts_kb(cfg=None):
    """Amount picker. Presets + per-row count + custom label come from cfg."""
    u = _ui(cfg) if cfg else None
    presets = (getattr(cfg, "amount_presets", None) if cfg else None) or [10, 50, 100, 500, 1000, 2000]
    per_row = u.amounts_per_row if u else 3
    rows, row = [], []
    for amt in presets:
        label = f"₹{amt:g}"
        row.append(InlineKeyboardButton(label, callback_data=f"pay:{amt:g}"))
        if len(row) == per_row:
            rows.append(row); row = []
    if row:
        rows.append(row)
    if not u or u.show_custom:
        rows.append([InlineKeyboardButton(u.custom_label if u else "✏️ Custom", callback_data="pay:custom")])
    return InlineKeyboardMarkup(rows)


def result_kb(cfg=None):
    """Pay Again / Menu after a result."""
    u = _ui(cfg) if cfg else None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(u.pay_again if u else "💳 Pay Again", callback_data="pay:start")],
        [InlineKeyboardButton(u.menu_home if u else "🏠 Menu", callback_data="nav:home")],
    ])


def admin_kb():
    """Top-level admin panel keyboard (admin-facing, not themed)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Recent", callback_data="admin:recent"),
         InlineKeyboardButton("🔍 Search", callback_data="admin:search")],
        [InlineKeyboardButton("🔌 Status", callback_data="admin:status"),
         InlineKeyboardButton("🔑 Login", callback_data="admin:login")],
        [InlineKeyboardButton("🏠 Menu", callback_data="nav:home")],
    ])


def back_admin_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="admin:panel")]])
