# Verification — BharatPe plugin refactor (first iteration)

Environment: Windows / PowerShell, CPython 3.10.0. Core deps installed into the
interpreter for the import checks (`python-telegram-bot`, `requests`, `Pillow`,
`qrcode[pil]`). `psycopg2` is NOT installed — proving the no-DB import path works.

## 1. Every .py parses
```
python -c "import ast,glob; [ast.parse(open(f,encoding='utf-8').read()) for f in glob.glob('**/*.py',recursive=True)]"
```
Result: **PASS** — printed `all parse`, exit 0.

## 2. Import with no DB / no psycopg2
```
python -c "import payment_plugin"                 -> import payment_plugin ok
python -c "import payment_plugin, database, bharatpe, qr_generator"  -> all import
python -c "import sys; sys.modules['psycopg2']=None; import database" -> db imports without psycopg2
```
Result: **PASS** — `database` imports with psycopg2 absent/blocked; `init_db`
only imports psycopg2 lazily when `db_url` starts with `postgres`.

## 3. UTR-reuse self-check (guard #4)
```
python tests/test_utr_reuse.py
```
Result: **PASS** — printed `PASS: reused UTR cannot verify a second order`, exit 0.
First `claim_utr` → True; second `claim_utr` with the same UTR → False; ORD2 stays
PENDING. Enforced by the sqlite `utr UNIQUE` constraint.

## 4. Config / QR / login-funcs
```
python -c "...PaymentConfig(...); print(c.bharatpe_api, c.db_path, c.utr_window_sec)"
   -> https://api-enterprise.bharatpe.in/api/v1/merchant/transactions payments.db 1800
python -c "...make_qr(500.0,'ORD1',cfg); print(len>0)"            -> qr True
python -c "import bharatpe; print(all hasattr start_login/complete_login/find_by_utr/fetch_transactions)" -> funcs True
python -c "import payment_plugin; print(payment_plugin.__all__)"  -> ['PaymentConfig', 'register_payment_handlers', 'register_admin_handlers']
```
Result: **PASS**. (Live OTP login not exercised — no real phone/OTP available.)

## 5. Cleanup + deps
```
python -c "assert not exists('bharatpe') and not exists('PAYMENT_FLOW.md') and not exists('INTEGRATION.md')" -> cleaned
requirements.txt: no duplicates, no bogus `telegram` package                 -> requirements ok
pyproject.toml: build_meta + optional-deps[postgres] + readme=README.md + Teamhapp -> toml ok
README.md: contains /login + UTR, no 'micro', no 'renewcredentials'          -> readme ok
```
Result: **PASS**. Burp capture `bharatpe` deleted from disk (was gitignored/untracked);
`PAYMENT_FLOW.md`, `INTEGRATION.md`, `payment_plugin/middleware.py` git-removed.
(Note: tomllib is 3.11+; on 3.10 the toml fields were asserted via substring check.)

## 6. Net line count (must go DOWN)
```
git diff --cached --stat
```
```
18 files changed, 577 insertions(+), 1928 deletions(-)
```
Net: **−1351 lines**. (Includes the planning doc `.agents/.../plan.md` +152;
even so, net is strongly negative.) `payments.db` is gitignored and not staged.

All checks pass. Temp files (`_check.py`, stray `payments.db`) removed.
