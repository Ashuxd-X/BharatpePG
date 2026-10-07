"""Fire the integrator's on_verified hook exactly once per paid order.

Called from both success paths (instant verify in payment.py, post-outage
drain in session_monitor.py) so delivery happens regardless of timing. Must
run only AFTER claim_utr succeeds, so one UTR → one claim → one delivery.
"""

import logging

log = logging.getLogger(__name__)


async def deliver(bot, cfg, order):
    """Invoke cfg.on_verified(bot, order) if set. Never raises — a failing
    delivery is logged, not allowed to break verification/notification."""
    if not cfg.on_verified:
        return
    try:
        await cfg.on_verified(bot, order)
    except Exception as e:
        log.error(f"on_verified failed for {order.get('order_id')}: {e}")
