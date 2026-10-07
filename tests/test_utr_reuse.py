"""Self-check: a UTR that verified one order cannot verify a second (guard #4).

Assert-based, stdlib only (no pytest/fixtures). ponytail: hits the sqlite store
directly — no network, no telegram — because the reuse guard is a storage
invariant (utr UNIQUE), not app logic.
"""

import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payment_plugin.config import PaymentConfig
import payment_plugin.database as db

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
try:
    cfg = PaymentConfig(upi_id="a@b", merchant_name="x", merchant_id="1", db_path=tmp.name)
    db.init_db(cfg)
    db.insert_payment("ORD1", 111, 500.0)
    db.insert_payment("ORD2", 222, 500.0)

    assert db.claim_utr("ORD1", "123456789012") is True, "first claim should succeed"
    assert db.claim_utr("ORD2", "123456789012") is False, "reused UTR must be rejected"
    assert db.get_payment("ORD2")["status"] == "PENDING", "ORD2 must stay PENDING"
    assert db.get_payment("ORD1")["status"] == "SUCCESS"
    print("PASS: reused UTR cannot verify a second order")
finally:
    os.unlink(tmp.name)
