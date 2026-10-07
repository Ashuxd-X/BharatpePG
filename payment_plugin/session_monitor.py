"""Background session-health monitor.

A JobQueue job (in-process, no OS cron — the BharatPe session lives in this
process's memory) polls check_credentials on an interval and DMs admins ONCE
when the session goes bad, so expiry is caught before a customer hits it.
Users never see "session expired" — the payment handler stays neutral.
"""

import logging
from telegram.ext import ContextTypes
from .bharatpe import check_credentials, find_by_utr, CredentialsExpiredError
from .database import queued_payments, claim_utr, fail_payment
from .delivery import deliver

log = logging.getLogger(__name__)

# ponytail: module-level flags, one bot per process. Multi-tenant would key by cfg.
_alerted = False     # True once admins warned for the current outage (de-dupes)


async def _alert_admins(bot, cfg, text):
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, text, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"could not alert admin {aid}: {e}")


async def _check_job(ctx: ContextTypes.DEFAULT_TYPE):
    cfg = ctx.job.data
    global _alerted
    state = check_credentials(cfg)          # 'ok' | 'expired' | 'unknown'
    if state == "expired" and not _alerted:
        _alerted = True
        await _alert_admins(ctx.bot,
            cfg, "⚠️ *BharatPe session expired.*\nRun /login to restore payment verification.")
        log.warning("session expired — admin alert sent")
    elif state == "ok" and _alerted:
        _alerted = False                    # recovered (e.g. admin re-logged in)
        log.info("session healthy again")
        await _drain_queue(ctx.bot, cfg)


async def _drain_queue(bot, cfg):
    """Verify UTRs queued during the outage and notify each user of the result."""
    for p in queued_payments():
        try:
            match = find_by_utr(p["pending_utr"], p["amount"], cfg)
        except CredentialsExpiredError:
            return                          # session died again mid-drain; retry next cycle
        except Exception as e:
            log.warning(f"queue verify failed for {p['order_id']}: {e}")
            continue
        ok = match and claim_utr(p["order_id"], p["pending_utr"])
        if not ok:
            fail_payment(p["order_id"])     # leave the queue so we don't re-notify forever
        text = (f"✅ *Payment Verified!*\n💰 ₹{p['amount']:.2f}\n🔗 `{p['pending_utr']}`\n📝 `{p['order_id']}`"
                if ok else
                f"❌ We couldn't verify order `{p['order_id']}`. If you paid, contact support.")
        try:
            await bot.send_message(p["user_id"], text, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"could not notify {p['user_id']}: {e}")
        if ok:                              # deliver AFTER the claim — once per paid order
            await deliver(bot, cfg,
                          {"user_id": p["user_id"], "amount": p["amount"],
                           "order_id": p["order_id"], "utr": p["pending_utr"]})


def session_healthy() -> bool:
    """False while we're in a known outage (admins alerted, awaiting /login)."""
    return not _alerted


def session_restored():
    """Call after a successful /login so the next expiry alerts again."""
    global _alerted
    _alerted = False


def start_session_monitor(app, cfg):
    """Register the repeating health check. Interval = cfg.session_check_sec."""
    if app.job_queue is None:
        log.warning("JobQueue unavailable — install python-telegram-bot[job-queue]; "
                    "session monitor disabled")
        return
    app.job_queue.run_repeating(_check_job, interval=cfg.session_check_sec,
                                first=cfg.session_check_sec, data=cfg)
    log.info(f"Session monitor every {cfg.session_check_sec}s")
