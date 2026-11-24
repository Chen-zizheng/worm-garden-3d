"""
生成提交用的演示视频（2–4 分钟，1280x800，MP4）。

无窗口、不依赖 pygame：世界逻辑与渲染用项目自己的模块，HUD 与字幕用 Pillow 画，
帧通过管道喂给 ffmpeg 编码成 H.264。

用法：
    python make_video.py                          # 需要 ffmpeg 在 PATH 或 --ffmpeg 指定
    python make_video.py --ffmpeg D:/tools/ffmpeg.exe
    python make_video.py --quality 0 --fps 15      # 更快、更小的草稿

输出：
    video/worm_garden_demo.mp4
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config as C
from camera import Camera
from raster import Renderer
from render_scene import draw_world
from world import World, cell_center

WINDOW_W, WINDOW_H = 1280, 800
VIDEO_DIR = os.path.join(HERE, "video")
FONT_PATH = "C:/Windows/Fonts/consola.ttf"
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
PRESET_NAMES = {1: "CHASE", 2: "TOP-DOWN", 3: "OVERVIEW"}


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def cell_of(pos):
    return (int(math.floor(float(pos[0]))), int(math.floor(float(pos[1]))))


def bfs_path(world, start, goal, blocked=frozenset()):
    """迷宫内 BFS，返回 start 之后到 goal 的格子序列（含 goal），不可达返回 []。"""
    if start == goal:
        return []
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for nb in world.available_neighbors(cur):
            if nb in prev or nb in blocked:
                continue
            prev[nb] = cur
            q.append(nb)
    if goal not in prev:
        return []
    path = []
    cur = goal
    while cur != start:
        path.append(cur)
        cur = prev[cur]
    return path[::-1]


class Director:
    """脚本化推进世界状态、渲染每一帧、画 HUD/字幕、写进 ffmpeg。"""

    def __init__(self, ffmpeg, out_path, seed=7, quality=1, fps=20):
        self.rw, self.rh = C.QUALITY_PRESETS[quality]
        self.fps = fps
        self.dt = 1.0 / fps
        self.renderer = Renderer(self.rw, self.rh)
        self.world = World(seed=seed)
        self.camera = Camera()
        self.bilinear = C.TEXTURE_BILINEAR
        self.checker = False
        self.bloom = C.BLOOM_ENABLED
        self.time = 0.0
        self.frame_ms = 0.0
        self.rng = __import__("random").Random(11)
        self.waypoints = []
        self.jump_every = 0.0
        self.jump_clock = 0.0
        self.last_pos = None
        self.stuck_clock = 0.0
        self.frame_index = 0
        self.font = load_font(FONT_PATH, 20)
        self.font_small = load_font(FONT_PATH, 17)
        self.font_title = load_font(FONT_BOLD, 30)
        self.font_sub = load_font(FONT_PATH, 21)

        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error",
             "-f", "rawvideo", "-vcodec", "rawvideo",
             "-s", f"{WINDOW_W}x{WINDOW_H}", "-pix_fmt", "rgb24",
             "-r", str(fps), "-i", "-",
             "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "20", "-preset", "veryfast",
             "-movflags", "+faststart", out_path],
            stdin=subprocess.PIPE)
        print(f"ffmpeg -> {out_path}  ({self.rw}x{self.rh} internal, {fps} fps)")

    # -------------------------------------------------- 自动驾驶
    def tour_route(self):
        """沿走廊把虫子带着走一圈（不碰奖牌），用于展示相机/投影/光影。"""
        for attempt in range(40):
            free = [(x, z) for z in range(C.ROWS) for x in range(C.COLS)]
            tx, tz = self.rng.choice(free)
            blocked = {m["cell"] for m in self.world.medals} | {C.FINISH_CELL}
            path = bfs_path(self.world, cell_of(self.world.player_pos), (tx, tz),
                            blocked=blocked)
            if len(path) >= 6:
                self.waypoints = [cell_center(c) for c in path]
                return
        self.waypoints = []

    def mission_route(self):
        """正式通关：依次吃最近的奖牌，最后跑向终点旗。"""
        start = cell_of(self.world.player_pos)
        targets = [m["pos"] for m in self.world.medals if not m["collected"]]
        targets.append(self.world.finish_center)
        wps = []
        cur = start
        pending = list(range(len(targets)))
        while pending:
            best = None
            for i in pending:
                tgt = targets[i]
                path = bfs_path(self.world, cur, cell_of(tgt))
                if not path and cell_of(tgt) != cur:
                    continue
                if best is None or len(path) < len(best[1]):
                    best = (i, tgt, path)
            if best is None:
                break
            i, tgt, path = best
            pending.remove(i)
            wps.extend(cell_center(c) for c in path)
            cur = cell_of(tgt)
        self.waypoints = wps

    def autopilot_move(self, mission=False):
        if not self.waypoints:
            if mission:
                self.mission_route()
            else:
                self.tour_route()
            if not self.waypoints:
                return np.zeros(2)
        target = self.waypoints[0]
        delta = target - self.world.player_pos
        dist = float(np.linalg.norm(delta))
        if dist < 0.30:
            self.waypoints.pop(0)
            return self.autopilot_move(mission)
        # 轴对齐转向：走廊里的路径都是四个方向，把很小的横向分量舍掉，
        # 否则虫子会斜着撞进墙角，两个轴同时被挡。
        if abs(delta[0]) < 0.18:
            delta[0] = 0.0
        if abs(delta[1]) < 0.18:
            delta[1] = 0.0
        n = float(np.linalg.norm(delta))
        if n < 1e-6:
            self.waypoints.pop(0)
            return self.autopilot_move(mission)
        return delta / n

    def want_jump(self, moving):
        if not moving or not self.world.on_ground:
            return False
        # 预判：前方 0.85 单位处是水坑格子就起跳（空中不会被判定落水，
        # 起跳水平距离 4.6 * 0.64 ≈ 2.9 单位，足够跨过 1 单位的格子）
        ahead = self.world.player_pos + self.world.player_dir * 0.85
        if cell_of(ahead) in self.world.water_cells:
            return True
        self.jump_clock += self.dt
        if self.jump_every > 0.0 and self.jump_clock >= self.jump_every:
            self.jump_clock = 0.0
            return True
        return False

    # -------------------------------------------------- 每帧
    def render(self):
        t0 = time.perf_counter()
        draw_world(self.renderer, self.world, self.camera, self.time,
                   bilinear=self.bilinear, checker=self.checker, bloom=self.bloom)
        img = self.renderer.to_image()
        self.frame_ms = (time.perf_counter() - t0) * 1000.0
        return Image.fromarray(img).resize((WINDOW_W, WINDOW_H), Image.BILINEAR)

    def wrap_text(self, d, text, font, max_width):
        words = text.split()
        lines, cur = [], ""
        for word in words:
            trial = (cur + " " + word).strip()
            if not cur or d.textlength(trial, font=font) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def draw_overlay(self, base, caption, title=None):
        overlay = Image.new("RGBA", (WINDOW_W, WINDOW_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        w = self.world

        d.rectangle([0, 0, WINDOW_W, 38], fill=(4, 8, 20, 160))
        left = (f"LEVEL {w.level}   SCORE {w.score}   "
                f"APPLES {w.collected}/{C.TOTAL_MEDALS}   TIME {w.time:5.1f}s")
        d.text((12, 8), left, font=self.font, fill=(240, 246, 255))
        filt = "BILINEAR" if self.bilinear else "NEAREST"
        fog = "FOG" if C.FOG_ENABLED else "-"
        glow = "BLOOM" if self.bloom else "-"
        right = (f"{PRESET_NAMES[self.camera.preset]}  "
                 f"{self.camera.mode.upper()}  {filt}  {fog}  {glow}  "
                 f"{self.frame_ms:5.1f} ms  {self.rw}x{self.rh}")
        tw = d.textlength(right, font=self.font)
        d.text((WINDOW_W - tw - 12, 8), right, font=self.font, fill=(140, 235, 215))

        if caption:
            body = self.wrap_text(d, caption, self.font_sub, WINDOW_W - 72)
            bar_h = (48 if title else 0) + 26 * len(body) + 18
            d.rectangle([0, WINDOW_H - bar_h, WINDOW_W, WINDOW_H],
                        fill=(4, 8, 20, 180))
            y = WINDOW_H - bar_h + 10
            if title:
                d.text((36, y), title, font=self.font_title, fill=(255, 255, 255))
                y += 38
            for line in body:
                d.text((36, y), line, font=self.font_sub, fill=(198, 216, 236))
                y += 26

        return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    def segment(self, duration, caption, title=None, preset=None, mode=None,
                bilinear=None, checker=None, fog=None, bloom=None, autopilot=False,
                mission=False, jump_every=0.0, time_scale=1):
        if preset is not None:
            self.camera.set_preset(preset)
            self.waypoints = []
        if mode is not None and self.camera.mode != mode:
            self.camera.toggle_projection()
        if bilinear is not None:
            self.bilinear = bilinear
        if checker is not None:
            self.checker = checker
        if fog is not None:
            C.FOG_ENABLED = fog
        if bloom is not None:
            self.bloom = bloom
        self.jump_every = jump_every
        if autopilot:
            self.world.enemies = []      # 演示路线不撞鸟：撞到会瞬移回起点

        self.last_pos = self.world.player_pos.copy()
        frames = max(1, int(round(duration * self.fps)))
        for _ in range(frames):
            for _ in range(max(1, time_scale)):
                if autopilot:
                    self.world.enemies = []
                    move = self.autopilot_move(mission)
                    jump = self.want_jump(True)
                    moved = float(np.linalg.norm(self.world.player_pos - self.last_pos))
                    if moved > 1.5:        # 被水坑/鸟送回起点：重新规划路线
                        self.waypoints = []
                    elif np.any(move) and moved < 0.02:
                        self.stuck_clock += self.dt
                        if self.stuck_clock > 0.5:
                            self.waypoints = []
                            self.stuck_clock = 0.0
                    else:
                        self.stuck_clock = 0.0
                    self.last_pos = self.world.player_pos.copy()
                else:
                    move = np.zeros(2)
                    jump = False
                self.world.update(self.dt, move, jump)
                self.camera.update(self.world, self.dt)
                self.time += self.dt
            frame = self.draw_overlay(self.render(), caption, title)
            self.proc.stdin.write(frame.tobytes())
            self.frame_index += 1
            if self.frame_index % 40 == 0:
                print(f"  frame {self.frame_index:5d}  "
                      f"render {self.frame_ms:5.1f} ms  "
                      f"world {self.world.player_pos.round(2)}", flush=True)

    def close(self):
        self.proc.stdin.close()
        code = self.proc.wait()
        print(f"ffmpeg exit {code}, {self.frame_index} frames")
        return code == 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ffmpeg", default=os.environ.get("FFMPEG", "ffmpeg"))
    ap.add_argument("--out", default=os.path.join(VIDEO_DIR, "worm_garden_demo.mp4"))
    ap.add_argument("--quality", type=int, default=1)
    ap.add_argument("--fps", type=int, default=20)
    args = ap.parse_args(argv)

    ffmpeg = args.ffmpeg
    if not os.path.isabs(ffmpeg) and not shutil.which(ffmpeg):
        sys.exit("找不到 ffmpeg：请用 --ffmpeg 指定可执行文件路径，或把它加到 PATH。")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    d = Director(ffmpeg, args.out, seed=7, quality=args.quality, fps=args.fps)

    # 1. 片头：夜色全景 + 深度雾 + bloom
    d.segment(9.0, "A night-garden remake of the 2D maze game. Every pixel is "
                   "computed on the CPU by the NumPy rasteriser in this project: "
                   "no OpenGL, no 3D library, no shader pipeline.",
              title="Worm Garden Adventure 3D  -  CGP final project",
              preset=3, mode="perspective", fog=True, bloom=True,
              bilinear=True, checker=False)

    # 2. 追逐视角自动寻路
    d.segment(13.0, "Chase camera, perspective. The worm walks the corridors with "
                    "3D collision against the wall boxes and a small jump physics "
                    "step; the HUD shows the internal render resolution.",
              preset=1, mode="perspective", autopilot=True)

    # 3. 跳跃与粒子
    d.segment(8.0, "Jump (v0 = 3.2, g = 10) with the landing spark particles, "
                   "pool capped at 250 particles.",
              autopilot=True, jump_every=0.9)

    # 4. 同一视角切正交投影
    d.segment(8.0, "P toggles the projection: orthographic has no foreshortening, "
                   "so corridor walls keep their real width.",
              mode="orthographic", autopilot=True)

    # 5. 俯视双投影
    d.segment(8.0, "Camera preset 2: top-down, perspective view.",
              preset=2, mode="perspective", autopilot=True)
    d.segment(8.0, "The same preset in orthographic: the maze reads like the "
                   "original 2D game.",
              preset=2, mode="orthographic", autopilot=True)

    # 6. 全景双投影
    d.segment(8.0, "Camera preset 3: overview of the whole 23 x 15 maze.",
              preset=3, mode="perspective")
    d.segment(7.0, "Overview, orthographic projection.",
              preset=3, mode="orthographic")

    # 7. 美术方向：暮色花园
    d.segment(7.0, "Art direction: Night Garden. 1600 stars, a moon glow, cool "
                   "moonlight as the key light, a colour grade and a vignette are "
                   "all produced by this renderer, not by a post-processing library.",
              preset=3, mode="perspective", bilinear=True)

    # 8. Part B 扩展 B：深度雾
    d.segment(8.0, "Part B extension B: depth fog reconstructed from the z-buffer. "
                   "FOG OFF.",
              preset=3, mode="perspective", fog=False)
    d.segment(8.0, "FOG ON: a linear fog factor from per-pixel depth, blended "
                   "after rasterisation. Distant walls melt into the night sky.",
              preset=3, mode="perspective", fog=True)

    # 9. Part B 扩展 C：bloom 泛光
    d.segment(8.0, "Part B extension C: screen-space bloom. BLOOM OFF.",
              preset=1, mode="perspective", fog=True, bilinear=True, bloom=False)
    d.segment(8.0, "BLOOM ON: bright pixels are downsampled, box-blurred and added "
                   "back, so the fluorescent worm, the apples and the moon bleed "
                   "light into their neighbours.",
              preset=1, mode="perspective", bloom=True)

    # 10. Part B 扩展 A：纹理过滤与走样
    d.segment(8.0, "Part B extension A: bilinear texture filtering. A high "
                   "frequency checkerboard exposes aliasing with NEAREST sampling.",
              preset=1, mode="perspective", fog=True, checker=True, bilinear=False)
    d.segment(8.0, "BILINEAR: four texels blended per sample. Softer transitions, "
                   "but still no mip-mapping.",
              preset=1, mode="perspective", checker=True, bilinear=True)
    d.segment(6.0, "Back to the real stone and grass textures with bilinear "
                   "filtering enabled.",
              checker=False, bilinear=True)

    # 11. 完整通关：BFS 寻路吃满四个奖牌 -> 终点旗（2x 时间压缩）
    d.segment(36.0, "Automated play-through at 2x speed: BFS path-finding collects "
                    "the four medals, then heads for the finish flag. Reaching the "
                    "flag resets the level unless every medal is collected.",
              preset=3, mode="perspective", autopilot=True, mission=True,
              checker=False, bilinear=True, time_scale=2)

    if d.world.level > 1:
        d.segment(8.0, "All medals collected: the level is complete and the "
                       "recursive backtracker carves a new 23 x 15 maze.",
                  preset=3, mode="perspective", autopilot=True)
    else:
        d.segment(6.0, "Reaching the flag without every medal only restarts the "
                       "run - the flag stays closed.",
                  preset=3, mode="perspective")

    # 12. 片尾：最后一帧再停 6 秒
    d.segment(6.0, "Python + NumPy software renderer, ~4200 lines, all textures "
                   "generated procedurally with Pillow. No external art assets.",
              preset=3, mode="perspective", fog=True, bilinear=True)

    ok = d.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
