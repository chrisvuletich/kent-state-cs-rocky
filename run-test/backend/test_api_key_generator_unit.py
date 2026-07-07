from __future__ import annotations

import importlib.util
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "rocky-backend" / "backend" / "api_key_generator.py"

spec = importlib.util.spec_from_file_location("api_key_generator", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load api_key_generator from {MODULE_PATH}")

api_key_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_key_module)

API_KEY_PREFIX = api_key_module.API_KEY_PREFIX
API_KEY_ID_PREFIX = api_key_module.API_KEY_ID_PREFIX
HIDDEN_API_KEY_PREFIX = api_key_module.HIDDEN_API_KEY_PREFIX
derive_hidden_api_key = api_key_module.derive_hidden_api_key
generate_api_key_id = api_key_module.generate_api_key_id
generate_hidden_api_key_pair = api_key_module.generate_hidden_api_key_pair
generate_api_key_pair = api_key_module.generate_api_key_pair


class ApiKeyGeneratorUnitTests(unittest.TestCase):
    def test_generate_api_key_pair_returns_prefixed_plaintext_and_hash(self):
        plaintext, key_hash = generate_api_key_pair()

        self.assertTrue(plaintext.startswith(API_KEY_PREFIX))
        self.assertEqual(len(key_hash), 64)
        self.assertEqual(key_hash, hashlib.sha256(plaintext.encode("utf-8")).hexdigest())

    def test_generate_api_key_pair_is_unique(self):
        first_plaintext, first_hash = generate_api_key_pair()
        second_plaintext, second_hash = generate_api_key_pair()

        self.assertNotEqual(first_plaintext, second_plaintext)
        self.assertNotEqual(first_hash, second_hash)

    def test_generate_api_key_id_returns_public_unique_identifier(self):
        first_id = generate_api_key_id()
        second_id = generate_api_key_id()

        self.assertTrue(first_id.startswith(API_KEY_ID_PREFIX))
        self.assertTrue(second_id.startswith(API_KEY_ID_PREFIX))
        self.assertNotEqual(first_id, second_id)

    def test_hidden_api_key_is_deterministic_for_owner_and_secret(self):
        first_key = derive_hidden_api_key(" User-One ", "test-secret")
        second_key = derive_hidden_api_key("user-one", "test-secret")
        other_user_key = derive_hidden_api_key("user-two", "test-secret")

        self.assertTrue(first_key.startswith(HIDDEN_API_KEY_PREFIX))
        self.assertEqual(first_key, second_key)
        self.assertNotEqual(first_key, other_user_key)

    def test_generate_hidden_api_key_pair_returns_hash_only_storage_value(self):
        plaintext, key_hash = generate_hidden_api_key_pair("user-one", "test-secret")

        self.assertTrue(plaintext.startswith(HIDDEN_API_KEY_PREFIX))
        self.assertEqual(key_hash, hashlib.sha256(plaintext.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    unittest.main()
