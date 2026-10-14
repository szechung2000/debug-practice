"""Encrypted answer-key vault.

The answer key (root-cause write-ups, hidden tests, reference patches) is
stored as one encrypted bundle: answer-key/bundle.enc. The passphrase is never
stored in the repository, so an AI session that works inside the repo cannot
read the answers.

Construction (stdlib only, portable to macOS and Linux):
  key material = PBKDF2-HMAC-SHA256(passphrase, salt, 300_000) -> 64 bytes
  keystream    = HMAC-SHA256(enc_key, nonce || counter) blocks
  ciphertext   = tar.gz(plaintext dir) XOR keystream
  tag          = HMAC-SHA256(mac_key, MAGIC || salt || nonce || ciphertext)

Usage:
  python tools/keyvault.py pack   --src DIR            (re-encrypt after edits)
  python tools/keyvault.py unpack --out DIR            (outside the repo!)
  python tools/keyvault.py check                       (test the passphrase)
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import io
import os
import secrets
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = REPO_ROOT / "answer-key" / "bundle.enc"
MAGIC = b"DPKEY1"
ITERATIONS = 300_000


class VaultError(Exception):
    pass


def _derive(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    km = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, ITERATIONS, dklen=64)
    return km[:32], km[32:]


def _keystream_xor(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray(len(data))
    for block_no in range((len(data) + 31) // 32):
        block = hmac.new(enc_key, nonce + block_no.to_bytes(8, "big"), hashlib.sha256).digest()
        start = block_no * 32
        chunk = data[start:start + 32]
        out[start:start + len(chunk)] = bytes(a ^ b for a, b in zip(chunk, block))
    return bytes(out)


def encrypt(plaintext: bytes, passphrase: str) -> bytes:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    enc_key, mac_key = _derive(passphrase, salt)
    ct = _keystream_xor(enc_key, nonce, plaintext)
    tag = hmac.new(mac_key, MAGIC + salt + nonce + ct, hashlib.sha256).digest()
    return MAGIC + salt + nonce + tag + ct


def decrypt(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise VaultError("bundle has an unknown format")
    off = len(MAGIC)
    salt, nonce, tag = blob[off:off + 16], blob[off + 16:off + 32], blob[off + 32:off + 64]
    ct = blob[off + 64:]
    enc_key, mac_key = _derive(passphrase, salt)
    expect = hmac.new(mac_key, MAGIC + salt + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        raise VaultError("wrong passphrase (or the bundle is damaged)")
    return _keystream_xor(enc_key, nonce, ct)


def get_passphrase(confirm: bool = False) -> str:
    env = os.environ.get("DEBUG_PRACTICE_KEY")
    if env:
        print("warning: DEBUG_PRACTICE_KEY is set. An AI session in this shell can read it.",
              file=sys.stderr)
        return env
    if not sys.stdin.isatty():
        raise VaultError("the passphrase prompt needs an interactive terminal; "
                         "run this command yourself, not through an AI agent")
    pw = getpass.getpass("Answer-key passphrase: ")
    if confirm and getpass.getpass("Repeat passphrase: ") != pw:
        raise VaultError("the passphrases do not match")
    return pw


def pack_dir(src: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(src.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                tar.add(path, arcname=str(path.relative_to(src)))
    return buf.getvalue()


def unpack_to(blob: bytes, out: Path, passphrase: str, member_prefix: str | None = None) -> None:
    data = decrypt(blob, passphrase)
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = [m for m in tar.getmembers()
                   if member_prefix is None or m.name.startswith(member_prefix)]
        tar.extractall(out, members=members, filter="data")


def load_scenario_key(scenario_id: str, out: Path, passphrase: str | None = None) -> Path:
    """Extract one scenario's key folder into `out` and return its path."""
    passphrase = passphrase if passphrase is not None else get_passphrase()
    unpack_to(BUNDLE.read_bytes(), out, passphrase, member_prefix=scenario_id)
    path = out / scenario_id
    if not path.exists():
        raise VaultError(f"no answer key for scenario {scenario_id}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--src", required=True, type=Path)
    u = sub.add_parser("unpack")
    u.add_argument("--out", required=True, type=Path)
    sub.add_parser("check")
    args = ap.parse_args()
    try:
        if args.cmd == "pack":
            blob = encrypt(pack_dir(args.src), get_passphrase(confirm=True))
            BUNDLE.parent.mkdir(exist_ok=True)
            BUNDLE.write_bytes(blob)
            print(f"wrote {BUNDLE.relative_to(REPO_ROOT)} ({len(blob)} bytes)")
        elif args.cmd == "unpack":
            if REPO_ROOT in args.out.resolve().parents or args.out.resolve() == REPO_ROOT:
                print("warning: you unpacked inside the repo; an AI session can now read the answers.",
                      file=sys.stderr)
            unpack_to(BUNDLE.read_bytes(), args.out, get_passphrase())
            print(f"unpacked to {args.out}")
        else:
            decrypt(BUNDLE.read_bytes(), get_passphrase())
            print("passphrase OK")
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
