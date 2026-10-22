"""Connect the owner's eBay seller account (OAuth user token) and keep it, encrypted, on the data branch.

    python tools/ebay_user.py link                 # print the eBay sign-in (consent) link
    python tools/ebay_user.py connect CODE STORE   # swap the one-time code for a refresh token, save it encrypted
    python tools/ebay_user.py check STORE          # confirm the saved connection works (prints the eBay user name)

The refresh token (valid ~18 months) is encrypted with AES-GCM under a key derived from
EBAY_CLIENT_SECRET, so the public data branch never holds it in readable form.
Needs EBAY_CLIENT_ID, EBAY_CLIENT_SECRET; pip install cryptography.
"""
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

RUNAME = os.environ.get("EBAY_RUNAME", "Drive_Style_Wiz-DriveSty-DYSMar-kmato")
SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.marketing.readonly",
]
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"


def creds():
    cid, sec = os.environ.get("EBAY_CLIENT_ID", "").strip(), os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise SystemExit("::error title=eBay connect::EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    return cid, sec


def _key():
    return hashlib.sha256(("dys-ebay-user:" + creds()[1]).encode()).digest()


def seal(obj):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = os.urandom(12)
    ct = AESGCM(_key()).encrypt(iv, json.dumps(obj).encode(), None)
    return base64.b64encode(iv + ct).decode()


def unseal(s):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(s)
    return json.loads(AESGCM(_key()).decrypt(raw[:12], raw[12:], None))


def token_call(form):
    cid, sec = creds()
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(form).encode(), headers={
        "Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def access_token(store):
    """A fresh user access token (2 hours) from the saved refresh token."""
    saved = unseal(open(os.path.join(store, "user.enc")).read().strip())
    d = token_call({"grant_type": "refresh_token", "refresh_token": saved["refresh_token"], "scope": " ".join(SCOPES)})
    return d["access_token"]


def whoami(tok):
    req = urllib.request.Request("https://apiz.ebay.com/commerce/identity/v1/user/", headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("username", "?")


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "link":
        cid, _ = creds()
        url = "https://auth.ebay.com/oauth2/authorize?" + urllib.parse.urlencode(
            {"client_id": cid, "response_type": "code", "redirect_uri": RUNAME, "scope": " ".join(SCOPES), "prompt": "login"})
        print(f"::notice title=eBay sign-in link::{url}")
    elif cmd == "connect":
        code, store = urllib.parse.unquote(argv[1].strip()), argv[2]
        try:
            d = token_call({"grant_type": "authorization_code", "code": code, "redirect_uri": RUNAME})
        except urllib.error.HTTPError as e:
            raise SystemExit(f"::error title=eBay connect::HTTP {e.code} {e.read()[:200]!r} (codes expire after 5 minutes; get a new one)")
        os.makedirs(store, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        open(os.path.join(store, "user.enc"), "w").write(seal({"refresh_token": d["refresh_token"], "at": now,
                                                               "refresh_expires_in": d.get("refresh_token_expires_in")}))
        user = whoami(d["access_token"])
        json.dump({"connected": now, "user": user}, open(os.path.join(store, "user.json"), "w"))
        print(f"::notice title=eBay connected::seller account {user} connected (refresh token saved encrypted)")
    elif cmd == "check":
        print(f"::notice title=eBay connection::OK, signed in as {whoami(access_token(argv[1]))}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
