"""Offline tests: no database, server, credentials or payment provider needed."""
import unittest
from security import generate_api_key, verify_api_key, validate_api_key_format, extract_prefix


class ApiKeyTests(unittest.TestCase):
    def test_issued_key_verifies_and_prefix_is_consistent(self):
        key, prefix, stored = generate_api_key()
        self.assertTrue(validate_api_key_format(key))
        self.assertEqual(extract_prefix(key), prefix)
        self.assertTrue(verify_api_key(key, stored))
        self.assertNotIn(key, stored)

    def test_different_key_cannot_authenticate(self):
        key, _, stored = generate_api_key()
        other, _, _ = generate_api_key()
        self.assertNotEqual(key, other)
        self.assertFalse(verify_api_key(other, stored))

    def test_modified_key_is_rejected(self):
        key, _, stored = generate_api_key()
        changed = key[:-1] + ("A" if key[-1] != "A" else "B")
        self.assertFalse(verify_api_key(changed, stored))

    def test_malformed_keys_and_stored_hashes_are_rejected(self):
        key, _, stored = generate_api_key()
        for malformed in ["", "missing-dot", "short.abcdefghijklmno", "."]:
            with self.subTest(key=malformed):
                self.assertFalse(verify_api_key(malformed, stored))
        for malformed in ["", "bad", "zz:aa", ":", "00:not-hex"]:
            with self.subTest(stored=malformed):
                self.assertFalse(verify_api_key(key, malformed))


if __name__ == "__main__":
    unittest.main()
