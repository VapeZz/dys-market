"""Encryption for the PRIVATE research file (records, evidence, screening, rechecks, pending identities). TEST BRANCH CODE.

Hybrid: a fresh AES-256-GCM key per file, wrapped with RSA-OAEP-SHA256 (4096-bit). Jobs that write need only the public key;
reading needs the private key (in production: an Actions secret + Keo's password manager; never in the repository).
File = 4-byte header length + JSON header + ciphertext (GCM tag included). The header is authenticated as AAD,
so any change to header or ciphertext makes decryption fail.
"""
import base64, hashlib, json, os, struct
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)

def new_keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=4096)

def key_id(public_key):
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()[:16]

def encrypt(plaintext, public_key):
    k = AESGCM.generate_key(256); nonce = os.urandom(12)
    hdr = {'v': 1, 'alg': 'RSA-OAEP-256+A256GCM', 'kid': key_id(public_key),
           'wrapped_key': base64.b64encode(public_key.encrypt(k, OAEP)).decode(), 'nonce': base64.b64encode(nonce).decode(),
           'plaintext_sha256': hashlib.sha256(plaintext).hexdigest()}
    h = json.dumps(hdr, sort_keys=True).encode()
    return struct.pack('>I', len(h)) + h + AESGCM(k).encrypt(nonce, plaintext, h)

def header(blob):
    n = struct.unpack('>I', blob[:4])[0]; return json.loads(blob[4:4 + n]), blob[4:4 + n], blob[4 + n:]

def decrypt(blob, private_key):
    hdr, h, ct = header(blob)
    if hdr.get('v') != 1: raise ValueError('unknown vault version')
    if hdr['kid'] != key_id(private_key.public_key()): raise ValueError(f'file was encrypted for key {hdr["kid"]}, not this key')
    k = private_key.decrypt(base64.b64decode(hdr['wrapped_key']), OAEP)
    pt = AESGCM(k).decrypt(base64.b64decode(hdr['nonce']), ct, h)   # raises InvalidTag on any change
    if hashlib.sha256(pt).hexdigest() != hdr['plaintext_sha256']: raise ValueError('plaintext checksum mismatch')
    return pt

def rewrap(blob, old_private, new_public):
    """Key rotation: decrypt with the old key, encrypt for the new one (old files stay readable with the old key)."""
    return encrypt(decrypt(blob, old_private), new_public)
