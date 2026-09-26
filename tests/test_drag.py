"""测试拖拽重排逻辑(纯函数,不依赖 tkinter event 循环)。"""
import unittest

from ui import panel


class DragHelpers(unittest.TestCase):
    def test_compute_drag_target_top(self):
        # Mock siblings with winfo_rooty / winfo_height
        class W:
            def __init__(self, y, h):
                self._y = y
                self._h = h
            def winfo_rooty(self):
                return self._y
            def winfo_height(self):
                return self._h
        rows = [W(0, 50), W(60, 50), W(120, 50)]
        self.assertEqual(panel._compute_target_static(rows, 10), 0)

    def test_compute_drag_target_middle(self):
        class W:
            def __init__(self, y, h):
                self._y = y
                self._h = h
            def winfo_rooty(self):
                return self._y
            def winfo_height(self):
                return self._h
        rows = [W(0, 50), W(60, 50), W(120, 50)]
        self.assertEqual(panel._compute_target_static(rows, 80), 1)

    def test_compute_drag_target_bottom(self):
        class W:
            def __init__(self, y, h):
                self._y = y
                self._h = h
            def winfo_rooty(self):
                return self._y
            def winfo_height(self):
                return self._h
        rows = [W(0, 50), W(60, 50), W(120, 50)]
        self.assertEqual(panel._compute_target_static(rows, 200), 3)


class ModelOrderCache(unittest.TestCase):
    def test_save_and_load_order(self):
        import os, tempfile, json
        import cache
        with tempfile.TemporaryDirectory() as d:
            cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
            cache.MODELS_CACHE = cache.CACHE_DIR / "models.json"
            cache.set_models("https://x", "k1", ["m1", "m2", "m3"])
            cache.save_model_order("https://x", "k1", ["m3", "m1", "m2"])
            result = cache.get_models("https://x", "k1")
            self.assertEqual(result, ["m3", "m1", "m2"])

    def test_order_pruned_to_existing_models(self):
        import os, tempfile
        import cache
        with tempfile.TemporaryDirectory() as d:
            cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
            cache.MODELS_CACHE = cache.CACHE_DIR / "models.json"
            cache.set_models("https://x", "k1", ["m1", "m2", "m3"])
            cache.save_model_order("https://x", "k1", ["m3", "ghost", "m1"])
            result = cache.get_models("https://x", "k1")
            self.assertEqual(result, ["m3", "m1", "m2"])

    def test_extras_appended(self):
        import os, tempfile
        import cache
        with tempfile.TemporaryDirectory() as d:
            cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
            cache.MODELS_CACHE = cache.CACHE_DIR / "models.json"
            cache.set_models("https://x", "k1", ["m1", "m2", "m3", "m4"])
            cache.save_model_order("https://x", "k1", ["m3", "m1"])
            result = cache.get_models("https://x", "k1")
            self.assertEqual(result, ["m3", "m1", "m2", "m4"])

    def test_models_expire_loses_order(self):
        import os, tempfile
        import cache
        with tempfile.TemporaryDirectory() as d:
            cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
            cache.MODELS_CACHE = cache.CACHE_DIR / "models.json"
            cache.set_models("https://x", "k1", ["m1", "m2"])
            cache.save_model_order("https://x", "k1", ["m2", "m1"])
            self.assertEqual(cache.get_models("https://x", "k1", ttl=0.1), ["m2", "m1"])
            import time
            time.sleep(0.2)
            self.assertIsNone(cache.get_models("https://x", "k1", ttl=0.1))

    def test_refresh_models_preserves_order(self):
        import os, tempfile
        import cache
        with tempfile.TemporaryDirectory() as d:
            cache.CACHE_DIR = type(cache.CACHE_DIR)(d)
            cache.MODELS_CACHE = cache.CACHE_DIR / "models.json"
            cache.set_models("https://x", "k1", ["m1", "m2", "m3"])
            cache.save_model_order("https://x", "k1", ["m3", "m1", "m2"])
            cache.set_models("https://x", "k1", ["m1", "m2", "m3", "m4"])
            result = cache.get_models("https://x", "k1")
            self.assertEqual(result, ["m3", "m1", "m2", "m4"])


if __name__ == "__main__":
    unittest.main()