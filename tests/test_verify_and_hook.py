"""Self-checks for the two new primitives:

1. verify_utr returns ok once, then 'reused' for the same UTR on a new order
   (reuse guard holds for the standalone path too).
2. the on_verified hook fires exactly once per paid order, with the right data.

Assert-based, stdlib only — fakes BharatPe, no network/telegram.
"""

import os, sys, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bharatpe_pg.config import PaymentConfig
import bharatpe_pg.database as db
import bharatpe_pg.verify as verify
import bharatpe_pg.delivery as delivery

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
try:
    cfg = PaymentConfig(upi_id="a@b", merchant_name="x", db_path=tmp.name)
    db.init_db(cfg)

    # Fake BharatPe: UTR 100000000001 is a real ₹100 payment.
    verify.find_by_utr = lambda utr, amount, cfg: (
        {"amount": 100.0, "utr": utr, "payer_name": "Ravi", "vpa": "ravi@upi"}
        if utr == "100000000001" and abs(amount - 100.0) < 0.01 else None)

    # 1a. first verify succeeds
    r = verify.verify_utr("100000000001", 100.0, "topup-1", 777, cfg)
    assert r.ok and r.reason == "verified" and r.payer_name == "Ravi", r

    # 1b. same UTR on a different order → reused
    r2 = verify.verify_utr("100000000001", 100.0, "topup-2", 777, cfg)
    assert (not r2.ok) and r2.reason == "reused", r2

    # 1c. a UTR BharatPe doesn't know → not_found; bad format → bad_utr
    assert verify.verify_utr("100000000009", 100.0, "topup-3", 777, cfg).reason == "not_found"
    assert verify.verify_utr("12", 100.0, "topup-4", 777, cfg).reason == "bad_utr"

    # 2. on_verified fires exactly once with the order payload
    calls = []
    async def hook(bot, order): calls.append(order)
    cfg.on_verified = hook
    asyncio.run(delivery.deliver("BOT", cfg, {"user_id": 1, "amount": 50.0, "order_id": "o", "utr": "u"}))
    assert len(calls) == 1 and calls[0]["amount"] == 50.0 and calls[0]["user_id"] == 1, calls

    # 2b. a hook that raises must not propagate (delivery never breaks verification)
    async def boom(bot, order): raise RuntimeError("delivery blew up")
    cfg.on_verified = boom
    asyncio.run(delivery.deliver("BOT", cfg, {"order_id": "o2"}))   # should swallow, not raise

    print("PASS: verify_utr guards hold (verified/reused/not_found/bad_utr); on_verified fires once & is crash-safe")
finally:
    os.unlink(tmp.name)
