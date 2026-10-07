"""Keyboard layouts bundled with the payment plugin."""

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)

# Persistent reply-keyboard labels (buttons send these as plain text).
BTN_PAY, BTN_ADMIN, BTN_LOGIN = "💳 Pay", "📊 Admin", "🔑 Login"


def is_admin(user_id: int, admin_ids: list) -> bool:
    """Return True if user_id is in the admin list."""
    return user_id in admin_ids


def menu_kb(admin: bool = False):
    """Persistent reply keyboard at the bottom of the chat. Admins also see
    Admin/Login. ponytail: labels double as the router keys in on_text."""
    rows = [[KeyboardButton(BTN_PAY)]]
    if admin:
        rows.append([KeyboardButton(BTN_ADMIN), KeyboardButton(BTN_LOGIN)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def amounts_kb():
    """Amount picker shown when the user taps Pay Now."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₹10", callback_data="pay:10"),
            InlineKeyboardButton("₹50", callback_data="pay:50"),
            InlineKeyboardButton("₹100", callback_data="pay:100"),
        ],
        [
            InlineKeyboardButton("₹500", callback_data="pay:500"),
            InlineKeyboardButton("₹1000", callback_data="pay:1000"),
            InlineKeyboardButton("₹2000", callback_data="pay:2000"),
        ],
        [InlineKeyboardButton("✏️ Custom", callback_data="pay:custom")],
    ])


def result_kb():
    """Pay Again / Menu buttons shown after a payment completes or expires."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay Again", callback_data="pay:start")],
        [InlineKeyboardButton("🏠 Menu", callback_data="nav:home")],
    ])


def admin_kb():
    """Top-level admin panel keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Recent", callback_data="admin:recent"),
            InlineKeyboardButton("🔍 Search", callback_data="admin:search"),
        ],
        [
            InlineKeyboardButton("🔌 Status", callback_data="admin:status"),
            InlineKeyboardButton("🔑 Login", callback_data="admin:login"),
        ],
        [InlineKeyboardButton("🏠 Menu", callback_data="nav:home")],
    ])


def back_admin_kb():
    """Single ◀️ Back button returning to the admin panel."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data="admin:panel")],
    ])
