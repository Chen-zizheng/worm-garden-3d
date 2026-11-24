"""
3D 数学工具：向量、4x4 矩阵、旋转/平移/缩放、透视与正交投影、look_at 视图矩阵。

约定：列向量，矩阵左乘点，即 p_out = M @ p。
"""
import numpy as np


def normalize(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    if n < 1e-12:
        return v.copy()
    return v / n


def vec(x, y, z):
    return np.array([x, y, z], dtype=np.float64)


def translation(t):
    m = np.eye(4)
    m[:3, 3] = np.asarray(t, dtype=np.float64)
    return m


def scaling(s):
    if np.isscalar(s):
        s = (s, s, s)
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = s
    return m


def rotation_x(angle):
    c, s = np.cos(angle), np.sin(angle)
    m = np.eye(4)
    m[1, 1], m[1, 2] = c, -s
    m[2, 1], m[2, 2] = s, c
    return m


def rotation_y(angle):
    c, s = np.cos(angle), np.sin(angle)
    m = np.eye(4)
    m[0, 0], m[0, 2] = c, s
    m[2, 0], m[2, 2] = -s, c
    return m


def rotation_z(angle):
    c, s = np.cos(angle), np.sin(angle)
    m = np.eye(4)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    return m


def perspective(fov_y_deg, aspect, near, far):
    """标准 OpenGL 透视投影矩阵（右手系，相机看向 -Z）。"""
    f = 1.0 / np.tan(np.radians(fov_y_deg) / 2.0)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def orthographic(height_world, aspect, near, far):
    """正交投影：height_world 为可视区高度（世界单位）。"""
    hh = height_world / 2.0
    hw = hh * aspect
    m = np.zeros((4, 4))
    m[0, 0] = 1.0 / hw
    m[1, 1] = 1.0 / hh
    m[2, 2] = -2.0 / (far - near)
    m[2, 3] = -(far + near) / (far - near)
    m[3, 3] = 1.0
    return m


def look_at(eye, target, up):
    """视图矩阵：世界坐标 -> 相机坐标（相机看向 -Z）。"""
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)

    f = normalize(target - eye)
    s = normalize(np.cross(f, up))
    u = np.cross(s, f)

    m = np.eye(4)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -float(np.dot(s, eye))
    m[1, 3] = -float(np.dot(u, eye))
    m[2, 3] = float(np.dot(f, eye))
    return m


def transform_points(m, pts):
    """把 (N,3) 点集变换到新空间（含平移）。"""
    pts = np.asarray(pts, dtype=np.float64)
    h = np.hstack([pts, np.ones((len(pts), 1))])
    return (h @ m.T)[:, :3]


def transform_normals(m, normals):
    """法线只受旋转/缩放影响（这里假设无剪切，用 3x3 部分）。"""
    normals = np.asarray(normals, dtype=np.float64)
    return normals @ m[:3, :3].T
