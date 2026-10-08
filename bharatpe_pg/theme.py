"""UI customization — colours, text, fonts, amount presets, and messages.

Everything the user sees is configurable here, so integrators brand the bot
without editing plugin source. Three levels of freedom:

  1. Tweak a field on `QRTheme` / `Messages` (colours, labels, templates).
  2. Replace the whole amount grid via `PaymentConfig.amount_presets`.
  3. Full control — pass your own `PaymentConfig.qr_renderer(amount, order_id, cfg)`
     returning a PNG BytesIO, bypassing the built-in card entirely.
"""

from dataclasses import dataclass, field


def _rgb(v):
    """Accept (r,g,b) tuple or '#rrggbb' hex → (r,g,b)."""
    if isinstance(v, str):
        v = v.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(v)


@dataclass
class QRTheme:
    """Colours, text and font for the generated QR card. Colours accept either
    an (r,g,b) tuple or a '#rrggbb' hex string."""
    bg_top: object = "#1a1a2e"          # gradient start (top)
    bg_bottom: object = "#0f3460"       # gradient end (bottom)
    accent: object = "#00bfa5"          # pill + underline + tag colour
    qr_dark: object = "#1a1a2e"         # QR foreground
    panel: object = "#ffffff"           # QR panel background
    text_on_bg: object = "#ffffff"      # brand/footer text on the gradient
    text_on_accent: object = "#ffffff"  # amount text inside the pill
    muted: object = "#96a0b4"           # order-id footer colour
    accent_dots: list = field(default_factory=lambda: ["#00b894", "#0984e3", "#6c5ce7", "#fd9650"])

    tagline: str = "UPI PAYMENT REQUEST"
    footer_hint: str = "Scan with any UPI app"
    show_dots: bool = True
    show_order_id: bool = True

    # Fonts: give .ttf names/paths; the generator falls back gracefully.
    font_regular: str = ""   # "" → Arial/DejaVu auto
    font_bold: str = ""

    def rgb(self, name):
        return _rgb(getattr(self, name))


@dataclass
class UIButtons:
    """Button labels + amount-grid layout. Emoji/text are free-form."""
    menu_pay: str = "💳 Pay"
    menu_admin: str = "📊 Admin"
    menu_login: str = "🔑 Login"
    menu_home: str = "🏠 Menu"
    pay_again: str = "💳 Pay Again"
    custom_label: str = "✏️ Custom"
    show_custom: bool = True
    amounts_per_row: int = 3


@dataclass
class Messages:
    """User-facing text templates. `{amount}`, `{order_id}`, `{utr}`, `{payer}`
    are filled in. Markdown is allowed. Override any you want."""
    pay_caption: str = ("💳 *Pay exactly ₹{amount:.2f}*\n📱 Scan with any UPI app\n\n"
                        "Then send me the *12-digit UTR* from your payment app.\n📝 `{order_id}`")
    verified: str = ("✅ *Payment Verified!*\n💰 ₹{amount:.2f}\n🔗 `{utr}`\n"
                     "👤 {payer}\n📝 `{order_id}`")
    bad_utr: str = "❌ A UTR is 12 digits. Check your UPI app and resend."
    not_found: str = "❌ Not found yet (or amount/time mismatch). Wait a moment and resend."
    reused: str = "❌ This UTR was already used for another order."
    gateway_down: str = ("🛠 Payment gateway is temporarily down. Your payment is *saved* — "
                         "I'll notify you here as soon as it's verified.")
    amount_prompt: str = "Enter the amount (₹):"
    amount_picker: str = "Select amount or enter custom:"
    out_of_range: str = "❌ Amount must be ₹{min_amount:.0f}–₹{max_amount:,.0f}"
    order_gone: str = "⚠️ This order is no longer pending. Start a new payment."
