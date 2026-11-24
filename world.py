"""
游戏世界（纯逻辑，不依赖 pygame）：迷宫生成、玩家运动、碰撞、跳跃、计分、关卡。

坐标约定：
    x, z 为水平面坐标（世界单位），y 为高度。
    原 2D 游戏里的 (px, py) 对应这里的 (x, z)，除以 50 换算成世界单位，
    但起点是 0，所以 x = px / 50, z = py / 50。
"""
import math
import random

import numpy as np

import config as C

DIRECTIONS = {
    "N": (0, -1, "S"),
    "E": (1, 0, "W"),
    "S": (0, 1, "N"),
    "W": (-1, 0, "E"),
}


def cell_center(cell):
    """格子中心 -> (x, z) 世界坐标。"""
    cx, cz = cell
    return np.array([cx * C.CELL + C.CELL / 2.0,
                     cz * C.CELL + C.CELL / 2.0])


class World:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.score = 0
        self.level = 1
        self.time = 0.0
        self.particles = []
        self.spark_timer = 0.0
        # 最近一次"被送回起点"的原因（水面/鸟/终点门），给 HUD 显示用
        self.event = None
        self.event_timer = 0.0
        # 传送回起点后的短暂无敌：否则刚落地就被路过的鸟再撞一次，
        # 玩家会觉得"原地无限循环、根本走不掉"。
        self.spawn_guard = 0.0
        self.new_level()

    # ==========================================================
    # 关卡生成
    # ==========================================================
    def new_level(self):
        self.generation = getattr(self, "generation", 0) + 1
        self.generate_maze()
        self.build_wall_buckets()
        self.water_holes = []
        self.water_cells = set()
        self.generate_water_holes()
        self.medals = []
        self.generate_medals()
        self.enemies = []
        self.generate_enemies()
        self.reset_player()
        self.time = 0.0
        self.collected = 0
        self.particles.clear()
        self.start_center = cell_center(C.START_CELL)
        self.finish_center = cell_center(C.FINISH_CELL)

    def generate_maze(self):
        """递归回溯法生成完美迷宫（和原 2D 游戏一致）。"""
        maze = [
            [{"walls": {d: True for d in DIRECTIONS}, "visited": False}
             for _ in range(C.COLS)]
            for _ in range(C.ROWS)
        ]
        sx, sz = C.START_CELL
        maze[sz][sx]["visited"] = True
        stack = [(sx, sz)]

        while stack:
            x, z = stack[-1]
            neighbors = []
            for d, (dx, dz, opp) in DIRECTIONS.items():
                nx, nz = x + dx, z + dz
                if 0 <= nx < C.COLS and 0 <= nz < C.ROWS and not maze[nz][nx]["visited"]:
                    neighbors.append((nx, nz, d, opp))

            if neighbors:
                nx, nz, d, opp = self.rng.choice(neighbors)
                maze[z][x]["walls"][d] = False
                maze[nz][nx]["walls"][opp] = False
                maze[nz][nx]["visited"] = True
                stack.append((nx, nz))
            else:
                stack.pop()

        # 外圈实体边界墙：3D 版没有 2D 的窗口边缘，必须自己封死边界
        for x in range(C.COLS):
            maze[0][x]["walls"]["N"] = True
            maze[C.ROWS - 1][x]["walls"]["S"] = True
        for z in range(C.ROWS):
            maze[z][0]["walls"]["W"] = True
            maze[z][C.COLS - 1]["walls"]["E"] = True
        self.maze = maze

    def build_wall_buckets(self):
        """把墙矩形按格子分桶，碰撞检测只需查玩家周围 3x3 格。"""
        T = C.WALL_T
        half = T / 2.0
        rects = []
        for z in range(C.ROWS):
            for x in range(C.COLS):
                px, pz = x * C.CELL, z * C.CELL
                w = self.maze[z][x]["walls"]
                if w["N"]:
                    rects.append((px - half, pz - half, px + C.CELL + half, pz + half))
                if w["W"]:
                    rects.append((px - half, pz - half, px + half, pz + C.CELL + half))
                if w["E"] and x == C.COLS - 1:
                    rects.append((px + C.CELL - half, pz - half,
                                  px + C.CELL + half, pz + C.CELL + half))
                if w["S"] and z == C.ROWS - 1:
                    rects.append((px - half, pz + C.CELL - half,
                                  px + C.CELL + half, pz + C.CELL + half))
        self.wall_rects = rects

        buckets = {}
        for r in rects:
            x0, z0, x1, z1 = r
            for cz in range(int(z0 // C.CELL), int(z1 // C.CELL) + 1):
                for cx in range(int(x0 // C.CELL), int(x1 // C.CELL) + 1):
                    buckets.setdefault((cx, cz), []).append(r)
        self.wall_buckets = buckets

    def generate_water_holes(self):
        cells = [(x, z) for z in range(C.ROWS) for x in range(C.COLS)
                 if (x, z) != C.START_CELL and (x, z) != C.FINISH_CELL]
        self.rng.shuffle(cells)
        for cell in cells[:C.WATER_HOLE_COUNT]:
            self.water_cells.add(cell)
            self.water_holes.append({
                "cell": cell,
                "pos": cell_center(cell),
                "radius": C.WATER_HOLE_RADIUS,
            })

    def generate_medals(self):
        cells = [(x, z) for z in range(C.ROWS) for x in range(C.COLS)
                 if (x, z) not in (C.START_CELL, C.FINISH_CELL)
                 and (x, z) not in self.water_cells]
        self.rng.shuffle(cells)
        rewards = [("silver", C.SILVER_VALUE)] * 3 + [("gold", C.GOLD_VALUE)]
        for cell, (kind, value) in zip(cells, rewards):
            self.medals.append({
                "cell": cell,
                "pos": cell_center(cell),
                "kind": kind,
                "value": value,
                "collected": False,
                "phase": self.rng.uniform(0.0, 6.28),
            })

    # ==========================================================
    # 玩家
    # ==========================================================
    def _reset(self, reason):
        """送回起点，并记录原因（HUD 会显示一行提示，免得玩家一头雾水）。"""
        self.reset_player()
        self.event = reason
        self.event_timer = 2.4

    def reset_player(self):
        self.spawn_guard = 1.2
        self.player_pos = cell_center(C.START_CELL)
        self.player_dir = np.array([1.0, 0.0])
        self.player_y = 0.0
        self.player_vy = 0.0
        self.on_ground = True
        self.jump_cooldown = 0.0
        self.spark_timer = 0.0

    def circle_hits_wall(self, pos, radius):
        x, z = pos
        cx, cz = int(x // C.CELL), int(z // C.CELL)
        r2 = radius * radius
        for ox in (-1, 0, 1):
            for oz in (-1, 0, 1):
                for (x0, z0, x1, z1) in self.wall_buckets.get((cx + ox, cz + oz), ()):
                    px = min(max(x, x0), x1)
                    pz = min(max(z, z0), z1)
                    dx = x - px
                    dz = z - pz
                    if dx * dx + dz * dz < r2:
                        return True
        return False

    def move_player(self, direction, dt):
        """分步移动 + 逐轴滑动碰撞（和原 2D 游戏一致，防止穿墙）。"""
        movement = direction * C.BALL_SPEED * dt
        max_step = max(0.02, C.WALL_T / 2.0)
        steps = max(1, math.ceil(float(np.max(np.abs(movement))) / max_step))
        sx, sz = movement[0] / steps, movement[1] / steps

        for _ in range(steps):
            nx = np.array([self.player_pos[0] + sx, self.player_pos[1]])
            if not self.circle_hits_wall(nx, C.BALL_RADIUS):
                self.player_pos[0] = nx[0]
            nz = np.array([self.player_pos[0], self.player_pos[1] + sz])
            if not self.circle_hits_wall(nz, C.BALL_RADIUS):
                self.player_pos[1] = nz[1]

        # 保险：任何情况下都不允许走出迷宫范围
        px = self.player_pos[0]
        pz = self.player_pos[1]
        if px < 0.0:
            self.player_pos[0] = 0.0
        elif px > C.MAZE_W:
            self.player_pos[0] = C.MAZE_W
        if pz < 0.0:
            self.player_pos[1] = 0.0
        elif pz > C.MAZE_H:
            self.player_pos[1] = C.MAZE_H

    def jump(self):
        if self.on_ground and self.jump_cooldown <= 0.0:
            self.player_vy = C.JUMP_V0
            self.on_ground = False
            self.jump_cooldown = 0.25

    # ==========================================================
    # 鸟
    # ==========================================================
    def available_neighbors(self, cell):
        x, z = cell
        out = []
        for d, (dx, dz, _opp) in DIRECTIONS.items():
            if not self.maze[z][x]["walls"][d]:
                nx, nz = x + dx, z + dz
                if 0 <= nx < C.COLS and 0 <= nz < C.ROWS:
                    out.append((nx, nz))
        return out

    def generate_enemies(self):
        count = min(2 + self.level, 8)
        cells = [(x, z) for z in range(C.ROWS) for x in range(C.COLS)
                 if (x, z) not in (C.START_CELL, C.FINISH_CELL)
                 and (x, z) not in self.water_cells]
        self.rng.shuffle(cells)
        for cell in cells[:count]:
            nbrs = self.available_neighbors(cell)
            if not nbrs:
                continue
            self.enemies.append({
                "cell": cell,
                "target": self.rng.choice(nbrs),
                "previous": cell,
                "pos": cell_center(cell),
                "speed": C.ENEMY_SPEED + self.rng.uniform(-0.2, 0.4),
                "phase": self.rng.uniform(0.0, 6.28),
            })

    def update_enemies(self, dt):
        for e in self.enemies:
            target = cell_center(e["target"])
            delta = target - e["pos"]
            dist = float(np.linalg.norm(delta))
            if dist <= 0.04:
                e["pos"] = target.copy()
                e["previous"] = e["cell"]
                e["cell"] = e["target"]
                nbrs = self.available_neighbors(e["cell"])
                if nbrs:
                    alt = [n for n in nbrs if n != e["previous"]]
                    e["target"] = self.rng.choice(alt if alt else nbrs)
            else:
                delta /= dist
                step = e["speed"] * dt
                e["pos"] = target.copy() if step >= dist else e["pos"] + delta * step

    # ==========================================================
    # 苹果 / 粒子
    # ==========================================================
    def add_spark(self):
        p = self.player_pos + np.array([self.rng.uniform(-0.06, 0.06),
                                        self.rng.uniform(-0.06, 0.06)])
        self.particles.append({
            "pos": np.array([p[0], self.player_y + 0.05, p[1]]),
            "vel": np.array([self.rng.uniform(-0.6, 0.6),
                             self.rng.uniform(0.3, 1.2),
                             self.rng.uniform(-0.6, 0.6)]),
            "life": 1.0,
            "decay": self.rng.uniform(0.8, 1.8),
        })
        if len(self.particles) > C.MAX_PARTICLES:
            del self.particles[:len(self.particles) - C.MAX_PARTICLES]

    def update_particles(self, dt):
        for p in self.particles:
            p["pos"] = p["pos"] + p["vel"] * dt
            p["vel"][1] -= 3.0 * dt
            p["life"] -= p["decay"] * dt
        self.particles = [p for p in self.particles if p["life"] > 0.0]

    # ==========================================================
    # 每帧更新
    # ==========================================================
    def update(self, dt, move_dir, jump_pressed):
        dt = min(dt, 0.05)

        if jump_pressed:
            self.jump()

        if move_dir is not None:
            norm = float(np.linalg.norm(move_dir))
            if norm > 0.0:
                d = move_dir / norm
                self.player_dir = d
                before = self.player_pos.copy()
                self.move_player(d, dt)
                # 只有真的走出去了才喷粒子；贴着墙按方向键时原地不动，
                # 否则粒子会在一个不动的虫子身上乱喷，看起来像卡住了。
                if float(np.linalg.norm(self.player_pos - before)) > 0.02:
                    self.spark_timer += dt
                    while self.spark_timer >= C.SPARK_INTERVAL:
                        self.spark_timer -= C.SPARK_INTERVAL
                        self.add_spark()
                else:
                    self.spark_timer = 0.0
            else:
                self.spark_timer = 0.0

        # 跳跃：重力积分
        if not self.on_ground:
            self.player_vy -= C.GRAVITY * dt
            self.player_y += self.player_vy * dt
            if self.player_y <= 0.0:
                self.player_y = 0.0
                self.player_vy = 0.0
                self.on_ground = True
        self.jump_cooldown = max(0.0, self.jump_cooldown - dt)

        self.spawn_guard = max(0.0, self.spawn_guard - dt)
        self.event_timer = max(0.0, self.event_timer - dt)
        self.check_water()
        self.update_enemies(dt)
        self.check_enemy_collision()
        self.update_medals()
        self.check_finish()
        self.update_particles(dt)
        self.time += dt

    def check_water(self):
        if self.player_y > 0.06:      # 跳在空中不算落水
            return
        for hole in self.water_holes:
            if float(np.linalg.norm(self.player_pos - hole["pos"])) < C.BALL_RADIUS + hole["radius"]:
                self._reset("water")
                return

    def check_enemy_collision(self):
        if self.spawn_guard > 0.0:      # 刚被送回起点，先别立刻再撞一次
            return
        for e in self.enemies:
            if float(np.linalg.norm(self.player_pos - e["pos"])) < C.BALL_RADIUS + C.ENEMY_RADIUS:
                self._reset("bird")
                return

    def update_medals(self):
        for m in self.medals:
            if m["collected"]:
                continue
            if float(np.linalg.norm(self.player_pos - m["pos"])) < C.BALL_RADIUS + C.MEDAL_RADIUS:
                m["collected"] = True
                self.score += m["value"]
                self.collected += 1

    def check_finish(self):
        if float(np.linalg.norm(self.player_pos - self.finish_center)) < C.FINISH_RADIUS:
            if self.collected == C.TOTAL_MEDALS:
                self.level += 1
                self.new_level()
            else:
                self._reset("finish")

    def restart(self):
        self.score = 0
        self.level = 1
        self.new_level()
