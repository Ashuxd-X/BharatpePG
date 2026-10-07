"""Self-check: a UTR queued during an outage is verified and claimed on recovery,
and a queued UTR that BharatPe never confirms is failed (not re-notified forever).

Assert-based, stdlib only — fakes BharatPe + the bot so no network/telegram.
"""

import os, sys, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payment_plugin.config import PaymentConfig
import payment_plugin.database as db
import payment_plugin.session_monitor as sm

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
try:
    cfg = PaymentConfig(upi_id="a@b", merchant_name="x", db_path=tmp.name)
    db.init_db(cfg)
    db.insert_payment("ORD_OK", 111, 500.0)
    db.insert_payment("ORD_BAD", 222, 500.0)
    db.queue_utr("ORD_OK", "100000000001")
    db.queue_utr("ORD_BAD", "100000000002")
    assert len(db.queued_payments()) == 2

    # Fake BharatPe: only ORD_OK's utr is a real payment.
    sm.find_by_utr = lambda utr, amount, cfg: (
        {"amount": 500.0, "utr": utr, "payer_name": "T", "vpa": ""} if utr == "100000000001" else None)

    class Bot:
        def __init__(self): self.sent = []
        async def send_message(self, uid, text, **k): self.sent.append((uid, text))

    bot = Bot()
    asyncio.run(sm._drain_queue(bot, cfg))

    assert db.get_payment("ORD_OK")["status"] == "SUCCESS", "verified order must be SUCCESS"
    assert db.get_payment("ORD_BAD")["status"] == "FAILURE", "unconfirmed order must fail, not re-queue"
    assert db.queued_payments() == [], "queue must be empty after drain"
    assert any("Verified" in t for _, t in bot.sent) and any("couldn't verify" in t for _, t in bot.sent)
    print("PASS: queue drains — verified claimed, unconfirmed failed, users notified")
finally:
    os.unlink(tmp.name)
