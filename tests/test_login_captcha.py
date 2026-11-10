"""Self-check: OTP-step image captcha — fetch_login_captcha + complete_login(captcha=...).

Assert-based, stdlib only, no network (fake requests.Session).
"""

import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bharatpe_pg.config import PaymentConfig
import bharatpe_pg.database as db
import bharatpe_pg.bharatpe as bp


class Resp:
    def __init__(self, status=200, ctype="image/jpeg", content=b"\xff\xd8jpg", body=None):
        self.status_code, self.headers, self.content, self._body = status, {"content-type": ctype}, content, body
    def json(self):
        return self._body


class FakeSession:
    def __init__(self, get=None, post=None):
        self._get, self._post, self.csrf, self.posted = get, post, "CSRF", None
        self.cookies = [type("C", (), {"name": "bharatpe_session", "value": "v"})()]
    def get(self, url, **kw):
        assert url.endswith("/v1/api/load-captcha") and kw["params"] == {"context": "otp"}
        assert kw["headers"]["X-Requested-With"] == "XMLHttpRequest" and kw["timeout"] == 15
        if isinstance(self._get, Exception):
            raise self._get
        return self._get
    def post(self, url, data=None, **kw):
        self.posted = data
        return self._post


def raises(fn, exc, msg=None):
    try:
        fn()
    except exc as e:
        assert msg is None or str(e).startswith(msg), f"bad message: {e}"
        return e
    raise AssertionError(f"expected {exc.__name__}")


tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
try:
    cfg = PaymentConfig(upi_id="a@b", merchant_name="x", db_path=tmp.name, merchant_id="M1")
    db.init_db(cfg)
    k = bp._key(cfg)

    # fetch_login_captcha
    bp._sessions.pop(k, None)
    raises(lambda: bp.fetch_login_captcha(cfg), RuntimeError, "no login in progress")
    bp._sessions[k] = FakeSession(get=Resp())
    assert bp.fetch_login_captcha(cfg) == b"\xff\xd8jpg"
    for bad in (Resp(ctype="text/html"), Resp(content=b""), Resp(status=500),
                requests.ConnectionError("boom")):
        bp._sessions[k] = FakeSession(get=bad)
        raises(lambda: bp.fetch_login_captcha(cfg), RuntimeError, "could not load captcha")

    # complete_login
    for c in (None, "", "   "):
        raises(lambda: bp.complete_login("9999999999", "U", "123456", cfg, captcha=c), ValueError, "captcha required")

    s = FakeSession(post=Resp(body={"success": False, "message": "ReCaptcha not verified"}))
    bp._sessions[k] = s
    e = raises(lambda: bp.complete_login("9999999999", "U", "123456", cfg, captcha="ab12"), bp.CaptchaRejected)
    assert isinstance(e, RuntimeError)
    assert s.posted == {"mobile": "9999999999", "uuid": "U", "otp": "123456",
                        "recaptcha_text": "ab12", "_token": "CSRF"}, s.posted

    bp._sessions[k] = FakeSession(post=Resp(body={"success": False, "message": "Invalid OTP"}))
    e = raises(lambda: bp.complete_login("9999999999", "U", "123456", cfg, captcha="ab12"), RuntimeError, "verifyotp failed: ")
    assert not isinstance(e, bp.CaptchaRejected)

    bp._sessions[k] = FakeSession(post=Resp(body={"success": True, "data": {"accessToken": "tokX"}}))
    assert bp.complete_login("9999999999", "U", "123456", cfg, captcha="ab12") == "tokX"
    assert bp._get_live(cfg)["token"] == "tokX" and bp._get_live(cfg)["cookie"] == "bharatpe_session=v"
    assert db.load_session()["token"] == "tokX", "session persisted"
    print("PASS: login captcha fetch + verifyotp recaptcha_text + CaptchaRejected")
finally:
    os.unlink(tmp.name)
