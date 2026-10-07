# Implementation Plan — BharatPe plugin refactor (amount-match → UTR submit, OTP login, optional Postgres)

In-place refactor. Keep structure: `bharatpe.py`, `qr_generator.py`, `database.py` at root; `payment_plugin/` package; `examples/`. Net lines MUST go down. No new dependencies (stdlib + already-installed `requests` only). Mark deliberate corner-cuts with `ponytail:` comments.

Environment confirmed during exploration: Python 3.10; `sqlite3`, `requests`, `python-telegram-bot` importable; **pytest NOT installed** → the self-check is an assert-based stdlib script, not a pytest file. No AGENTS/CONTRIBUTING/steering docs exist. Capture file `bharatpe` confirms the exact OTP + transactions API shapes used below (and contains the user's live mobile/OTP/accessToken/cookies — must be deleted).

Verification evidence location: each coder step appends a short pass/fail line (command + outcome) to `.agents/tasks/bharatpe-refactor/verify.log` so the reviewer can read results without re-running. The review verdict goes to `.agents/tasks/bharatpe-refactor/review.json` as `{"verdict":"APPROVED"|"CHANGES_REQUESTED", ...}` (jsonPath `verdict`, stop value `APPROVED`).

Design decisions recorded inline (no separate design doc): sqlite chosen over JSON because it enforces the UTR UNIQUE constraint natively (guard #4); Postgres kept as an opt-in path imported lazily so no-DB import never needs psycopg2; endpoints made configurable because BharatPe just changed domains; login reuses the existing `_live`/`update_credentials()` creds slot so the poll/fetch path is untouched below the token.

Order is dependency-driven. Each item leaves the repo importable.

---

- [ ] 1. CONFIG — extend `PaymentConfig` with configurable hosts, storage selection, UTR window; drop the amount-match knobs.
      Add fields (all with defaults so everything stays injectable): `auth_host: str = "https://enterprise.bharatpe.in"`, `api_host: str = "https://api-enterprise.bharatpe.in"`, `db_url: str = ""` (empty = use file store), `db_path: str = "payments.db"` (sqlite file), `utr_window_sec: int = 1800` (recency guard). Change `bharatpe_api` to default from `api_host`: make it a property/`__post_init__` default `f"{api_host}/api/v1/merchant/transactions"` (replaces the stale `payments-tesseract...` default). Keep `upi_id, merchant_name, merchant_id, admin_ids, user_agent, timeout, min_amount, max_amount, max_per_hour, max_concurrent`. DELETE `poll_interval` (no more polling). Keep `api_token`/`api_cookie` as optional seeds (default `""`) since login now supplies them. Add `mobile: str = ""` optional (admin can also pass it at /login time).
      Files: payment_plugin/config.py
      Verify: `python -c "from payment_plugin.config import PaymentConfig; c=PaymentConfig(upi_id='a@b', merchant_name='x', merchant_id='1'); print(c.bharatpe_api, c.db_path, c.utr_window_sec)"` prints the api-enterprise URL, `payments.db`, `1800`. Append result to verify.log.

- [ ] 2. STORAGE — rewrite `database.py` as a stdlib `sqlite3` file store by default, Postgres as a lazy opt-in. No module-level psycopg2 import.
      Remove the top `import psycopg2` / `from psycopg2.extras ...`. At module load decide backend from a module global set by `init_db(cfg)`: if `cfg.db_url` starts with `postgres` → import psycopg2 lazily inside that branch; else open the sqlite file at `cfg.db_path`. Provide ONE connection helper `_conn()` that returns the active backend's connection (`sqlite3.connect(path)` with `row_factory=sqlite3.Row`, or `psycopg2.connect(url)`), and run queries through it. sqlite schema (minimal, UTR UNIQUE enforces guard #4):
      ```sql
      CREATE TABLE IF NOT EXISTS payments (
        order_id   TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        amount     REAL NOT NULL,
        status     TEXT NOT NULL DEFAULT 'PENDING',
        utr        TEXT UNIQUE,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      ```
      Keep ONLY the functions the new flow needs: `init_db(cfg)`, `insert_payment(order_id, user_id, amount)`, `get_payment(order_id)`, `claim_utr(order_id, utr)` (the guard-#4 writer — see item 4), `fail_payment(order_id)`, `admin_search(q)` (by order_id or utr), `admin_recent(limit)`. DELETE: `is_amount_in_use`, `complete_payment` (replaced by `claim_utr`), `expire_stale`, `log_activity`, all `users`/`activity_log` tables and their functions (`upsert_user`, `is_blocked`, `get_user`, `block_user`, `unblock_user`, `user_history`, `user_active_count`, `user_hourly_count`, `admin_dashboard`, `admin_users`), the `_MIGRATIONS` Postgres DO-block. `ponytail:` comment on the file store noting the ceiling (single-process, naive sqlite locking — fine for one bot; use DATABASE_URL/Postgres for multi-process).
      Note: dropping users/activity_log means middleware.py (track_user/check_blocked) and the admin dashboard/members/block/broadcast features lose their DB. See items 7 and 8 — rate-limit/blocking move to in-memory or are dropped per the settled "keep minimal" scope. Flag kept here so later items stay consistent.
      Files: database.py
      Verify: `python -c "import database; print('ok')"` succeeds with no psycopg2 installed path triggered (importing the module must not raise). Then run the item-4 self-check. Append result to verify.log.

- [ ] 3. QR — `qr_generator.py` encode the EXACT amount, drop micro-delta wording.
      No logic change beyond the docstring: `make_qr` already uses `amount` verbatim in the UPI `am=` field. Update the `amount` docstring line to say "Exact payment amount" (remove "with micro-delta"). This is a 1-line edit.
      Files: qr_generator.py
      Verify: `python -c "from payment_plugin.config import PaymentConfig; from qr_generator import make_qr; b=make_qr(500.0,'TG1','n'if False else PaymentConfig(upi_id='a@b',merchant_name='x',merchant_id='1') and 'ORD1', PaymentConfig(upi_id='a@b',merchant_name='x',merchant_id='1')); print(len(b.getvalue())>0)"` prints `True`. Append result to verify.log.

- [ ] 4. VERIFY CORE — repurpose `bharatpe.py`: delete the amount-match path, add `find_by_utr`, and add the storage-level reuse guard `claim_utr`.
      In `bharatpe.py`: DELETE `find_payment` (amount ± 0.001 path) and the now-unused `fetch_transactions_with` / `check_credentials_with` helpers (login replaces the "validate before commit" dance; see item 5). KEEP `_live`, `_get_live`, `update_credentials`, `_build_headers`, `_parse_response`, `fetch_transactions`, `CredentialsExpiredError`, `check_credentials`. Add:
      ```python
      def find_by_utr(utr, amount, cfg):
          """Return the matching received-payment txn dict for `utr`, else None.
          Guards 1-3 + 5: exists, PAYMENT_RECV+SUCCESS, amount match, recent."""
          cutoff = datetime.now(IST).timestamp() - cfg.utr_window_sec
          for tx in fetch_transactions(cfg):
              if tx.get("bankReferenceNo") != utr: continue
              if tx.get("type") != "PAYMENT_RECV" or tx.get("status") != "SUCCESS": return None
              if abs(float(tx.get("amount", 0)) - amount) >= 0.01: return None
              if int(tx.get("paymentTimestamp", 0)) / 1000 < cutoff: return None
              return {"amount": float(tx["amount"]), "utr": utr,
                      "payer_name": tx.get("payerName",""), "vpa": tx.get("payerVpa","")}
          return None
      ```
      Guard #4 (reuse) lives in `database.claim_utr(order_id, utr)` (item 2): it runs `UPDATE payments SET status='SUCCESS', utr=? WHERE order_id=? AND status='PENDING'` and relies on the `utr UNIQUE` constraint — on `sqlite3.IntegrityError` (utr already used by another order) it returns `False` without committing. Return `True` only when a row was updated. This makes "a UTR cannot verify a second order" a storage invariant, not app logic.
      Self-check (assert-based, stdlib only, no pytest): create `tests/test_utr_reuse.py` that uses a temp sqlite file, `init_db` a file-store cfg, `insert_payment` two orders, `claim_utr(order1, "UTR123")` asserts True, `claim_utr(order2, "UTR123")` asserts False (reuse blocked), and asserts order2 is still PENDING. `ponytail:` note that it hits sqlite directly (no network, no telegram).
      Files: bharatpe.py, database.py (claim_utr), tests/test_utr_reuse.py
      Verify: `python tests/test_utr_reuse.py` prints a pass line and exits 0; a reused UTR must NOT verify a second order. Append the command + outcome to verify.log.

- [ ] 5. OTP LOGIN — add three short functions to `bharatpe.py` and delete the DevTools-renew model.
      Module-level `_sessions: dict[str, requests.Session] = {}` keyed by merchant_id (holds the cookie jar from login). Add:
      ```python
      def start_login(mobile, cfg):          # steps A+B → returns uuid
          s = requests.Session()
          html = s.get(cfg.auth_host + "/", headers={"User-Agent": cfg.user_agent}, timeout=15).text
          csrf = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
          r = s.post(cfg.auth_host + "/v1/api/user/requestotp",
                     data={"mobile": mobile, "_token": csrf},
                     headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": cfg.user_agent}, timeout=15)
          d = r.json()
          _sessions[cfg.merchant_id] = s                 # keep session+csrf for step D
          s.csrf = csrf                                  # ponytail: stash csrf on the session object, one less dict
          return d["data"]["uuid"]

      def complete_login(mobile, uuid, otp, cfg):        # step D → stores accessToken as token creds
          s = _sessions[cfg.merchant_id]
          r = s.post(cfg.auth_host + "/v1/api/user/verifyotp",
                     data={"mobile": mobile, "uuid": uuid, "otp": otp, "_token": s.csrf},
                     headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": cfg.user_agent}, timeout=15)
          d = r.json()
          token = d["data"]["accessToken"]
          cookie = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
          update_credentials(token, cookie, cfg)         # reuse existing _live slot → fetch path unchanged
          return token
      ```
      Step E is the existing `fetch_transactions` (it already sends `token` header + Cookie against `cfg.bharatpe_api`, now `api-enterprise.bharatpe.in`). Input guards (trust boundary): raise a clear error if `d.get("success")` is false or `data` missing, if `mobile` isn't 10 digits, or if OTP isn't 4-6 digits — do NOT auto-read OTP anywhere. `ponytail:` note that cookie-string rebuild from the jar is a simplification (works because BharatPe only needs XSRF-TOKEN + bharatpe_session).
      Files: bharatpe.py (add `import re`)
      Verify: `python -c "import bharatpe, inspect; print(all(hasattr(bharatpe,n) for n in ['start_login','complete_login','find_by_utr','fetch_transactions']))"` prints `True`. (Live login not exercised — no real OTP in CI.) Append result to verify.log.

- [ ] 6. PAYMENT FLOW — rewrite `payment_plugin/payment.py`: QR for exact amount, then UTR submission; delete polling, micro-delta, ActiveSession, credential-alert.
      New flow in `register_payment_handlers`:
      - `cmd_pay` / amount buttons / `on_amount_text`: validate min/max, create `order_id = f"TG{int(time.time())}{int(amount*100):05d}"`, `insert_payment(order_id, user_id, amount)`, send QR via `make_qr(amount, order_id, cfg)` with caption "Pay exactly ₹X, then send me the 12-digit UTR". Store `ctx.user_data["await_utr"] = order_id`.
      - New `on_utr_text` handler: when `await_utr` set and message is a 12-digit UTR (`re.fullmatch(r"\d{12}", text)`), look up `get_payment(order_id)`, call `find_by_utr(utr, pay["amount"], cfg)`; if match, `claim_utr(order_id, utr)` → on True reply success (amount, UTR, payer), on False reply "UTR already used / mismatch"; if no match reply "not found yet, try again". Catch `CredentialsExpiredError` → tell admin to run /login.
      DELETE: `_find_free_amount`, the poll `while` loop, `ActiveSession`, `_alert_admins_credentials_expired`, `expire_stale`/`log_activity` calls, `is_amount_in_use`/`complete_payment` imports. Keep it short — collapse the old success-message branching (payer_name/handle/vpa ladder) into one line.
      Rate limiting / blocking: the users table is gone (item 2). Per settled "keep minimal", DROP the `track_user`/`check_blocked`/`check_rate_limit` middleware calls from this flow. (Item 8 deletes middleware.py.)
      Files: payment_plugin/payment.py
      Verify: `python -c "import payment_plugin.payment as p; print(hasattr(p,'register_payment_handlers'))"` prints `True`; `grep` MUST find no `find_free_amount`/`poll`/`is_amount_in_use` — but the real check is the import plus item 9's example smoke run. Append result to verify.log.

- [ ] 7. ADMIN /login — rewrite `payment_plugin/admin.py`: replace `/renewcredentials` with a two-step `/login` (mobile → OTP), locked to admin IDs; trim dashboard to what the file store supports.
      Replace `cmd_renew_credentials` + the `admin_renew_token`/`admin_renew_cookie` text branches with:
      - `cmd_login` (admin-only): set `ctx.user_data["input"]="login_mobile"`, prompt for mobile.
      - In `on_admin_text`: `login_mobile` → `uuid = start_login(text, cfg)`, stash `pending_mobile`/`pending_uuid`, set `input="login_otp"`, prompt for OTP. `login_otp` → `complete_login(pending_mobile, pending_uuid, text, cfg)`, then `check_credentials(cfg)` and report 🟢/🟡.
      Keep `/admin` panel but reduce to backends that still exist: `admin_recent` and `admin_search` (both now sqlite). DELETE dashboard/members/block/unblock/broadcast buttons + handlers (their DB is gone) OR keep only recent+search in `keyboards.admin_kb` (item 8). Register `/login` instead of `/renewcredentials`. Keep `/cancel`.
      Files: payment_plugin/admin.py
      Verify: `python -c "import payment_plugin.admin as a; print(hasattr(a,'register_admin_handlers'))"` prints `True`. Append result to verify.log.

- [ ] 8. PRUNE package glue — update `keyboards.py`, delete `middleware.py`, fix `__init__.py`.
      `keyboards.py`: trim `admin_kb` to only Recent + Search + Menu buttons (block/unblock/broadcast/dashboard/members removed in item 7); keep `amounts_kb`, `waiting_kb`→rename/keep as `result_kb` only if still used, `back_admin_kb`, `is_admin`. Remove the cancel-payment keyboard if the cancel path is gone. DELETE `payment_plugin/middleware.py` (users table removed; no track/block/rate-limit). `__init__.py`: update the docstring quickstart (no `db_url` required, no psycopg2, /login not /renewcredentials) — exports unchanged (`PaymentConfig`, `register_payment_handlers`, `register_admin_handlers`).
      Files: payment_plugin/keyboards.py, payment_plugin/__init__.py, delete payment_plugin/middleware.py
      Verify: `python -c "import payment_plugin; print(payment_plugin.__all__)"` imports cleanly and prints the three names. Append result to verify.log.

- [ ] 9. EXAMPLE — rewrite `examples/minimal_bot.py` to the new API: no DATABASE_URL required (file store default), register `/login`, show UTR flow, drop psycopg2 note.
      Env: `BOT_TOKEN`, `UPI_ID`, `MERCHANT_NAME`, `MERCHANT_ID`, `ADMIN_IDS`; optional `DATABASE_URL` (opt-in Postgres), `DB_PATH`. Call `init_db(cfg)` (now takes cfg, item 2). Keep `/start` and `nav:home` handlers. Keep it short.
      Files: examples/minimal_bot.py
      Verify: `python -c "import ast; ast.parse(open('examples/minimal_bot.py').read()); print('parses')"` prints `parses` (can't run without a bot token). Append result to verify.log.

- [ ] 10. REQUIREMENTS + PYPROJECT — clean deps, make Postgres an optional extra, fix build backend/metadata.
      `requirements.txt` → deduped core only: `python-telegram-bot>=20.0`, `requests>=2.28`, `Pillow>=9.0`, `qrcode[pil]>=7.0`. REMOVE the bogus `telegram` line (conflicts with python-telegram-bot), the duplicates, `python-dotenv` (unused), and `psycopg2-binary` (moves to extra).
      `pyproject.toml`: `build-backend = "setuptools.build_meta"`; `readme = "README.md"`; single `version = "0.1.0"` (match git tag); `[project.urls]` → `github.com/Teamhapp/bharatpe-payment-plugin`; move `psycopg2-binary>=2.9` out of `dependencies` into `[project.optional-dependencies] postgres = ["psycopg2-binary>=2.9"]`; core `dependencies` = the four above.
      Files: requirements.txt, pyproject.toml
      Verify: `python -c "import tomllib,sys; d=tomllib.load(open('pyproject.toml','rb')); assert d['build-system']['build-backend']=='setuptools.build_meta'; assert 'postgres' in d['project']['optional-dependencies']; assert d['project']['readme']=='README.md'; print('toml ok')"` prints `toml ok`. Append result to verify.log.

- [ ] 11. CLEANUP FILES — delete the Burp capture, PAYMENT_FLOW.md; prune INTEGRATION.md.
      DELETE root file `bharatpe` (live mobile/OTP/accessToken/cookies — never ship; already gitignored) and `PAYMENT_FLOW.md`. In `INTEGRATION.md`: remove sections referencing polling, micro-amount collision, shared-DB-for-collision, `/renewcredentials`, DevTools credential extraction, and the users/activity_log tables; or fold INTEGRATION.md into README.md and delete it (item 12 makes README primary). Decision: keep INTEGRATION.md only if it adds non-duplicated content after README rewrite; otherwise delete it (fewer files = lazier). Prefer DELETE and point everything at README.
      Files: delete `bharatpe`, delete `PAYMENT_FLOW.md`, delete or prune `INTEGRATION.md`
      Verify: `python -c "import os; assert not os.path.exists('bharatpe'); assert not os.path.exists('PAYMENT_FLOW.md'); print('cleaned')"` prints `cleaned`. Append result to verify.log.

- [ ] 12. DOCS — rewrite `README.md` as the primary integration guide for other bot authors.
      Sections: (1) what it is + honest caveat — UNOFFICIAL integration against BharatPe private endpoints, can break, for merchants on their OWN KYC-verified account, endpoints are configurable not hard-coded; (2) 5-minute quickstart (`register_handlers`/`register_payment_handlers`+`register_admin_handlers` with real code, file-store default so zero DB setup); (3) config/env vars table (new fields: auth_host, api_host, db_path, db_url, utr_window_sec, admin_ids, merchant_id, upi_id, merchant_name); (4) the `/login` OTP flow (mobile → bot sends to BharatPe → user types OTP → session stored; OTP entered manually, never auto-read); (5) the UTR payment+verify flow (pay exact amount via QR → send 12-digit UTR → guards 1-5 explained); (6) security section (never commit the Burp capture or session, credentials via env only, UTR UNIQUE prevents reuse); (7) deploy notes for Railway / Render / VPS (file-store default; opt into Postgres via mounted volume + `DATABASE_URL`). Remove all micro-amount / polling / renewcredentials text.
      Files: README.md
      Verify: `python -c "t=open('README.md',encoding='utf-8').read(); assert '/login' in t and 'UTR' in t and 'micro' not in t.lower() and 'renewcredentials' not in t; print('readme ok')"` prints `readme ok`. Append result to verify.log.

- [ ] 13. INTEGRATION PASS — full import + self-check + net-line check.
      Run the whole suite: import `payment_plugin`, `database`, `bharatpe`, `qr_generator` with no DB/env present (must not raise, must not need psycopg2); run `python tests/test_utr_reuse.py`; confirm `git diff --stat` shows net deletion (lines removed > added across tracked files, excluding the deleted capture). Fix any seam between the sqlite store and the handlers. Write final pass/fail summary to verify.log for the reviewer.
      Files: (whole repo, fixes only)
      Verify: `python -c "import payment_plugin, database, bharatpe, qr_generator; print('all import')"` prints `all import`; `python tests/test_utr_reuse.py` exits 0; `git diff --stat` net lines negative. Append the full summary to verify.log.

---

## Deletion summary (net lines must go DOWN)

Deleted outright: root `bharatpe` capture, `PAYMENT_FLOW.md`, `payment_plugin/middleware.py`, likely `INTEGRATION.md`.
Functions deleted: `find_payment`, `fetch_transactions_with`, `check_credentials_with` (bharatpe.py); `is_amount_in_use`, `complete_payment`, `expire_stale`, `log_activity`, all users/activity_log tables+functions, `_MIGRATIONS` DO-block, `admin_dashboard`, `admin_users`, block/unblock (database.py); `_find_free_amount`, poll loop, `ActiveSession`, `_alert_admins_credentials_expired` (payment.py); `cmd_renew_credentials` + renew text branches (admin.py).
Added (small): `find_by_utr`, `start_login`, `complete_login`, `claim_utr`, `on_utr_text`, `cmd_login`, sqlite schema, `tests/test_utr_reuse.py`.

## Assumptions / gaps
- Rate-limiting and user-blocking are DROPPED (their DB tables removed per "keep minimal"); if the user wants per-user limits back, they'd need an in-memory counter — noted, not built, since not in the settled scope.
- `claim_utr` reuse guard relies on the sqlite `UNIQUE` constraint; the Postgres path must declare the same `utr UNIQUE` for the invariant to hold there too (schema parity required when `DATABASE_URL` is used).
- Live OTP login can't be exercised in CI (no real phone/OTP); verification is import-level + the offline UTR-reuse self-check. The API shapes are taken verbatim from the confirmed Burp capture before it is deleted.
