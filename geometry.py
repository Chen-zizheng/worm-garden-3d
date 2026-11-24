"""
几何体生成：把 3D 物体生成为“三角面网格”字典。

网格字典字段：
    name      : str
    verts     : (N, 3) float32  物体空间顶点
    faces     : (F, 3) int32    每个三角面的三个顶点索引（逆时针朝外）
    colors    : (F, 3) float32  每个三角面的基色（0~1）
    uvs       : (N, 2) float32 或 None  每顶点纹理坐标（以“世界单位 / tile”计）
    tex       : str 或 None     纹理材质名（见 assets.MATERIALS）
    cull      : bool            是否做背面剔除（封闭凸物体为 True）
    two_sided : bool            是否双面可见（地面/水面等为 True）
"""
import numpy as np

import math3d


def _mesh(verts, faces, colors, cull=True, two_sided=False, name="",
          uvs=None, tex=None):
    return {
        "name": name,
        "verts": np.asarray(verts, dtype=np.float32),
        "faces": np.asarray(faces, dtype=np.int32).reshape(-1, 3),
        "colors": np.asarray(colors, dtype=np.float32).reshape(-1, 3),
        "uvs": None if uvs is None else np.asarray(uvs, dtype=np.float32).reshape(-1, 2),
        "tex": tex,
        "cull": bool(cull),
        "two_sided": bool(two_sided),
    }


def box(cx, cy, cz, sx, sy, sz, color, skip=("bottom",), top_color=None,
        name="box", tex=None, tile=1.0):
    """以中心 (cx,cy,cz)、尺寸 (sx,sy,sz) 生成闭合并朝外的立方体。

    每个面有独立的 4 个顶点，这样 (u,v) 才能按面正确展开、不会在棱边串味。
    tex/tile: 材质名与“一个纹理重复对应多少世界单位”。
    """
    x0, x1 = cx - sx / 2.0, cx + sx / 2.0
    y0, y1 = cy - sy / 2.0, cy + sy / 2.0
    z0, z1 = cz - sz / 2.0, cz + sz / 2.0
    u_scale = 1.0 / float(tile) if tile else 1.0

    def corner_uv(key, x, y, z):
        if key in ("front", "back"):
            return ((x - x0) * u_scale, (y1 - y) * u_scale)
        if key == "right":
            return ((z1 - z) * u_scale, (y1 - y) * u_scale)
        if key == "left":
            return ((z - z0) * u_scale, (y1 - y) * u_scale)
        if key == "top":
            return ((x - x0) * u_scale, (z - z0) * u_scale)
        return ((x - x0) * u_scale, (z1 - z) * u_scale)      # bottom

    # 每个面的 4 个角点（顺序与下面两个三角面一致，从外部看逆时针）
    faces_def = {
        "front": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        "back": [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],
        "right": [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],
        "left": [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
        "top": [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)],
        "bottom": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
    }
    tri_orders = ((0, 1, 2), (0, 2, 3))

    verts, uvs, faces, colors = [], [], [], []
    for key, quad_pts in faces_def.items():
        if key in skip:
            continue
        base = len(verts)
        for p in quad_pts:
            verts.append(p)
            uvs.append(corner_uv(key, *p))
        for tri in tri_orders:
            faces.append(tuple(base + i for i in tri))
            c = top_color if (key == "top" and top_color is not None) else color
            colors.append(c)
    return _mesh(verts, faces, colors, cull=True, name=name,
                 uvs=(uvs if tex is not None else None), tex=tex)


def quad(p0, p1, p2, p3, color, two_sided=True, name="quad", tex=None, uvs=None):
    """用四个角点构造一个四边形（0-1-2, 0-2-3 两个三角面）。"""
    verts = [p0, p1, p2, p3]
    faces = [(0, 1, 2), (0, 2, 3)]
    colors = [color] * 2
    if uvs is None and tex is not None:
        uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    return _mesh(verts, faces, colors, cull=not two_sided, two_sided=two_sided,
                 name=name, uvs=uvs, tex=tex)


