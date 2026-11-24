"""
场景构建：把 World 的状态变成 3D 网格。

静态几何体（地面/墙/水坑/旗子）每关构建一次并缓存；
动态物体（虫/苹果/鸟/粒子）每帧构建。
"""
import math

import numpy as np

import config as C
import geometry as geo


# ==============================================================
# 墙：把迷宫网格的墙边界合并成尽量少的“长条盒子”
# ==============================================================
def _h_wall(world, x, zb):
    if zb == 0:
        return world.maze[0][x]["walls"]["N"]
    if zb == C.ROWS:
        return world.maze[C.ROWS - 1][x]["walls"]["S"]
    return world.maze[zb][x]["walls"]["N"]


def _v_wall(world, xb, z):
    if xb == 0:
        return world.maze[z][0]["walls"]["W"]
    if xb == C.COLS:
        return world.maze[z][C.COLS - 1]["walls"]["E"]
    return world.maze[z][xb]["walls"]["W"]


def wall_runs(world):
    """返回合并后的墙段 [(kind, a, b, c)]，kind 为 'h' 或 'v'。"""
    runs = []
    for zb in range(C.ROWS + 1):
        x = 0
        while x < C.COLS:
            if not _h_wall(world, x, zb):
                x += 1
                continue
            x0 = x
            while x < C.COLS and _h_wall(world, x, zb):
                x += 1
            runs.append(("h", x0, zb, x))
    for xb in range(C.COLS + 1):
        z = 0
        while z < C.ROWS:
            if not _v_wall(world, xb, z):
                z += 1
                continue
            z0 = z
            while z < C.ROWS and _v_wall(world, xb, z):
                z += 1
            runs.append(("v", xb, z0, z))
    return runs


# ==============================================================
# 静态场景
# ==============================================================
def _flag(cx, cz, color, name, with_pole=True):
    """旗子：底盘（+ 旗杆和旗面）。起点只放底盘，免得挡住第三人称相机。"""
    radius = C.FINISH_RADIUS * (1.15 if with_pole else 0.62)
    parts = [geo.disc((cx, 0.016, cz), radius, 14, color)]
    if with_pole:
        parts += [
            geo.cylinder((cx, 0.62, cz), 0.03, 1.24, 6, (0.75, 0.76, 0.78)),
            geo.quad((cx + 0.02, 1.18, cz), (cx + 0.02, 1.02, cz + 0.34),
                     (cx + 0.36, 1.02, cz + 0.34), (cx + 0.36, 1.18, cz), color),
        ]
    return geo.merge(parts, name)


def build_static(world):
    meshes = []

    # --- 墙 ---
    boxes = []
    for kind, a, b, c in wall_runs(world):
        if kind == "h":
            x0, zb, x1 = a, b, c
            boxes.append(geo.box(
                (x0 + x1) * C.CELL / 2.0, C.WALL_H / 2.0, zb * C.CELL,
                (x1 - x0) * C.CELL + C.WALL_T, C.WALL_H, C.WALL_T,
                C.COL_WALL_TINT, top_color=C.COL_WALL_TOP_TINT,
                tex="stone", tile=C.TEX_TILE_WALL))
        else:
            xb, z0, z1 = a, b, c
            boxes.append(geo.box(
                xb * C.CELL, C.WALL_H / 2.0, (z0 + z1) * C.CELL / 2.0,
                C.WALL_T, C.WALL_H, (z1 - z0) * C.CELL + C.WALL_T,
                C.COL_WALL_TINT, top_color=C.COL_WALL_TOP_TINT,
                tex="stone", tile=C.TEX_TILE_WALL))
    meshes.append(geo.merge(boxes, "walls"))

    # --- 水坑：外圈深色 + 内圈亮色 ---
    water = []
    for hole in world.water_holes:
        cx, cz = hole["pos"]
        water.append(geo.disc((cx, 0.010, cz), hole["radius"] * 1.25, 14, (0.04, 0.16, 0.34)))
        water.append(geo.disc((cx, 0.014, cz), hole["radius"], 14, C.COL_WATER))
    meshes.append(geo.merge(water, "water"))

    # --- 起点 / 终点 ---
    meshes.append(_flag(world.start_center[0], world.start_center[1], C.COL_START,
                         "start_flag", with_pole=False))
    meshes.append(_flag(world.finish_center[0], world.finish_center[1], C.COL_FINISH, "finish_flag"))

    # --- 地面放在最后画 ---
    # 从前往后绘制（水坑/旗子 -> 墙 -> 地面），被遮住的像素在深度测试里直接失败，
    # 就不会白做贴图采样。地面是屏幕上最大的一片，放最后能省掉大量 overdraw。
    # uv 以“世界单位 / TEX_TILE_GROUND”计，所以纹理在全世界里连续、不随三角形拉伸
    # 只铺一整块地面（扩展到迷宫外 GROUND_MARGIN），避免两块几乎共面的地面
    # 在远处产生 Z-fighting 的花纹。uv 从 0 开始，保证非负。
    m = C.GROUND_MARGIN
    tg = C.TEX_TILE_GROUND
    gw = C.MAZE_W + 2 * m
    gh = C.MAZE_H + 2 * m
    meshes.append(geo.quad(
        (-m, 0.0, -m), (gw - m, 0.0, -m),
        (gw - m, 0.0, gh - m), (-m, 0.0, gh - m),
        C.COL_GROUND_TINT, name="ground", tex="grass",
        uvs=[(0.0, 0.0), (gw / tg, 0.0), (gw / tg, gh / tg), (0.0, gh / tg)]))
    return meshes


