"""PaymentConfig — injectable configuration for the UPI payment plugin."""

from dataclasses import dataclass, field


@dataclass
class PaymentConfig:
    """All settings needed to run the UPI payment system in any Telegram bot.

    Required fields have no default and must always be supplied. Everything
    else defaults to BharatPe's current setup and is injectable (hosts,
    storage, UTR recency window, admin IDs).

    Example::

        from payment_plugin import PaymentConfig, register_payment_handlers
        from database import init_db

        cfg = PaymentConfig(
            upi_id="yourname@bank",
            merchant_name="My Store",
            merchant_id="12345678",
            admin_ids=[123456789],
        )
        init_db(cfg)
        register_payment_handlers(app, cfg)
    """

    # ── Merchant identity ──────────────────────────────────────────────────
    upi_id: str
    merchant_name: str
    merchant_id: str

    # ── BharatPe hosts (configurable — the domain changed recently) ─────────
    auth_host: str = "https://enterprise.bharatpe.in"
    api_host: str = "https://api-enterprise.bharatpe.in"
    bharatpe_api: str = ""  # set from api_host in __post_init__ unless overridden
    user_agent: str = (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36"
    )

    # Optional credential seeds — /login normally supplies these at runtime.
    api_token: str = ""
    api_cookie: str = ""
    mobile: str = ""

    # ── Storage: file store by default, Postgres when db_url points at it ───
    db_url: str = ""            # empty = sqlite file store
    db_path: str = "payments.db"

    # ── Payment behaviour ──────────────────────────────────────────────────
    utr_window_sec: int = 1800  # UTR recency guard (default: 30 min)
    min_amount: float = 1.0
    max_amount: float = 50000.0
    timeout: int = 300          # QR caption hint only (no polling anymore)

    # ── Admin Telegram user IDs ─────────────────────────────────────────────
    admin_ids: list[int] = field(default_factory=list)

    def __post_init__(self):
        self.bharatpe_api = self.bharatpe_api or f"{self.api_host}/api/v1/merchant/transactions"
