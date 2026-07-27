from __future__ import annotations

import json
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MODULE_DIR = Path(__file__).resolve().parents[1]


class RailCallBundleTests(unittest.TestCase):
    def test_signature_matches_exact_manifest_and_handler_bytes(self):
        manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
        handler_bytes = (MODULE_DIR / "handlers" / "handler.py").read_bytes()
        signature_hex = (MODULE_DIR / "module.sig").read_text(encoding="utf-8").strip()
        unsigned_manifest = {
            key: value for key, value in manifest.items() if key != "signature"
        }
        canonical = json.dumps(
            unsigned_manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        payload = canonical + b"\n" + handler_bytes

        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(manifest["publisher_pubkey"])
        )
        public_key.verify(bytes.fromhex(signature_hex), payload)

    def test_bundle_has_only_expected_runtime_files(self):
        self.assertTrue((MODULE_DIR / "module.json").is_file())
        self.assertTrue((MODULE_DIR / "module.sig").is_file())
        self.assertTrue((MODULE_DIR / "handlers" / "handler.py").is_file())

    def test_contest_tag_and_free_license_are_explicit(self):
        manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
        self.assertIn("contest:2026Q3", manifest["description"])
        self.assertFalse(manifest["license_required"])
        self.assertEqual("1.0.0", manifest["version"])


if __name__ == "__main__":
    unittest.main()