# ==============================================================
# 动态物体
# ==============================================================
def _worm(world, t):
    """虫：三段球体 + 摆动动画（3D 动画要求）。"""
    d = world.player_dir
    perp = np.array([-d[1], d[0]])
    spheres = []
    segments = ((0.0, C.BALL_RADIUS, C.COL_WORM),
                (0.17, C.BALL_RADIUS * 0.80, C.COL_WORM_DARK),
                (0.32, C.BALL_RADIUS * 0.58, C.COL_WORM_DARK))
    for i, (back, radius, color) in enumerate(segments):
        wiggle = math.sin(t * 9.0 + i * 1.3) * 0.035
        extra_y = 0.02 * math.sin(t * 7.0 + i)
        p = world.player_pos - d * back + perp * wiggle
        y = world.player_y + radius + extra_y
        spheres.append(geo.sphere((p[0], y, p[1]), radius, color, rings=4, segments=8))
    # 接触阴影：贴在正下方地面，跳起来时和虫分离 —— 让"虫在动/在跳"一眼可见
    mid = world.player_pos - d * 0.14
    shadow = geo.disc((mid[0], 0.012, mid[1]),
                      C.BALL_RADIUS * 1.15, 12, (0.11, 0.24, 0.13), name="worm_shadow")
    spheres.append(shadow)
    return geo.merge(spheres, "worm")


def _apples(world, t):
    meshes = []
    for m in world.medals:
        if m["collected"]:
            continue
        color = C.COL_GOLD if m["kind"] == "gold" else C.COL_SILVER
        y = C.MEDAL_HOVER + 0.05 * math.sin(t * 2.5 + m["phase"])
        meshes.append(geo.sphere((m["pos"][0], y, m["pos"][1]),
                                 C.MEDAL_RADIUS, color, rings=3, segments=6))
    return geo.merge(meshes, "apples") if meshes else None


def _birds(world, t):
    meshes = []
    for e in world.enemies:
        ex, ez = e["pos"]
        y = 0.34 + 0.05 * math.sin(t * 6.0 + e["phase"])
        meshes.append(geo.sphere((ex, y, ez), C.ENEMY_RADIUS, C.COL_BIRD,
                                 rings=3, segments=6))
        flap = 0.10 + 0.06 * math.sin(t * 16.0 + e["phase"])
        for side in (-1.0, 1.0):
            meshes.append(geo.quad(
                (ex, y, ez),
                (ex + 0.28 * side, y + flap, ez),
                (ex + 0.20 * side, y + flap, ez + 0.16),
                (ex, y + 0.02, ez + 0.14),
                (0.05, 0.05, 0.08)))
    return geo.merge(meshes, "birds") if meshes else None


def _particles(world, cam_right, cam_up):
    """粒子用面向相机的广告牌四边形绘制。"""
    verts, faces, colors = [], [], []
    for p in world.particles:
        life = max(p["life"], 0.0)
        size = 0.045 * (0.35 + 0.65 * life)
        pos = p["pos"]
        i = len(verts)
        verts.extend([
            pos - cam_right * size - cam_up * size,
            pos + cam_right * size - cam_up * size,
            pos + cam_right * size + cam_up * size,
            pos - cam_right * size + cam_up * size,
        ])
        faces.extend([(i, i + 1, i + 2), (i, i + 2, i + 3)])
        base = np.array(C.COL_SPARK) * (0.35 + 0.65 * life)
        colors.extend([base, base])
    if not verts:
        return None
    return geo.custom(verts, faces, colors, name="particles")


def build_dynamic(world, t, cam_right, cam_up):
    meshes = [_worm(world, t)]
    apples = _apples(world, t)
    if apples is not None:
        meshes.append(apples)
    birds = _birds(world, t)
    if birds is not None:
        meshes.append(birds)
    particles = _particles(world, cam_right, cam_up)
    if particles is not None:
        meshes.append(particles)
    return meshes