def disc(center, radius, segments, color, name="disc"):
    """水平圆盘（在 XZ 平面上，y = center[1]）。"""
    cx, cy, cz = center
    verts = [(cx, cy, cz)]
    for i in range(segments):
        a = 2.0 * np.pi * i / segments
        verts.append((cx + radius * np.cos(a), cy, cz + radius * np.sin(a)))
    faces = []
    for i in range(segments):
        faces.append((0, 1 + i, 1 + (i + 1) % segments))
    return _mesh(verts, faces, [color] * len(faces), cull=False, two_sided=True, name=name)


def cylinder(center, radius, height, segments, color, name="cylinder"):
    """竖直圆柱（用于旗杆）。"""
    cx, cy, cz = center
    half = height / 2.0
    verts = []
    for y in (cy - half, cy + half):
        for i in range(segments):
            a = 2.0 * np.pi * i / segments
            verts.append((cx + radius * np.cos(a), y, cz + radius * np.sin(a)))
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j))
        faces.append((i, segments + j, segments + i))
    return _mesh(verts, faces, [color] * len(faces), cull=False, two_sided=True, name=name)


def sphere(center, radius, color, rings=4, segments=8, name="sphere"):
    """UV 球：rings 为竖直分段，segments 为绕圈分段。"""
    cx, cy, cz = center
    verts = []
    for i in range(rings + 1):
        phi = np.pi * i / rings
        for j in range(segments):
            th = 2.0 * np.pi * j / segments
            verts.append((
                cx + radius * np.sin(phi) * np.cos(th),
                cy + radius * np.cos(phi),
                cz + radius * np.sin(phi) * np.sin(th),
            ))

    def idx(i, j):
        return i * segments + (j % segments)

    faces = []
    for i in range(rings):
        for j in range(segments):
            a, b = idx(i, j), idx(i + 1, j)
            c, d = idx(i + 1, j + 1), idx(i, j + 1)
            faces.append((a, c, b))
            faces.append((a, d, c))
    return _mesh(verts, faces, [color] * len(faces), cull=False, two_sided=True, name=name)


def merge(meshes, name="merged"):
    """把多个网格合并成一个（减少绘制调用）。"""
    verts, faces, colors, uvs = [], [], [], []
    offset = 0
    all_uv = bool(meshes) and all(m.get("uvs") is not None for m in meshes)
    tex = meshes[0].get("tex") if meshes else None
    if any(m.get("tex") != tex for m in meshes):
        tex = None
    for m in meshes:
        verts.append(m["verts"])
        faces.append(m["faces"] + offset)
        colors.append(m["colors"])
        if all_uv:
            uvs.append(m["uvs"])
        offset += len(m["verts"])
    return _mesh(
        np.vstack(verts) if verts else np.zeros((0, 3)),
        np.vstack(faces) if faces else np.zeros((0, 3), dtype=np.int32),
        np.vstack(colors) if colors else np.zeros((0, 3)),
        cull=all(m["cull"] for m in meshes) if meshes else True,
        two_sided=any(m["two_sided"] for m in meshes) if meshes else False,
        name=name,
        uvs=(np.vstack(uvs) if (all_uv and uvs) else None),
        tex=tex,
    )


def custom(verts, faces, colors, two_sided=True, name="custom"):
    """直接由顶点/面/颜色数组构造网格（粒子广告牌等）。"""
    return _mesh(verts, faces, colors, cull=not two_sided, two_sided=two_sided, name=name)


def transform(mesh, m, name=None):
    """对网格顶点应用 4x4 变换，返回新网格。"""
    out = dict(mesh)
    out["verts"] = math3d.transform_points(m, mesh["verts"]).astype(np.float32)
    if name is not None:
        out["name"] = name
    return out
