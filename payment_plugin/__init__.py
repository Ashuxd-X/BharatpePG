"""UPI Payment Plugin — drop-in BharatPe payment for any python-telegram-bot project.

Quick start::

    from payment_plugin import PaymentConfig, register_payment_handlers, register_admin_handlers
    from database import init_db

    cfg = PaymentConfig(
        upi_id="yourname@bank",
        merchant_name="My Store",
        merchant_id="12345678",
        admin_ids=[123456789],
    )

    init_db(cfg)                        # sqlite file store by default — no DB setup needed
    register_payment_handlers(app, cfg)
    register_admin_handlers(app, cfg)   # optional — adds /admin + /login (OTP)

Admin runs /login (mobile → OTP) once to authenticate the merchant session.
Users /pay, scan the exact-amount QR, then send the 12-digit UTR to verify.
See README.md for the full guide.
"""

from .config import PaymentConfig
from .payment import register_payment_handlers
from .admin import register_admin_handlers

__all__ = [
    "PaymentConfig",
    "register_payment_handlers",
    "register_admin_handlers",
]
