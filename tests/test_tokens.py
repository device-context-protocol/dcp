"""Tests for HMAC capability tokens."""
from __future__ import annotations

import pytest

from dcp.tokens import TokenError, mint, verify


SECRET = b"x" * 32


def test_mint_and_verify_round_trip():
    token = mint({"lamp.write", "lamp.read"}, secret=SECRET, ttl_seconds=60)
    parsed = verify(token, secret=SECRET)
    assert parsed.caps == frozenset({"lamp.write", "lamp.read"})
    assert not parsed.expired()


def test_rejects_wrong_secret():
    token = mint({"lamp.write"}, secret=SECRET)
    with pytest.raises(TokenError, match="signature"):
        verify(token, secret=b"y" * 32)


def test_rejects_tampered_payload():
    token = mint({"lamp.read"}, secret=SECRET)
    hdr, sig = token.split(".")
    bad = hdr[:-1] + ("A" if hdr[-1] != "A" else "B") + "." + sig
    with pytest.raises(TokenError):
        verify(bad, secret=SECRET)


def test_rejects_expired_token():
    token = mint({"lamp.write"}, secret=SECRET, ttl_seconds=0, now=1000)
    with pytest.raises(TokenError, match="expired"):
        verify(token, secret=SECRET, now=2000)


def test_rejects_short_secret():
    with pytest.raises(ValueError):
        mint({"x"}, secret=b"too-short")


def test_rejects_malformed_token():
    with pytest.raises(TokenError):
        verify("not-a-token", secret=SECRET)
