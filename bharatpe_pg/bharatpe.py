"""BharatPe transaction API + OTP login.

All functions take a PaymentConfig (fields merchant_id, user_agent, auth_host,
bharatpe_api, utr_window_sec, api_token, api_cookie). Credentials live per
merchant_id so several bots can share one process. /login (OTP) supplies the
token+cookies at runtime via update_credentials().
"""

import re
import logging
import requests
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger(__name__)

_live: dict[str, dict] = {}                       # merchant_id -> {token, cookie}
_sessions: dict[str, requests.Session] = {}       # merchant_id -> login session (cookie jar)


class CredentialsExpiredError(Exception):
    """Raised when BharatPe rejects the token/cookie (session expired)."""


def _key(cfg):
    # ponytail: key creds by the config object's identity, not merchant_id —
    # merchant_id is empty until /login auto-discovers it, so it can't be the key.
    return id(cfg)


def _get_live(cfg) -> dict:
    return _live.setdefault(_key(cfg), {"token": cfg.api_token, "cookie": cfg.api_cookie})


def has_session(cfg) -> bool:
    """True once a token exists (via /login or an api_token seed) — i.e. a
    verification is even possible. False means nobody has logged in yet."""
    return bool(_get_live(cfg)["token"])


def update_credentials(token: str, cookie: str, cfg) -> None:
    """Replace the active BharatPe credentials at runtime AND persist them, so a
    redeploy/restart stays logged in (no re-OTP every deploy)."""
    slot = _get_live(cfg)
    slot["token"], slot["cookie"] = token.strip(), cookie.strip()
    from .database import save_session
    save_session(slot["token"], slot["cookie"], cfg.merchant_id)
    logger.info(f"BharatPe credentials updated + persisted for merchant {cfg.merchant_id}")


def load_persisted_session(cfg) -> bool:
    """Restore a saved session into memory on startup. Returns True if one was
    found. Call once after init_db so the bot survives redeploys without re-login."""
    from .database import load_session
    s = load_session()
    if not s or not s.get("token"):
        return False
    slot = _get_live(cfg)
    slot["token"], slot["cookie"] = s["token"], s.get("cookie", "")
    if s.get("merchant_id") and not cfg.merchant_id:
        cfg.merchant_id = s["merchant_id"]
    logger.info("Restored persisted BharatPe session")
    return True


def _build_headers(cfg) -> dict:
    slot = _get_live(cfg)
    return {"token": slot["token"], "Cookie": slot["cookie"], "User-Agent": cfg.user_agent}


def _parse_response(resp: requests.Response) -> list:
    # Transactions API uses status+message:"SUCCESS"; some endpoints use success:true.
    data = resp.json()
    if (data.get("status") and data.get("message") == "SUCCESS") or data.get("success"):
        return data.get("data", {}).get("transactions", [])
    msg = data.get("message", "UNKNOWN")
    logger.warning(f"BharatPe API error: {msg} (HTTP {resp.status_code})")
    if msg in ("UNAUTHORIZED", "UNAUTHENTICATED", "TOKEN_EXPIRED", "SESSION_EXPIRED") \
            or resp.status_code in (401, 403):
        raise CredentialsExpiredError(msg)
    # ponytail: any other non-SUCCESS (incl. "Not Found", 404) is a real failure —
    # raise so check_credentials can't report a dead endpoint as healthy.
    raise RuntimeError(f"BharatPe transactions call failed: {msg} (HTTP {resp.status_code})")


def fetch_transactions(cfg) -> list:
    """Fetch recent QR payment transactions. Raises CredentialsExpiredError if
    the token/cookie is rejected; requests.RequestException on network errors."""
    now = datetime.now(IST)
    params = {"module": "PAYMENT_QR",
              "sDate": int((now - timedelta(days=2)).timestamp() * 1000),   # epoch ms
              "eDate": int((now + timedelta(days=1)).timestamp() * 1000),
              "pageSize": 50, "pageCount": 0, "isFromOtDashboard": 1}
    if cfg.merchant_id:                      # dashboard sends merchantId only when known
        params["merchantId"] = cfg.merchant_id
    resp = requests.get(cfg.bharatpe_api, params=params, headers=_build_headers(cfg), timeout=15)
    return _parse_response(resp)


