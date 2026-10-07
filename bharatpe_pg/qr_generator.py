"""
UPI QR Code Generator — professional branded QR cards for Telegram.

Pure Pillow (stdlib + already-installed deps), no external image assets:
a dark gradient canvas, a rounded white QR panel, a gradient brand header,
an amount pill, and a UPI-app accent strip.
"""

import io
import qrcode
from PIL import Image, ImageDraw, ImageFont
from urllib.parse import quote

# Palette
BG_TOP, BG_BOT = (26, 26, 46), (15, 52, 96)      # deep indigo → blue gradient
ACCENT = (0, 191, 165)                            # teal accent
QR_DARK = (26, 26, 46)
WHITE = (255, 255, 255)
MUTED = (150, 160, 180)
UPI_DOTS = [(0, 184, 148), (9, 132, 227), (108, 92, 231), (253, 150, 68)]  # app-ish accents


def _font(size, bold=False):
    for name in ((["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else []) +
                 ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _vgradient(w, h, top, bot):
    """Vertical gradient as an RGB image. ponytail: per-row fill, O(h) not O(w*h)."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return img


def _text_w(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def make_qr(amount: float, order_id: str, cfg) -> io.BytesIO:
    """Generate a professional branded UPI QR card PNG.

    Args:
        amount:   Exact payment amount.
        order_id: Unique order identifier embedded in the UPI note field.
        cfg:      PaymentConfig — provides upi_id and merchant_name.

    Returns:
        BytesIO buffer containing the PNG image.
    """
    upi_uri = (f"upi://pay?pa={quote(cfg.upi_id)}&am={amount:.2f}"
               f"&pn={quote(cfg.merchant_name)}&tn={quote(order_id)}")

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=9, border=1)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=QR_DARK, back_color=WHITE).convert("RGB")
    qr_w, qr_h = qr_img.size

    # Layout
    pad = 40
    header_h = 92
    panel_pad = 26          # white panel inset around the QR
    amount_h = 64
    footer_h = 70
    panel_w = qr_w + panel_pad * 2
    card_w = panel_w + pad * 2
    card_h = header_h + amount_h + panel_pad + qr_h + panel_pad + footer_h + pad

    card = _vgradient(card_w, card_h, BG_TOP, BG_BOT)
    draw = ImageDraw.Draw(card)

    f_brand = _font(26, bold=True)
    f_tag = _font(14)
    f_amt = _font(40, bold=True)
    f_small = _font(14)
    f_order = _font(13)

    # ── Header: brand name + accent underline ──
    draw.text((pad, 30), cfg.merchant_name, fill=WHITE, font=f_brand)
    draw.text((pad, 64), "UPI PAYMENT REQUEST", fill=ACCENT, font=f_tag)
    draw.rounded_rectangle([(pad, header_h - 6), (pad + 60, header_h - 2)], radius=2, fill=ACCENT)

    # ── Amount pill (right-aligned, teal) ──
    amt_text = f"₹{amount:,.2f}"
    aw = _text_w(draw, amt_text, f_amt)
    pill_w = aw + 44
    pill_x1 = card_w - pad - pill_w
    draw.rounded_rectangle([(pill_x1, 22), (card_w - pad, 22 + 56)], radius=28, fill=ACCENT)
    draw.text((pill_x1 + 22, 30), amt_text, fill=WHITE, font=f_amt)

    # ── White rounded QR panel with soft shadow ──
    panel_y = header_h + amount_h
    sx, sy = pad + 6, panel_y + 6
    draw.rounded_rectangle([(sx, sy), (sx + panel_w, sy + panel_pad * 2 + qr_h)],
                           radius=24, fill=(0, 0, 0))                       # shadow
    px, py = pad, panel_y
    draw.rounded_rectangle([(px, py), (px + panel_w, py + panel_pad * 2 + qr_h)],
                           radius=24, fill=WHITE)
    card.paste(qr_img, (px + panel_pad, py + panel_pad))

    # ── Footer: scan hint + UPI accent dots + order id ──
    fy = card_h - footer_h + 6
    draw.text((pad, fy), "Scan with any UPI app", fill=WHITE, font=f_small)
    dot_x = pad
    for i, c in enumerate(UPI_DOTS):
        cx = dot_x + i * 26
        draw.ellipse([(cx, fy + 28), (cx + 16, fy + 44)], fill=c)
    order_text = order_id
    draw.text((card_w - pad - _text_w(draw, order_text, f_order), fy + 30),
              order_text, fill=MUTED, font=f_order)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf
