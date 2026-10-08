"""
UPI QR card generator — fully themeable via cfg.qr_theme (see theme.QRTheme).

Pure Pillow, no external assets. An integrator can also bypass this entirely
by setting cfg.qr_renderer to their own callable(amount, order_id, cfg) -> BytesIO.
"""

import io
import qrcode
from PIL import Image, ImageDraw, ImageFont
from urllib.parse import quote
from .theme import QRTheme


def _font(name, size, fallback_bold=False):
    candidates = [n for n in (name,) if n] + (
        ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if fallback_bold else ["arial.ttf", "DejaVuSans.ttf"])
    for n in candidates:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _vgradient(w, h, top, bot):
    """Vertical gradient. ponytail: per-row fill, O(h) not O(w*h)."""
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
    """Generate a themed UPI QR card PNG. If cfg.qr_renderer is set, delegate to it."""
    if getattr(cfg, "qr_renderer", None):
        return cfg.qr_renderer(amount, order_id, cfg)

    t: QRTheme = getattr(cfg, "qr_theme", None) or QRTheme()

    upi_uri = (f"upi://pay?pa={quote(cfg.upi_id)}&am={amount:.2f}"
               f"&pn={quote(cfg.merchant_name)}&tn={quote(order_id)}")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=9, border=1)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=t.rgb("qr_dark"), back_color=t.rgb("panel")).convert("RGB")
    qr_w, qr_h = qr_img.size

    pad, header_h, panel_pad, amount_h, footer_h = 40, 92, 26, 64, 70
    has_footer = t.footer_hint or t.show_dots or t.show_order_id
    footer_h = footer_h if has_footer else 24
    panel_w = qr_w + panel_pad * 2
    card_w = panel_w + pad * 2
    card_h = header_h + amount_h + panel_pad + qr_h + panel_pad + footer_h + pad

    card = _vgradient(card_w, card_h, t.rgb("bg_top"), t.rgb("bg_bottom"))
    draw = ImageDraw.Draw(card)
    on_bg, on_accent, accent = t.rgb("text_on_bg"), t.rgb("text_on_accent"), t.rgb("accent")

    f_brand = _font(t.font_bold, 26, fallback_bold=True)
    f_tag = _font(t.font_regular, 14)
    f_amt = _font(t.font_bold, 40, fallback_bold=True)
    f_small = _font(t.font_regular, 14)
    f_order = _font(t.font_regular, 13)

    # Header: brand + tagline + underline
    draw.text((pad, 30), cfg.merchant_name, fill=on_bg, font=f_brand)
    if t.tagline:
        draw.text((pad, 64), t.tagline, fill=accent, font=f_tag)
    draw.rounded_rectangle([(pad, header_h - 6), (pad + 60, header_h - 2)], radius=2, fill=accent)

    # Amount pill
    amt_text = f"₹{amount:,.2f}"
    aw = _text_w(draw, amt_text, f_amt)
    pill_x1 = card_w - pad - (aw + 44)
    draw.rounded_rectangle([(pill_x1, 22), (card_w - pad, 78)], radius=28, fill=accent)
    draw.text((pill_x1 + 22, 30), amt_text, fill=on_accent, font=f_amt)

    # QR panel + shadow
    panel_y = header_h + amount_h
    draw.rounded_rectangle([(pad + 6, panel_y + 6), (pad + 6 + panel_w, panel_y + 6 + panel_pad * 2 + qr_h)],
                           radius=24, fill=(0, 0, 0))
    draw.rounded_rectangle([(pad, panel_y), (pad + panel_w, panel_y + panel_pad * 2 + qr_h)],
                           radius=24, fill=t.rgb("panel"))
    card.paste(qr_img, (pad + panel_pad, panel_y + panel_pad))

    # Footer
    if has_footer:
        fy = card_h - footer_h + 6
        if t.footer_hint:
            draw.text((pad, fy), t.footer_hint, fill=on_bg, font=f_small)
        if t.show_dots:
            for i, c in enumerate(t.accent_dots):
                cx = pad + i * 26
                draw.ellipse([(cx, fy + 28), (cx + 16, fy + 44)], fill=_rgb_dot(c))
        if t.show_order_id:
            draw.text((card_w - pad - _text_w(draw, order_id, f_order), fy + 30),
                      order_id, fill=t.rgb("muted"), font=f_order)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _rgb_dot(v):
    from .theme import _rgb
    return _rgb(v)