def find_by_utr(utr: str, amount: float, cfg) -> dict | None:
    """Return the matching received-payment txn for `utr`, else None.
    Guards 1-3 + 5: exists, PAYMENT_RECV+SUCCESS, amount match, recent."""
    cutoff = datetime.now(IST).timestamp() - cfg.utr_window_sec
    for tx in fetch_transactions(cfg):
        if tx.get("bankReferenceNo") != utr:
            continue
        if tx.get("type") != "PAYMENT_RECV" or tx.get("status") != "SUCCESS":
            return None
        if abs(float(tx.get("amount", 0)) - amount) >= 0.01:
            return None
        if int(tx.get("paymentTimestamp", 0)) / 1000 < cutoff:
            return None
        return {"amount": float(tx["amount"]), "utr": utr,
                "payer_name": tx.get("payerName", ""), "vpa": tx.get("payerVpa", "")}
    return None


def check_credentials(cfg) -> str:
    """'ok' | 'expired' | 'unknown' — lightweight session health check."""
    try:
        fetch_transactions(cfg); return "ok"
    except CredentialsExpiredError:
        return "expired"
    except Exception as e:
        logger.warning(f"check_credentials: BharatPe unreachable: {e}")
        return "unknown"


# ── OTP login (phone + OTP; OTP is always entered manually, never auto-read) ──

def start_login(mobile: str, cfg) -> str:
    """GET auth_host to grab the CSRF token + cookies, POST requestotp, return uuid."""
    if not re.fullmatch(r"\d{10}", mobile):
        raise ValueError("mobile must be 10 digits")
    s = requests.Session()
    html = s.get(cfg.auth_host + "/", headers={"User-Agent": cfg.user_agent}, timeout=15).text
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not m:
        raise RuntimeError("could not scrape csrf-token from BharatPe page")
    csrf = m.group(1)
    r = s.post(cfg.auth_host + "/v1/api/user/requestotp",
               data={"mobile": mobile, "_token": csrf},
               headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": cfg.user_agent}, timeout=15)
    d = r.json()
    if not d.get("success") or "uuid" not in d.get("data", {}):
        raise RuntimeError(f"requestotp failed: {d.get('message', d)}")
    s.csrf = csrf                       # ponytail: stash csrf on the session, saves a dict
    _sessions[_key(cfg)] = s
    return d["data"]["uuid"]


def complete_login(mobile: str, uuid: str, otp: str, cfg) -> str:
    """POST verifyotp, store accessToken + login cookies as the active session."""
    if not re.fullmatch(r"\d{4,6}", otp):
        raise ValueError("otp must be 4-6 digits")
    s = _sessions.get(_key(cfg))
    if s is None:
        raise RuntimeError("no login in progress — call start_login first")
    r = s.post(cfg.auth_host + "/v1/api/user/verifyotp",
               data={"mobile": mobile, "uuid": uuid, "otp": otp, "_token": s.csrf},
               headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": cfg.user_agent}, timeout=15)
    d = r.json()
    if not d.get("success") or "accessToken" not in d.get("data", {}):
        raise RuntimeError(f"verifyotp failed: {d.get('message', d)}")
    # ponytail: rebuild the Cookie header from the jar — works because BharatPe
    # only needs XSRF-TOKEN + bharatpe_session, no path/domain nuance.
    cookie = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
    token = d["data"]["accessToken"]
    update_credentials(token, cookie, cfg)
    if not cfg.merchant_id:                  # auto-discover — BharatPe hides it in the UI
        try:
            cfg.merchant_id = fetch_merchant_id(cfg)
            logger.info(f"Discovered merchant_id {cfg.merchant_id} via getmerchantinfo")
        except Exception as e:
            logger.warning(f"could not auto-fetch merchant_id: {e}")
    return token


def fetch_merchant_id(cfg) -> str:
    """GET getmerchantinfo (token header) and return the account's merchantId.
    Lets users skip MERCHANT_ID entirely — BharatPe never shows it in the UI."""
    r = requests.get("https://api-merchant.bharatpe.in/merchant/v3/getmerchantinfo",
                     headers={"token": _get_live(cfg)["token"], "User-Agent": cfg.user_agent}, timeout=15)
    mid = r.json().get("data", {}).get("merchantId")
    if not mid:
        raise RuntimeError("merchantId missing from getmerchantinfo response")
    return str(mid)
