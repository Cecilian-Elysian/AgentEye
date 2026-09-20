import unittest

from providers.detect import detect


class TestKeyPrefix(unittest.TestCase):
    def test_minimax_coding(self):
        r = detect("sk-cp-abcdefghij")
        self.assertEqual(r["kind"], "minimax")
        self.assertEqual(r["base_url"], "https://api.minimaxi.com")
        self.assertEqual(r["confidence"], "high")

    def test_opencode_jwt(self):
        r = detect("eyJhbGciOiJIUzI1NiJ9.payload.signature")
        self.assertEqual(r["kind"], "opencode_go")
        self.assertEqual(r["confidence"], "medium")

    def test_generic_sk_no_url(self):
        r = detect("sk-abcdefghij1234567890")
        self.assertEqual(r["kind"], "generic_openai")
        self.assertEqual(r["base_url"], "")
        self.assertEqual(r["confidence"], "low")

    def test_unknown_key_no_url(self):
        r = detect("xxx-random-key-no-prefix")
        self.assertEqual(r["kind"], "generic_openai")
        self.assertEqual(r["base_url"], "")
        self.assertIn("无法识别", r["notes"])

    def test_empty_key_and_url(self):
        r = detect("", "")
        self.assertEqual(r["kind"], "generic_openai")
        self.assertEqual(r["confidence"], "low")


class TestUrlHints(unittest.TestCase):
    def test_deepseek_url(self):
        r = detect("any-key", "https://api.deepseek.com")
        self.assertEqual(r["kind"], "deepseek")
        self.assertEqual(r["base_url"], "https://api.deepseek.com")
        self.assertEqual(r["confidence"], "high")

    def test_zhipu_url(self):
        r = detect("any-key", "https://open.bigmodel.cn")
        self.assertEqual(r["kind"], "zhipu")
        self.assertEqual(r["base_url"], "https://open.bigmodel.cn")

    def test_minimax_url(self):
        r = detect("any-key", "https://api.minimaxi.com/v1")
        self.assertEqual(r["kind"], "minimax")

    def test_url_with_v1_path(self):
        r = detect("any-key", "https://api.example.com/v1")
        self.assertEqual(r["kind"], "generic_openai")
        self.assertEqual(r["base_url"], "https://api.example.com/v1")

    def test_url_without_v1(self):
        r = detect("any-key", "https://api.example.com")
        self.assertEqual(r["kind"], "generic_openai")
        self.assertEqual(r["base_url"], "https://api.example.com")
        self.assertEqual(r["confidence"], "low")

    def test_url_overrides_key_prefix(self):
        r = detect("sk-cp-xxx", "https://api.deepseek.com")
        self.assertEqual(r["kind"], "deepseek")


class TestEdgeCases(unittest.TestCase):
    def test_whitespace_trimmed(self):
        r = detect("  sk-cp-xxx  ", "  https://api.deepseek.com  ")
        self.assertEqual(r["kind"], "deepseek")

    def test_trailing_slash_stripped(self):
        r = detect("k", "https://api.deepseek.com/")
        self.assertEqual(r["base_url"], "https://api.deepseek.com")


if __name__ == "__main__":
    unittest.main()
