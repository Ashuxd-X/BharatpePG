"""Self-check: a session saved by update_credentials survives a 'restart'
(fresh in-memory state) via load_persisted_session — so redeploys stay logged in.

Assert-based, stdlib only, no network.
"""

import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payment_plugin.config import PaymentConfig
import payment_plugin.database as db
import payment_plugin.bharatpe as bp

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
try:
    cfg = PaymentConfig(upi_id="a@b", merchant_name="x", db_path=tmp.name)
    db.init_db(cfg)

    assert bp.has_session(cfg) is False, "fresh install has no session"
    assert bp.load_persisted_session(cfg) is False, "nothing to restore yet"

    bp.update_credentials("tok123", "cookieZ", cfg)   # like a /login, persists to DB
    assert bp.has_session(cfg) is True

    # Simulate a redeploy: wipe in-memory creds, new config object.
    bp._live.clear()
    cfg2 = PaymentConfig(upi_id="a@b", merchant_name="x", db_path=tmp.name)
    db.init_db(cfg2)
    assert bp.has_session(cfg2) is False, "memory cleared on restart"

    assert bp.load_persisted_session(cfg2) is True, "session restored from DB"
    assert bp.has_session(cfg2) is True
    assert bp._get_live(cfg2)["token"] == "tok123", "restored the right token"
    print("PASS: session persists across restart — no re-login per deploy")
finally:
    os.unlink(tmp.name)
