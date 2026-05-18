"""Capability tokens — HMAC-SHA256 signed capability claims.

A token authorizes an LLM session to call intents that require a specific set
of capabilities, up to an expiry time. The Bridge issues tokens at session
start and verifies them on every ``call()``.

For v0.2 enforcement happens **only at the Bridge**. Devices trust their
Bridge implicitly. A future revision will let devices verify per-frame
signatures, but that needs MCU-side crypto we haven't profiled yet.

Token wire format (base64url, no padding)::

    <hdr_b64>.<sig_b64>

    hdr  = JSON({ "caps": ["lamp.write", ...], "exp": <unix-ts>, "sub": "<session-id>" })
    sig  = HMAC-SHA256(secret, hdr_b64)[:16]   # 128-bit truncated, plenty for our scope
"""
from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256

SIG_BYTES = 16  # truncate HMAC to 128 bits


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@dataclass(slots=True, frozen=True)
class Token:
    caps: frozenset[str]
    exp: int           # unix seconds
    sub: str           # session id / opaque subject

    def expired(self, *, now: int | None = None) -> bool:
        return (now or int(time.time())) >= self.exp


class TokenError(Exception):
    pass


def mint(
    capabilities: set[str] | frozenset[str],
    *,
    secret: bytes,
    ttl_seconds: int = 3600,
    subject: str | None = None,
    now: int | None = None,
) -> str:
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
        raise ValueError("secret must be >= 16 bytes")
    issued = now if now is not None else int(time.time())
    sub = subject or _b64url(secrets.token_bytes(9))
    header = {
        "caps": sorted(capabilities),
        "exp": issued + ttl_seconds,
        "sub": sub,
    }
    hdr_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(secret, hdr_b64.encode("ascii"), sha256).digest()[:SIG_BYTES]
    return f"{hdr_b64}.{_b64url(sig)}"


def verify(token: str, *, secret: bytes, now: int | None = None) -> Token:
    try:
        hdr_b64, sig_b64 = token.split(".", 1)
    except ValueError as e:
        raise TokenError("malformed token") from e

    expected = hmac.new(secret, hdr_b64.encode("ascii"), sha256).digest()[:SIG_BYTES]
    try:
        provided = _b64url_decode(sig_b64)
    except Exception as e:  # noqa: BLE001
        raise TokenError("malformed token signature") from e
    if not hmac.compare_digest(expected, provided):
        raise TokenError("invalid signature")

    try:
        payload = json.loads(_b64url_decode(hdr_b64).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise TokenError("malformed token payload") from e

    try:
        caps = frozenset(payload["caps"])
        exp = int(payload["exp"])
        sub = str(payload["sub"])
    except (KeyError, ValueError, TypeError) as e:
        raise TokenError("token missing required fields") from e

    tok = Token(caps=caps, exp=exp, sub=sub)
    if tok.expired(now=now):
        raise TokenError("token expired")
    return tok
