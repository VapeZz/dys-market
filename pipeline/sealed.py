"""Encrypted storage for third-party data we may keep but must not publish.

The repo (and its data branch) is public, so data whose terms forbid exposing stored copies is
kept encrypted there: PokemonPriceTracker data (graded prices, the price history it filled in
before our own tracking started) and cached eBay listings. The site still shows the data to its
visitors; only the raw stored copies are sealed.

AES-256-GCM with a key derived from a GitHub secret the jobs already have:
    "ppt"   PPT_API_KEY          (PPT_API_KEY_OLD is also tried when reading, after a key change)
    "ebay"  EBAY_CLIENT_SECRET   (EBAY_CLIENT_SECRET_OLD likewise)
Changing one of those secrets? Save the old value as the matching *_OLD secret first; files are
re-sealed with the new key as they're rewritten.

Needs: pip install cryptography
"""
import hashlib
import os

MAGIC = b"DYSENC1"
SECRETS = {"ppt": ("PPT_API_KEY", "PPT_API_KEY_OLD"), "ebay": ("EBAY_CLIENT_SECRET", "EBAY_CLIENT_SECRET_OLD")}


class Locked(Exception):
    """The key (or the cryptography package) isn't available, so sealed data can't be read or written."""


def _key(purpose, name):
    v = (os.environ.get(name) or "").strip()
    return hashlib.sha256(f"dys-sealed-{purpose}:{v}".encode()).digest() if v else None


def _aes():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except ImportError as e:
        raise Locked("the cryptography package isn't installed (pip install cryptography)") from e


def can_seal(purpose):
    return _key(purpose, SECRETS[purpose][0]) is not None


def seal(purpose, data):
    key = _key(purpose, SECRETS[purpose][0])
    if key is None:
        raise Locked(f"{SECRETS[purpose][0]} isn't set")
    nonce = os.urandom(12)
    return MAGIC + nonce + _aes()(key).encrypt(nonce, data, MAGIC)


def unseal(purpose, blob):
    """Returns (data, stale): stale is True when only the old key opened it (rewrite it to re-seal)."""
    if not blob.startswith(MAGIC):
        raise ValueError("not a sealed file")
    AESGCM = _aes()
    nonce, ct = blob[len(MAGIC):len(MAGIC) + 12], blob[len(MAGIC) + 12:]
    for i, name in enumerate(SECRETS[purpose]):
        key = _key(purpose, name)
        if key is None:
            continue
        try:
            return AESGCM(key).decrypt(nonce, ct, MAGIC), i > 0
        except Exception:  # wrong key
            continue
    raise Locked(f"no key opens it ({' / '.join(SECRETS[purpose])})")


def write(purpose, path, data):
    blob = seal(purpose, data)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)


def read(purpose, path):
    with open(path, "rb") as f:
        return unseal(purpose, f.read())[0]
