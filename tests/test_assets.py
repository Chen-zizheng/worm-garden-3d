"""纹理资源与双线性过滤的集成测试。"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, ROOT)

import assets
import config as C


class TestTextureAssets(unittest.TestCase):
    def setUp(self):
        assets.ensure_textures()

    def test_textures_exist_and_load(self):
        for name in assets.MATERIALS:
            path = assets.tex_path(name)
            self.assertTrue(os.path.exists(path), f"缺少纹理文件 {path}")
            tex = assets.load_texture(name)
            self.assertEqual(tex.shape, (assets.TEX_SIZE, assets.TEX_SIZE, 3))
            self.assertEqual(tex.dtype, np.float32)
            self.assertGreaterEqual(float(tex.min()), 0.0)
            self.assertLessEqual(float(tex.max()), 1.0)

    def test_power_of_two_size(self):
        n = assets.TEX_SIZE
        self.assertEqual(n & (n - 1), 0, "位与取模要求纹理尺寸是 2 的幂")

    def test_grass_and_stone_are_different(self):
        grass = assets.load_texture("grass")
        stone = assets.load_texture("stone")
        self.assertGreater(float(np.abs(grass - stone).mean()), 0.05)
        # 石墙整体更亮，所以比“绝对绿”没意义；比“绿 - 红 / 绿 - 蓝”的色偏才有意义
        grass_green = float((grass[:, :, 1] - grass[:, :, 0]).mean())
        stone_green = float((stone[:, :, 1] - stone[:, :, 0]).mean())
        self.assertGreater(grass_green, 0.15, "草地应明显偏绿")
        self.assertGreater(grass_green, stone_green + 0.10, "草地应比石墙更绿")

    def test_textures_have_variation(self):
        for name in ("grass", "stone"):
            tex = assets.load_texture(name)
            self.assertGreater(float(tex.std()), 0.01, f"{name} 纹理应有细节")


class TestChecker(unittest.TestCase):
    def test_checker_two_values(self):
        # make_checker 返回 PIL Image；单通道应有且仅有两个灰度值，黑白各半
        arr = np.asarray(assets.make_checker(64, squares=8))
        self.assertEqual(arr.shape, (64, 64, 3))
        self.assertEqual(len(np.unique(arr[..., 0])), 2, "棋盘只应有两种颜色")
        self.assertEqual(len(np.unique(arr[..., 1])), 2)
        light = float((arr[..., 0] > 128).mean())
        self.assertAlmostEqual(light, 0.5, delta=0.06)


if __name__ == "__main__":
    unittest.main()
