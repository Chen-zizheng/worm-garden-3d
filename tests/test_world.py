"""游戏世界逻辑测试：迷宫连通性、碰撞、跳跃物理、计分、状态重置。"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, ROOT)

import config as C
import world as world_mod
from world import World, cell_center

DT = 1.0 / 60.0


def simulate(w, seconds, move=(0.0, 0.0), jump_at=()):
    frames = int(round(seconds / DT))
    mv = np.array(move, dtype=float)
    for i in range(frames):
        w.update(DT, mv, i in jump_at)


class TestMaze(unittest.TestCase):
    def test_all_cells_reachable(self):
        """递归回溯生成的是完美迷宫：所有格子必须连通。"""
        w = World(seed=7)
        seen = {C.START_CELL}
        stack = [C.START_CELL]
        while stack:
            cell = stack.pop()
            for nb in w.available_neighbors(cell):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        self.assertEqual(len(seen), C.COLS * C.ROWS)

    def test_border_is_closed(self):
        w = World(seed=7)
        for x in range(C.COLS):
            self.assertTrue(w.maze[0][x]["walls"]["N"])
            self.assertTrue(w.maze[C.ROWS - 1][x]["walls"]["S"])
        for z in range(C.ROWS):
            self.assertTrue(w.maze[z][0]["walls"]["W"])
            self.assertTrue(w.maze[z][C.COLS - 1]["walls"]["E"])

    def test_wall_buckets_cover_every_rect(self):
        w = World(seed=7)
        total = sum(len(v) for v in w.wall_buckets.values())
        self.assertGreaterEqual(total, len(w.wall_rects))
        self.assertGreater(len(w.wall_rects), 100)


class TestCollision(unittest.TestCase):
    def test_center_of_cell_is_free(self):
        w = World(seed=7)
        for cell in ((0, 7), (11, 7), (22, 7), (5, 3)):
            self.assertFalse(w.circle_hits_wall(cell_center(cell), C.BALL_RADIUS))

    def test_boundary_wall_blocks(self):
        w = World(seed=7)
        start = cell_center(C.START_CELL)
        self.assertTrue(w.circle_hits_wall(start + np.array([-0.30, 0.0]), C.BALL_RADIUS))

    def test_cannot_walk_through_wall(self):
        w = World(seed=7)
        simulate(w, 2.0, move=(-1.0, 0.0))
        self.assertGreaterEqual(float(w.player_pos[0]), C.WALL_T * 0.5 + C.BALL_RADIUS - 0.02)

    def test_slides_along_wall(self):
        """斜着撞墙时应该沿墙滑动，而不是完全停住。"""
        w = World(seed=7)
        w.player_pos = cell_center((0, 7))
        simulate(w, 1.5, move=(-1.0, 1.0))
        self.assertNotAlmostEqual(float(w.player_pos[1]), cell_center((0, 7))[1], places=2)


class TestJump(unittest.TestCase):
    def test_jump_apex_and_landing(self):
        w = World(seed=7)
        z_max = 0.0
        landed_frame = None
        w.update(DT, np.zeros(2), True)
        for i in range(200):
            w.update(DT, np.zeros(2), False)
            z_max = max(z_max, float(w.player_y))
            if w.on_ground and i > 2:
                landed_frame = i
                break
        expected_apex = C.JUMP_V0 ** 2 / (2.0 * C.GRAVITY)     # 3.2^2 / 20 = 0.512
        self.assertAlmostEqual(z_max, expected_apex, delta=0.05)
        self.assertIsNotNone(landed_frame)
        air_time = (landed_frame + 1) * DT
        self.assertAlmostEqual(air_time, 2.0 * C.JUMP_V0 / C.GRAVITY, delta=0.05)

    def test_cannot_double_jump(self):
        w = World(seed=7)
        w.update(DT, np.zeros(2), True)
        for _ in range(5):
            w.update(DT, np.zeros(2), True)
        self.assertFalse(w.on_ground)
        self.assertLessEqual(float(w.player_y), C.JUMP_V0 ** 2 / (2.0 * C.GRAVITY) + 0.01)


class TestCollectibles(unittest.TestCase):
    def test_score_and_count(self):
        w = World(seed=7)
        self.assertEqual(len(w.medals), C.TOTAL_MEDALS)
        medal = w.medals[0]
        w.player_pos = medal["pos"].copy()
        w.update(DT, np.zeros(2), False)
        self.assertEqual(w.collected, 1)
        self.assertEqual(w.score, medal["value"])

    def test_water_resets_player(self):
        w = World(seed=7)
        hole = w.water_holes[0]
        w.player_pos = hole["pos"].copy()
        w.update(DT, np.zeros(2), False)
        start = cell_center(C.START_CELL)
        np.testing.assert_allclose(w.player_pos, start, atol=1e-6)

    def test_jumping_over_water_is_safe(self):
        w = World(seed=7)
        hole = w.water_holes[0]
        w.player_pos = hole["pos"].copy()
        w.player_y = 0.4
        w.on_ground = False
        w.player_vy = 0.0
        w.check_water()
        np.testing.assert_allclose(w.player_pos, hole["pos"], atol=1e-6)

    def test_finish_without_medals_resets(self):
        w = World(seed=7)
        w.player_pos = w.finish_center.copy()
        w.update(DT, np.zeros(2), False)
        np.testing.assert_allclose(w.player_pos, cell_center(C.START_CELL), atol=1e-6)
        self.assertEqual(w.level, 1)

    def test_finish_with_all_medals_advances_level(self):
        w = World(seed=7)
        for m in w.medals:
            m["collected"] = True
            w.collected += 1
        w.player_pos = w.finish_center.copy()
        w.update(DT, np.zeros(2), False)
        self.assertEqual(w.level, 2)
        self.assertEqual(len(w.medals), C.TOTAL_MEDALS)


class TestParticles(unittest.TestCase):
    def test_particle_cap(self):
        w = World(seed=7)
        for _ in range(C.MAX_PARTICLES + 80):
            w.add_spark()
        self.assertLessEqual(len(w.particles), C.MAX_PARTICLES)

    def test_particles_expire(self):
        w = World(seed=7)
        for _ in range(20):
            w.add_spark()
        for _ in range(400):
            w.update_particles(DT)
        self.assertEqual(len(w.particles), 0)

    def test_walking_emits_particles(self):
        w = World(seed=7)
        simulate(w, 0.6, move=(1.0, 0.0))
        self.assertGreater(len(w.particles), 0)


class TestRestart(unittest.TestCase):
    def test_restart_resets(self):
        w = World(seed=7)
        w.score = 250
        w.level = 3
        w.restart()
        self.assertEqual(w.score, 0)
        self.assertEqual(w.level, 1)
        self.assertEqual(w.collected, 0)
        self.assertEqual(len(w.medals), C.TOTAL_MEDALS)
        np.testing.assert_allclose(w.player_pos, cell_center(C.START_CELL))


if __name__ == "__main__":
    unittest.main()
