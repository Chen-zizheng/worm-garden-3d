"""软件光栅化器单元测试：投影、近平面裁剪、深度缓冲、背面剔除、贴图过滤。"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, ROOT)

import math3d as m3
import raster
from raster import Renderer, clip_near

IDENTITY = np.eye(4)
RED = np.array([[1.0, 0.0, 0.0]], np.float32)
GREEN = np.array([[0.0, 1.0, 0.0]], np.float32)
LIGHT = np.array([0.0, 0.0, 1.0])


def quad(z, half=1.2):
    """相机前方 z 单位处、面向相机的方片（两个三角形，逆时针）。

    相机看向 -z，所以 z 是“距离”，顶点实际在 -z 平面上；从相机方向看是正面。
    """
    verts = np.array([
        [-half, -half, -z], [half, -half, -z], [half, half, -z], [-half, half, -z],
    ], np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], np.int32)
    return verts, faces


def draw_quad(r, z, color, half=1.2, cull=True, two_sided=False, **kw):
    verts, faces = quad(z, half)
    r.draw_mesh(verts, faces, color, IDENTITY,
                m3.perspective(60.0, r.w / r.h, 0.1, 100.0),
                np.zeros(3), LIGHT, 0.1, ambient=0.35,
                cull=cull, two_sided=two_sided, **kw)


class TestProjection(unittest.TestCase):
    def test_center_maps_to_screen_center(self):
        r = Renderer(64, 40)
        proj = m3.perspective(60.0, 64 / 40, 0.1, 100.0)
        sx, sy, ndc = r.project_eye(np.array([[0.0, 0.0, -4.0]]), proj)
        self.assertAlmostEqual(float(sx[0]), 32.0, places=6)
        self.assertAlmostEqual(float(sy[0]), 20.0, places=6)

    def test_x_axis_direction(self):
        r = Renderer(64, 64)
        proj = m3.perspective(60.0, 1.0, 0.1, 100.0)
        sx, _, _ = r.project_eye(np.array([[1.0, 0.0, -4.0], [-1.0, 0.0, -4.0]]), proj)
        self.assertGreater(float(sx[0]), float(sx[1]))

    def test_orthographic_parallel_rays(self):
        r = Renderer(64, 64)
        proj = m3.orthographic(8.0, 1.0, 0.1, 100.0)
        sx, _, _ = r.project_eye(np.array([[1.0, 0.0, -3.0], [1.0, 0.0, -30.0]]), proj)
        self.assertAlmostEqual(float(sx[0]), float(sx[1]), places=5)


class TestClipNear(unittest.TestCase):
    def test_fully_visible_triangle_is_unchanged(self):
        tri = np.array([[0.0, 0.0, -1.0], [1.0, 0.0, -1.0], [0.0, 1.0, -1.0]])
        out = clip_near(tri, 0.1)
        self.assertEqual(len(out), 1)

    def test_triangle_behind_camera_is_removed(self):
        tri = np.array([[0.0, 0.0, -0.05], [1.0, 0.0, -0.05], [0.0, 1.0, -0.05]])
        self.assertEqual(clip_near(tri, 0.1), [])

    def test_partially_clipped_becomes_quad(self):
        tri = np.array([[0.0, 0.0, -0.02], [1.0, 0.0, -2.0], [1.0, 1.0, -2.0]])
        out = clip_near(tri, 0.1)
        self.assertEqual(len(out), 2, "一个顶点在近平面后方时裁出两个三角形")
        for t in out:
            self.assertTrue(np.all(t[:, 2] <= -0.1 + 1e-6), "裁剪后所有顶点必须在近平面之前")

    def test_interpolates_uv(self):
        tri = np.array([[0.0, 0.0, -0.02], [1.0, 0.0, -2.0], [1.0, 1.0, -2.0]])
        uv = np.array([[0.5, 0.5], [0.0, 0.0], [1.0, 0.0]])
        out = clip_near(tri, 0.1, uv)
        self.assertTrue(len(out) == 2)
        for _, a in out:
            self.assertEqual(a.shape, (3, 2))
            self.assertTrue(np.all(a >= -1e-6) and np.all(a <= 1.0 + 1e-6))


class TestDepthBuffer(unittest.TestCase):
    def test_nearer_quad_wins_regardless_of_order(self):
        for order in ((2.0, 4.0), (4.0, 2.0)):
            r = Renderer(64, 64)
            r.clear()
            colors = {2.0: RED, 4.0: GREEN}
            for z in order:
                draw_quad(r, z, colors[z])
            px = r.to_image()[32, 32]
            self.assertGreater(int(px[0]), 100)
            self.assertLess(int(px[1]), 100)

    def test_depth_values_written(self):
        r = Renderer(64, 64)
        r.clear()
        draw_quad(r, 3.0, RED)
        finite = np.isfinite(r.depth)
        self.assertGreater(int(finite.sum()), 0)
        self.assertTrue(np.all(r.depth[finite] > -1.5) and np.all(r.depth[finite] <= 1.0))

    def test_back_face_culled_but_two_sided_shows(self):
        r = Renderer(64, 64)
        r.clear()
        verts, faces = quad(3.0)
        faces = faces[:, ::-1].copy()          # 翻转绕序 -> 背面
        r.draw_mesh(verts, faces, RED, IDENTITY,
                    m3.perspective(60.0, 1.0, 0.1, 100.0),
                    np.zeros(3), LIGHT, 0.1, cull=True)
        self.assertEqual(r.drawn_count, 0, "背面应被剔除")
        r.clear()
        r.draw_mesh(verts, faces, RED, IDENTITY,
                    m3.perspective(60.0, 1.0, 0.1, 100.0),
                    np.zeros(3), LIGHT, 0.1, cull=True, two_sided=True)
        self.assertGreater(r.drawn_count, 0, "双面网格不应被剔除")


class TestTexturedRaster(unittest.TestCase):
    def _checker(self):
        t = np.zeros((8, 8, 3), np.float32)
        for j in range(8):
            for i in range(8):
                if (i + j) % 2 == 0:
                    t[j, i] = 1.0
        return t

    def _render(self, bilinear):
        r = Renderer(64, 64)
        r.clear()
        verts, faces = quad(2.0, half=1.0)
        uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], np.float32)
        r.draw_mesh(verts, faces, np.ones((2, 3), np.float32), IDENTITY,
                    m3.perspective(60.0, 1.0, 0.1, 100.0),
                    np.zeros(3), LIGHT, 0.1,
                    tex=self._checker(), uvs=uvs, bilinear=bilinear,
                    perspective=False)
        return r.to_image()

    def test_nearest_vs_bilinear(self):
        near = self._render(False)
        bil = self._render(True)
        # 只取方片内部区域，避免天空渐变混进颜色统计
        near = near[16:48, 16:48]
        bil = bil[16:48, 16:48]
        self.assertGreater(int(near.max()), 200)
        # 最近邻只采样到棋盘的两个原始颜色（暗格/亮格 x 每个三角形一个固定光强）
        self.assertLessEqual(len(np.unique(near)), 8)
        # 双线性会插值出大量中间灰
        self.assertGreater(len(np.unique(bil)), 20)

    def test_constant_texture_identical(self):
        tex = np.full((4, 4, 3), 0.5, np.float32)
        outs = []
        for bil in (False, True):
            r = Renderer(32, 32)
            r.clear()
            verts, faces = quad(2.0, half=1.0)
            uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], np.float32)
            r.draw_mesh(verts, faces, np.ones((2, 3), np.float32), IDENTITY,
                        m3.perspective(60.0, 1.0, 0.1, 100.0),
                        np.zeros(3), LIGHT, 0.1, tex=tex, uvs=uvs, bilinear=bil)
            outs.append(r.to_image())
        np.testing.assert_array_equal(outs[0], outs[1])


class TestFog(unittest.TestCase):
    def test_fog_uses_linear_distance(self):
        r = Renderer(8, 8)
        r.clear()
        # 手动写入 NDC 深度：近平面处的点 -> 雾系数 0；远处 -> 雾系数 1
        proj = m3.perspective(60.0, 1.0, 0.1, 100.0)
        _, _, ndc_near = r.project_eye(np.array([[0.0, 0.0, -1.0]]), proj)
        _, _, ndc_far = r.project_eye(np.array([[0.0, 0.0, -90.0]]), proj)
        r.depth.fill(np.inf)
        r.depth[0, 0] = float(ndc_near[0])
        r.depth[0, 1] = float(ndc_far[0])
        r.color[:] = 0.0
        r.apply_fog(5.0, 60.0, (1.0, 1.0, 1.0), near=0.1, far=100.0, perspective=True)
        self.assertLess(float(r.color[0, 0, 0]), 0.2)
        self.assertGreater(float(r.color[0, 1, 0]), 0.8)
        # 天空像素（depth=inf）不受雾影响
        self.assertEqual(float(r.color[5, 5, 0]), 0.0)


if __name__ == "__main__":
    unittest.main()
