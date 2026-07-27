#!/usr/bin/env python3
"""Sign a RailCall module bundle with an existing publisher key."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "module_dir",
        nargs="?",
        default=".",
        help="Directory containing module.json and handlers/handler.py",
    )
    parser.add_argument(
        "--publisher-key",
        default=os.environ.get("RAILCALL_PUBLISHER_KEY")
        or "~/.railcall/marketplace_publisher.json",
        help="RailCall marketplace publisher key record",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    module_dir = Path(args.module_dir).expanduser().resolve()
    manifest_path = module_dir / "module.json"
    handler_path = module_dir / "handlers" / "handler.py"
    signature_path = module_dir / "module.sig"
    key_path = Path(args.publisher_key).expanduser().resolve()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    handler_bytes = handler_path.read_bytes()
    key_record = json.loads(key_path.read_text(encoding="utf-8"))

    seed_hex = str(key_record.get("seed_hex") or "")
    public_hex = str(key_record.get("pubkey_hex") or "")
    if len(seed_hex) != 64 or len(public_hex) != 64:
        raise RuntimeError("publisher key record is missing a 32-byte seed or public key")
    if manifest.get("publisher_pubkey") != public_hex:
        raise RuntimeError("module publisher_pubkey does not match the local publisher key")

    unsigned_manifest = {
        key: value for key, value in manifest.items() if key != "signature"
    }
    payload = canonical_json(unsigned_manifest) + b"\n" + handler_bytes
    signature = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex)).sign(payload)

    signature_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=signature_path.parent,
        delete=False,
    ) as handle:
        handle.write(signature.hex() + "\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, signature_path)
    os.chmod(signature_path, 0o644)
    print(
        f"signed {manifest.get('id')} with publisher {public_hex[:16]}... "
        f"into {signature_path}"
    )


if __name__ == "__main__":
    main()
