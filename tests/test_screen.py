"""多显示器磁吸/恢复钳制的单元测试。

背景:磁吸原先按主屏 winfo_screenwidth/height 钳制,窗口在副屏时
会被强行拽回主屏。钳制逻辑抽成纯函数后可直接单测。
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ui.screen as screen


class TestSnapClamp(unittest.TestCase):
    AREA = (0, 0, 1920, 1040)

    def test_left_edge_snaps(self):
        self.assertEqual(screen.snap_clamp(10, 500, 360, 360,
                                           self.AREA, 20), (0, 500))

    def test_right_edge_snaps(self):
        x, _ = screen.snap_clamp(1910, 500, 360, 360, self.AREA, 20)
        self.assertEqual(x, 1920 - 360)

    def test_top_and_bottom_edges_snap(self):
        _, y1 = screen.snap_clamp(500, 5, 360, 360, self.AREA, 20)
        self.assertEqual(y1, 0)
        _, y2 = screen.snap_clamp(500, 1035, 360, 360, self.AREA, 20)
        self.assertEqual(y2, 1040 - 360)

    def test_middle_stays_put(self):
        self.assertEqual(screen.snap_clamp(500, 500, 360, 360,
                                           self.AREA, 20), (500, 500))

    def test_secondary_monitor_area_is_respected(self):
        # 副屏在主屏右侧:(1920, 0, 3840, 1040)。旧的主屏钳制会把
        # x=2000 的窗口拽回主屏右缘,这里必须原地不动
        area = (1920, 0, 3840, 1040)
        self.assertEqual(screen.snap_clamp(2000, 500, 360, 360,
                                           area, 20), (2000, 500))


class TestRestorePosition(unittest.TestCase):
    def test_offscreen_coords_clamp_into_monitor(self):
        with mock.patch.object(screen, "work_area",
                               return_value=(0, 0, 1920, 1040)):
            self.assertEqual(screen.restore_position(
                -5000, -5000, 360, 360, (1920, 1080)), (0, 0))
            self.assertEqual(screen.restore_position(
                5000, 100, 360, 360, (1920, 1080)), (1920 - 360, 100))

    def test_inside_coords_untouched(self):
        with mock.patch.object(screen, "work_area",
                               return_value=(0, 0, 1920, 1040)):
            self.assertEqual(screen.restore_position(
                100, 200, 360, 360, (1920, 1080)), (100, 200))


class TestWorkAreaFallback(unittest.TestCase):
    def test_point_off_all_monitors_falls_back(self):
        # 10^9 远在任何虚拟桌面之外,MonitorFromPoint 返回 NULL → 回退
        self.assertEqual(screen.work_area(10 ** 9, 10 ** 9, (800, 600)),
                         (0, 0, 800, 600))

    def test_primary_screen_point_returns_real_area(self):
        area = screen.work_area(10, 10, (800, 600))
        self.assertEqual(len(area), 4)
        left, top, right, bottom = area
        self.assertLess(left, right)
        self.assertLess(top, bottom)


if __name__ == "__main__":
    unittest.main()
