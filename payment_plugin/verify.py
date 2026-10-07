"""Standalone UTR verification — for bots with their own payment UI.

One call runs all five guards plus the reuse guard and returns a plain result,
so a dev can bolt BharatPe verification onto any flow (credits top-up,
pay-per-use, a custom QR screen) without adopting the /pay handlers.

    from payment_plugin import verify_utr, PaymentConfig, init_db
    init_db(cfg)
    r = verify_utr("664700063288", 100.0, order_id="topup-42", user_id=123, cfg=cfg)
    if r.ok:
        add_credits(123, int(100 * RATE))   # your rule; the plugin just vouches for the money
"""

import re
import logging
from dataclasses import dataclass
from .bharatpe import find_by_utr, CredentialsExpiredError
from .database import ensure_payment, claim_utr

log = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    ok: bool
    reason: str                 # 'verified' | 'bad_utr' | 'not_found' | 'reused' | 'gateway_down' | 'error'
    payer_name: str = ""
    vpa: str = ""


def verify_utr(utr: str, amount: float, order_id: str, user_id: int, cfg) -> VerifyResult:
    """Verify a UTR for `amount` and bind it to `order_id` (reuse-safe).

    order_id must be unique per sale — reusing one that's already SUCCESS, or a
    UTR already claimed elsewhere, returns ok=False. Returns, never raises.
    """
    utr = utr.replace(" ", "")
    if not re.fullmatch(r"\d{12}", utr):              # trust boundary
        return VerifyResult(False, "bad_utr")
    ensure_payment(order_id, user_id, amount)         # idempotent — safe to call repeatedly
    try:
        match = find_by_utr(utr, amount, cfg)
    except CredentialsExpiredError:
        return VerifyResult(False, "gateway_down")
    except Exception as e:
        log.error(f"verify_utr lookup failed: {e}")
        return VerifyResult(False, "error")
    if not match:
        return VerifyResult(False, "not_found")
    if not claim_utr(order_id, utr):                  # reuse guard (utr UNIQUE)
        return VerifyResult(False, "reused")
    return VerifyResult(True, "verified", match.get("payer_name", ""), match.get("vpa", ""))
