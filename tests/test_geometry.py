"""几何网格生成器单元测试（顶点数、绕序、法线朝向）。"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, ROOT)

import geometry as geo
import math3d as m3

RED = (1.0, 0.0, 0.0)


def face_normals(mesh):
    v = mesh["verts"].astype(np.float64)
    f = mesh["faces"]
    v0, v1, v2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    return n, (v0 + v1 + v2) / 3.0


class TestBox(unittest.TestCase):
    def test_counts(self):
        b = geo.box(0, 0.375, 0, 1.0, 0.75, 1.0, RED)
        self.assertEqual(b["verts"].shape[1], 3)
        self.assertEqual(len(b["faces"]), 10)      # 5 个可见面 x 2 个三角形
        # 纯色盒不生成 uv/纹理属性，贴图盒才需要
        self.assertIsNone(b["uvs"])
        self.assertIsNone(b["tex"])
        tb = geo.box(0, 0.375, 0, 1.0, 0.75, 1.0, RED, tex="stone")
        self.assertEqual(tb["uvs"].shape, (len(tb["verts"]), 2))
        self.assertEqual(tb["tex"], "stone")

    def test_normals_point_outward(self):
        b = geo.box(2.0, 0.375, -1.0, 1.0, 0.75, 1.0, RED)
        n, centers = face_normals(b)
        center = np.array([2.0, 0.375, -1.0])
        out = np.einsum("ij,ij->i", n, centers - center)
        self.assertTrue(np.all(out > 0.0), "所有面法线必须朝外（逆时针绕序）")

    def test_skip_bottom(self):
        b = geo.box(0, 0, 0, 1, 1, 1, RED, skip=("bottom",))
        n, _ = face_normals(b)
        self.assertFalse(np.any(n[:, 1] < -1e-6), "跳过底面后不应有朝下的三角形")

    def test_uv_range(self):
        b = geo.box(0, 0.5, 0, 2.0, 1.0, 2.0, RED, tex="stone", tile=1.0)
        u, v = b["uvs"][:, 0], b["uvs"][:, 1]
        self.assertGreaterEqual(float(u.min()), 0.0)
        self.assertGreaterEqual(float(v.min()), 0.0)
        self.assertLessEqual(float(u.max()), 2.0 + 1e-6)


class TestQuadSphereMerge(unittest.TestCase):
    def test_quad_square(self):
        q = geo.quad((-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1), RED)
        self.assertEqual(len(q["faces"]), 2)
        self.assertTrue(q["two_sided"])

    def test_sphere_outward(self):
        s = geo.sphere((1.0, 2.0, 3.0), 0.4, RED, rings=4, segments=8)
        n, centers = face_normals(s)
        center = np.array([1.0, 2.0, 3.0])
        out = np.einsum("ij,ij->i", n, centers - center)
        # 极点处的三角形退化成零面积，叉积为 0，不参与朝向判断（光栅化时也被剔除）
        alive = np.linalg.norm(n, axis=1) > 1e-9
        self.assertGreater(int(alive.sum()), 40, "绝大多数球面三角形不应退化")
        self.assertTrue(np.all(out[alive] > 0.0), "球面三角形必须朝外")

    def test_merge_counts(self):
        a = geo.box(0, 0.5, 0, 1, 1, 1, RED)
        b = geo.box(3, 0.5, 0, 1, 1, 1, (0, 1, 0))
        m = geo.merge([a, b])
        self.assertEqual(len(m["verts"]), len(a["verts"]) + len(b["verts"]))
        self.assertEqual(len(m["faces"]), len(a["faces"]) + len(b["faces"]))
        self.assertEqual(int(m["faces"].max()), len(m["verts"]) - 1)

    def test_transform_scaling(self):
        b = geo.box(0, 0.5, 0, 1, 1, 1, RED)
        # box(0,0.5,0,1,1,1) 的 y 范围是 0..1，缩放 2 倍后变成 0..2
        self.assertAlmostEqual(float(b["verts"][:, 1].max()), 1.0, places=5)
        t = geo.transform(b, m3.scaling([2.0, 2.0, 2.0]))
        self.assertAlmostEqual(float(t["verts"][:, 1].max()), 2.0, places=5)
        self.assertAlmostEqual(float(np.abs(t["verts"]).max()), 2.0, places=5)
        # 源网格不能被就地修改（transform 必须返回新网格）
        self.assertAlmostEqual(float(b["verts"][:, 1].max()), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
