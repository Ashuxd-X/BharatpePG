"""UPI Payment Plugin — drop-in BharatPe payment for any python-telegram-bot project.

Quick start::

    from payment_plugin import (
        PaymentConfig, init_db,
        register_payment_handlers, register_admin_handlers,
    )

    cfg = PaymentConfig(
        upi_id="yourname@bank",
        merchant_name="My Store",
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
from .database import init_db
from .payment import register_payment_handlers
from .admin import register_admin_handlers
from .session_monitor import start_session_monitor
from .verify import verify_utr, VerifyResult

__all__ = [
    "PaymentConfig",
    "init_db",
    "register_payment_handlers",
    "register_admin_handlers",
    "start_session_monitor",
    "verify_utr",
    "VerifyResult",
]
