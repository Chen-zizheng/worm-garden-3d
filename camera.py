"""相机：1/2/3 三个预设 + P 键切透视/正交 + 鼠标环绕。"""
import math

import numpy as np

import config as C
import math3d as m3


class Camera:
    def __init__(self):
        self.mode = "perspective"
        self.preset = 1
        self.yaw = 0.0
        self.pitch = 0.55
        self.heading = 0.0
        self.eye = np.array([11.5, 3.0, 15.0])
        self.target = np.array([11.5, 0.0, 7.5])
        self.up = np.array([0.0, 1.0, 0.0])
        self.right = np.array([1.0, 0.0, 0.0])
        self.forward = np.array([0.0, 0.0, -1.0])
        self.ortho_h = 8.0
        self._last_player = None
        self._anchor = None
        self.moving = False
        self.set_preset(1)

    def set_preset(self, preset):
        self.preset = preset
        self.yaw = 0.0
        self.ortho_h = {1: 7.5, 2: 12.0, 3: 19.0}[preset]

    def toggle_projection(self):
        self.mode = "orthographic" if self.mode == "perspective" else "perspective"
        return self.mode

    def update(self, world, dt, align=True):
        p = np.array([world.player_pos[0], 0.0, world.player_pos[1]])

        # 相机朝向跟着"真实位移"转，而不是跟着按键方向转。
        # align=False 时不自动转：玩家按左右键是"屏幕上的左右"，如果相机也跟着转，
        # 左右键的相对方向就会不停变化（画圈），玩家会觉得"按了不走那个方向"。
        if self._last_player is not None:
            delta = p - self._last_player
            moved = float(np.linalg.norm(delta))
            if moved > 0.02:
                self.moving = True
                if align and self.preset == 1:
                    target_heading = math.atan2(delta[2], delta[0])
                    diff = (target_heading - self.heading + math.pi) % (2.0 * math.pi) - math.pi
                    self.heading += diff * min(1.0, dt * 4.0)
            else:
                self.moving = False
        self._last_player = p

        if self.preset == 1:
            # 相机位置稍微滞后于虫子：虫子会在屏幕上往前走一点点，
            # 而不是永远钉在画面中央。这样"我在动"才看得出来。
            if self._anchor is None:
                self._anchor = p.copy()
            elif float(np.linalg.norm(p - self._anchor)) > 2.5:
                # 掉进水坑 / 撞鸟后会被瞬移回起点：这时不要慢慢"飞"过去，
                # 直接把相机锚点搬过去，否则镜头会穿墙飞一段。
                self._anchor = p.copy()
            else:
                k = 1.0 - math.exp(-dt * 5.5)
                self._anchor = self._anchor + (p - self._anchor) * k
            ang = self.heading + self.yaw
            back = np.array([-math.cos(ang), 0.0, -math.sin(ang)])
            self.target = (self._anchor
                           + np.array([0.0, 0.34 + world.player_y * 0.6, 0.0]))
            # 相机不能跑到迷宫外：一旦越界，边界墙（0.75 高）会把虫完全挡住。
            # 所以把后拉距离缩短到“刚好留在迷宫内”，贴着西/东/南/北边界时
            # 相机就变成更陡的俯视，仍能看见虫。
            margin = C.WALL_T
            hi_x, hi_z = C.MAZE_W - margin, C.MAZE_H - margin
            back_dist = 2.15
            for axis, lo, hi in ((0, margin, hi_x), (2, margin, hi_z)):
                b = float(back[axis])
                p_axis = float(self.target[axis])
                if abs(b) > 1e-6:
                    limit = (hi - p_axis) / b if b > 0 else (lo - p_axis) / b
                    back_dist = min(back_dist, max(limit, 0.0))
            back_dist = max(back_dist, 0.30)
            self.eye = (self.target + back * back_dist
                        + np.array([0.0, 1.05 + self.pitch * 0.9, 0.0]))
        elif self.preset == 2:
            self._anchor = None
            self.target = p.copy()
            self.eye = p + np.array([0.001, 8.5, 0.0])
        else:
            self._anchor = None
            center = np.array([C.MAZE_W / 2.0, 0.0, C.MAZE_H / 2.0])
            self.target = center
            self.eye = center + np.array([C.MAZE_W * 0.40, 15.5, C.MAZE_H * 0.72])

        self._update_basis()

    def _update_basis(self):
        self.up = np.array([0.0, 0.0, -1.0]) if self.preset == 2 else np.array([0.0, 1.0, 0.0])
        self.forward = m3.normalize(self.target - self.eye)
        self.right = m3.normalize(np.cross(self.forward, self.up))
        self.up = np.cross(self.right, self.forward)

    def ground_basis(self):
        """屏幕"上"和屏幕"右"在地面上的方向（单位向量，XZ）。

        按键按这两个方向解释，所以"↑"永远是往屏幕里走、"→"永远是往屏幕右走，
        不管相机被鼠标转到哪个方位。俯视（相机垂直向下）时 forward 没有地面分量，
        退化成用相机 up 向量的地面投影（也就是屏幕上方）。
        """
        view = self.view_matrix()

        def ground(v):
            """把三维向量投到地面 (XZ) 并归一化，同时返回投影前的长度。"""
            a = np.array([float(v[0]), float(v[2])])
            n = float(np.linalg.norm(a))
            return (a / n if n > 1e-6 else None), n

        # 注意：必须先用"投影前的长度"判断相机是否几乎垂直向下，
        # 再归一化。preset 2 的 eye 有 0.001 的 x 偏移，forward 的地面分量
        # 只有 1e-4 量级，先归一化会把这个数值噪声放大成 (-1, 0)，
        # 结果按上键变成往西走 —— 正是用户看到的"方向乱跳"。
        fwd, fwd_len = ground(-view[2, :3])
        if fwd is None or fwd_len < 0.35:
            up_g, _ = ground(view[1, :3])
            if up_g is not None:
                fwd = up_g
            elif fwd is None:
                fwd = np.array([0.0, -1.0])
        right, _ = ground(view[0, :3])
        if right is None:
            right = np.array([-fwd[1], fwd[0]])
        return fwd, right

    # 正交模式下把眼睛后移，避免近平面把可见地面裁掉（否则屏幕下缘露天空）
    ORTHO_EYE_BACK = 40.0

    def view_matrix(self):
        eye = self.eye
        if self.mode == "orthographic":
            eye = self.eye - self.forward * self.ORTHO_EYE_BACK
        return m3.look_at(eye, self.target, self.up)

    def proj_matrix(self, aspect):
        if self.mode == "perspective":
            return m3.perspective(C.FOV_Y, aspect, C.NEAR, C.FAR)
        far = self.ORTHO_EYE_BACK + C.FAR
        return m3.orthographic(self.ortho_h, aspect, C.NEAR, far)

    def orbit(self, dx, dy):
        self.yaw += dx * 0.006
        self.pitch = float(np.clip(self.pitch - dy * 0.004, -0.2, 1.6))
