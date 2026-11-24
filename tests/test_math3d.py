"""矩阵与投影的数学单元测试。"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, ROOT)

import math3d as m3


def apply(m, p):
    return m3.transform_points(m, np.asarray([p], np.float64))[0]


class TestBasicMatrices(unittest.TestCase):
    def test_translation_scaling(self):
        np.testing.assert_allclose(apply(m3.translation([2, -1, 3]), [1, 1, 1]), [3, 0, 4])
        np.testing.assert_allclose(apply(m3.scaling([2, 3, 4]), [1, 1, 1]), [2, 3, 4])

    def test_rotations(self):
        np.testing.assert_allclose(apply(m3.rotation_x(np.pi / 2), [0, 1, 0]), [0, 0, 1], atol=1e-6)
        np.testing.assert_allclose(apply(m3.rotation_y(np.pi / 2), [1, 0, 0]), [0, 0, -1], atol=1e-6)
        np.testing.assert_allclose(apply(m3.rotation_z(np.pi / 2), [1, 0, 0]), [0, 1, 0], atol=1e-6)

    def test_rotation_preserves_length(self):
        r = m3.rotation_y(0.7) @ m3.rotation_x(-0.3) @ m3.rotation_z(1.1)
        v = np.array([0.3, -1.2, 0.8])
        np.testing.assert_allclose(np.linalg.norm(apply(r, v)), np.linalg.norm(v), rtol=1e-9)

    def test_composition_order(self):
        # M = T * S：先缩放再平移（列向量、M @ p 约定）
        m = m3.translation([5, 0, 0]) @ m3.scaling([2, 2, 2])
        np.testing.assert_allclose(apply(m, [1, 0, 0]), [7, 0, 0])


class TestLookAt(unittest.TestCase):
    def test_eye_maps_to_origin(self):
        eye = np.array([4.0, 5.0, -6.0])
        target = np.array([0.0, 0.0, 0.0])
        v = m3.look_at(eye, target, np.array([0.0, 1.0, 0.0]))
        np.testing.assert_allclose(apply(v, eye), [0, 0, 0], atol=1e-9)

    def test_target_on_negative_z(self):
        eye = np.array([0.0, 0.0, 5.0])
        target = np.array([0.0, 0.0, 0.0])
        v = m3.look_at(eye, target, np.array([0.0, 1.0, 0.0]))
        p = apply(v, target)
        self.assertAlmostEqual(float(p[0]), 0.0, places=9)
        self.assertAlmostEqual(float(p[1]), 0.0, places=9)
        # 相机看向 -z：目标点的视图坐标 z 必须是负的
        self.assertAlmostEqual(float(p[2]), -5.0, places=9)


class TestProjection(unittest.TestCase):
    def _ndc(self, proj, p):
        h = np.hstack([np.asarray([p], np.float64), np.ones((1, 1))])
        clip = h @ proj.T
        return clip[0, :3] / clip[0, 3]

    def test_perspective_near_far(self):
        proj = m3.perspective(60.0, 1.0, 0.1, 100.0)
        self.assertAlmostEqual(float(self._ndc(proj, [0, 0, -0.1])[2]), -1.0, places=6)
        self.assertAlmostEqual(float(self._ndc(proj, [0, 0, -100.0])[2]), 1.0, places=6)

    def test_perspective_fov(self):
        proj = m3.perspective(90.0, 1.0, 0.1, 100.0)
        # 45 度对应视野边缘：x = z 的点落在 NDC x = 1
        self.assertAlmostEqual(float(self._ndc(proj, [2.0, 0, -2.0])[0]), 1.0, places=6)

    def test_orthographic_near_far(self):
        proj = m3.orthographic(10.0, 1.0, 0.1, 50.0)
        self.assertAlmostEqual(float(self._ndc(proj, [0, 0, -0.1])[2]), -1.0, places=6)
        self.assertAlmostEqual(float(self._ndc(proj, [0, 0, -50.0])[2]), 1.0, places=6)

    def test_orthographic_no_foreshortening(self):
        proj = m3.orthographic(10.0, 1.0, 0.1, 50.0)
        a = self._ndc(proj, [2.0, 0, -5.0])
        b = self._ndc(proj, [2.0, 0, -45.0])
        self.assertAlmostEqual(float(a[0]), float(b[0]), places=6)

    def test_normalize_zero(self):
        np.testing.assert_allclose(m3.normalize(np.zeros(3)), np.zeros(3))
        np.testing.assert_allclose(np.linalg.norm(m3.normalize([3.0, 4.0, 0.0])), 1.0)


if __name__ == "__main__":
    unittest.main()
