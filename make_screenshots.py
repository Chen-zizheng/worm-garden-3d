"""
生成提交用截图（含 Part B 扩展的 before/after 对比图）。

用法：
    python make_screenshots.py            # 1120x700 高画质截图 + 对比图
    python make_screenshots.py --quality 1

输出：
    screenshots/*.png            带 HUD 的游戏截图（窗口 1280x800，内部渲染分辨率见 HUD）
    screenshots/comparisons/*.png 最近邻/双线性、走样、深度雾的并排对比
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame
from PIL import Image, ImageDraw, ImageFont

import config as C
from camera import Camera
from raster import Renderer
from render_scene import draw_world
from world import World

WINDOW_W, WINDOW_H = 1280, 800
SHOT_DIR = os.path.join(HERE, "screenshots")
CMP_DIR = os.path.join(SHOT_DIR, "comparisons")
FONT_PATH = "C:/Windows/Fonts/consola.ttf"
FONT_CANDIDATES = "consolas,couriernew,segoeui"
PRESET_NAMES = {1: "CHASE", 2: "TOP-DOWN", 3: "OVERVIEW"}


def load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


_HINT_FONTS = {}


def render_hint(text, max_width, color=(225, 235, 245)):
    """一行放不下就折成两行（和 main.py 的渲染逻辑保持一致）。"""
    for size in (16, 15, 14, 13, 12):
        f = _HINT_FONTS.get(size) or pygame.font.SysFont(FONT_CANDIDATES, size)
        _HINT_FONTS[size] = f
        surf = f.render(text, True, color)
        if surf.get_width() <= max_width:
            return surf
    groups = text.split("   ")
    mid = max(1, len(groups) // 2)
    lines = ["   ".join(groups[:mid]), "   ".join(groups[mid:])]
    f = _HINT_FONTS.get(14) or pygame.font.SysFont(FONT_CANDIDATES, 14)
    _HINT_FONTS[14] = f
    surfs = [f.render(t, True, color) for t in lines]
    width = max(s.get_width() for s in surfs)
    height = sum(s.get_height() for s in surfs)
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    y = 0
    for s in surfs:
        out.blit(s, (0, y))
        y += s.get_height()
    return out


class Stage:
    """无窗口（SDL dummy）渲染舞台：可以脚本化推进世界状态并截图。"""

    def __init__(self, seed=7, quality=2):
        pygame.display.init()
        pygame.font.init()
        self.quality = quality
        self.rw, self.rh = C.QUALITY_PRESETS[quality]
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Worm Garden Adventure 3D")
        self.font = pygame.font.SysFont(FONT_CANDIDATES, 20, bold=True)
        self.font_small = pygame.font.SysFont(FONT_CANDIDATES, 16)
        self.world = World(seed=seed)
        self.camera = Camera()
        self.renderer = Renderer(self.rw, self.rh)
        self.bilinear = C.TEXTURE_BILINEAR
        self.checker = False
        self.bloom = C.BLOOM_ENABLED
        self.time = 0.0
        self.frame_ms = 0.0

    # -------------------------------------------------- 推进 / 渲染
    def advance(self, seconds, move=(0.0, 0.0), jump=False):
        frames = max(1, int(round(seconds * C.FPS)))
        mv = np.array(move, dtype=float)
        for i in range(frames):
            self.world.update(1.0 / C.FPS, mv, bool(jump and i == 0))
            self.camera.update(self.world, 1.0 / C.FPS)
            self.time += 1.0 / C.FPS

    def render_raw(self):
        t0 = time.perf_counter()
        draw_world(self.renderer, self.world, self.camera, self.time,
                   bilinear=self.bilinear, checker=self.checker, bloom=self.bloom)
        img = self.renderer.to_image()
        self.frame_ms = (time.perf_counter() - t0) * 1000.0
        return img

    def to_surface(self, img):
        surface = pygame.surfarray.make_surface(img.swapaxes(0, 1))
        if surface.get_size() != (WINDOW_W, WINDOW_H):
            surface = pygame.transform.smoothscale(surface, (WINDOW_W, WINDOW_H))
        return surface

    def draw_hud(self, surface, caption=None):
        w = self.world
        panel = pygame.Surface((WINDOW_W, 34), pygame.SRCALPHA)
        panel.fill((4, 8, 20, 150))
        surface.blit(panel, (0, 0))
        left = (f"LEVEL {w.level}   SCORE {w.score}   "
                f"APPLES {w.collected}/{C.TOTAL_MEDALS}   TIME {w.time:5.1f}s")
        filt = "BILINEAR" if self.bilinear else "NEAREST"
        fog = "FOG" if getattr(C, "FOG_ENABLED", True) else "-"
        glow = "BLOOM" if self.bloom else "-"
        right = (f"{PRESET_NAMES[self.camera.preset]}  "
                 f"{self.camera.mode.upper()}  {filt}  {fog}  {glow}  "
                 f"{self.frame_ms:5.1f} ms  {self.rw}x{self.rh}")
        surface.blit(self.font.render(left, True, (240, 246, 255)), (12, 6))
        txt = self.font.render(right, True, (140, 235, 215))
        surface.blit(txt, (WINDOW_W - txt.get_width() - 12, 6))

        hint = caption or C.HINT_TEXT
        h = render_hint(hint, WINDOW_W - 40)
        bg = pygame.Surface((h.get_width() + 16, h.get_height() + 8), pygame.SRCALPHA)
        bg.fill((4, 8, 20, 140))
        bx = WINDOW_W // 2 - bg.get_width() // 2
        by = WINDOW_H - bg.get_height() - 8
        surface.blit(bg, (bx, by))
        surface.blit(h, (bx + 8, by + 4))

    def shot(self, name, caption=None, use_hud=True):
        raw = self.render_raw()
        surface = self.to_surface(raw)
        if use_hud:
            self.draw_hud(surface, caption)
        path = os.path.join(SHOT_DIR, name + ".png")
        pygame.image.save(surface, path)
        print(f"  {name}.png  ({self.rw}x{self.rh} -> {WINDOW_W}x{WINDOW_H}, "
              f"{self.frame_ms:.0f} ms)")
        return raw


# ------------------------------------------------------ 对比图工具
def _crop_zoom(img, box, zoom):
    crop = Image.fromarray(img).crop(box)
    return crop.resize((crop.width * zoom, crop.height * zoom), Image.NEAREST)


def _label(width, text, height=46, size=22):
    bar = Image.new("RGB", (width, height), (14, 20, 28))
    d = ImageDraw.Draw(bar)
    d.text((14, 10), text, font=load_font(size), fill=(232, 240, 250))
    return bar


def side_by_side(pairs, out_name, title, subtitle=""):
    """pairs: [(label, PIL.Image), ...] 横向或纵向拼接并加标题。"""
    imgs = [p[1] for p in pairs]
    gap = 12
    width = sum(i.width for i in imgs) + gap * (len(imgs) - 1)
    height = max(i.height for i in imgs)
    canvas = Image.new("RGB", (width, height + 46 + 34), (10, 14, 20))
    x = 0
    for lb, im in pairs:
        canvas.paste(im, (x, 46))
        bar = _label(im.width, lb)
        canvas.paste(bar, (x, 46 + im.height))
        x += im.width + gap
    canvas.paste(_label(width, title, 46, 24), (0, 0))
    if subtitle:
        d = ImageDraw.Draw(canvas)
        d.text((width - 12 - 9 * len(subtitle), 16), subtitle,
               font=load_font(16), fill=(150, 170, 190))
    path = os.path.join(CMP_DIR, out_name + ".png")
    canvas.save(path)
    print(f"  comparisons/{out_name}.png  ({canvas.width}x{canvas.height})")


def main(argv):
    quality = 2
    if "--quality" in argv:
        quality = max(0, min(2, int(argv[argv.index("--quality") + 1])))
    os.makedirs(SHOT_DIR, exist_ok=True)
    os.makedirs(CMP_DIR, exist_ok=True)
    st = Stage(seed=7, quality=quality)
    print(f"rendering at {st.rw}x{st.rh} (window {WINDOW_W}x{WINDOW_H})")

    # ---------- 1. 基本巡览（Part A 的 6 张必备截图）----------
    print("[1/5] tour")
    # 提交用的截图统一开双线性：128 像素贴图在 1120x700 下最近邻会明显闪，
    # 双线性更能代表最终画质（游戏里默认最近邻是性能权衡，B 键可切）。
    st.bilinear = True
    # 起始格向东只有 1.15 个单位就撞墙，走出这段的同时粒子才会喷出来，
    # 所以 01 拍在起步后 0.16 秒（还在走），02 拍在紧接着起跳的空中，
    # 这时尾巴上的粒子还在寿命内，能同时看到腾空的虫子和火花。
    st.advance(0.16, move=(1.0, 0.0))
    st.shot("01_chase_perspective")
    st.advance(0.10, move=(1.0, 0.0), jump=True)
    st.shot("02_jump_particles")
    st.camera.toggle_projection()
    st.advance(0.35, move=(1.0, 0.0))
    st.shot("03_chase_orthographic")
    st.camera.set_preset(2)
    st.advance(0.70, move=(0.0, 1.0))
    st.shot("04_topdown_orthographic")
    st.camera.toggle_projection()
    st.advance(0.20)
    st.shot("05_topdown_perspective")
    st.camera.set_preset(3)
    st.advance(0.60)
    st.shot("06_overview_perspective")
    st.camera.toggle_projection()
    st.advance(0.10)
    st.shot("07_overview_orthographic")

    # ---------- 2. 双线性过滤（Part B 扩展 A）----------
    print("[2/5] bilinear filtering")
    st.camera.set_preset(1)
    if st.camera.mode == "orthographic":
        st.camera.toggle_projection()
    st.camera.pitch = 0.30
    st.camera.yaw = 0.55
    st.advance(0.60, move=(1.0, 0.0))
    st.bilinear = False
    raw_near = st.shot("08_filter_nearest",
                       caption="BILINEAR OFF (nearest neighbour)  --  internal "
                               f"{st.rw}x{st.rh}")
    st.bilinear = True
    raw_bilin = st.shot("09_filter_bilinear",
                        caption="BILINEAR ON  --  internal "
                                f"{st.rw}x{st.rh}")
    box = (int(st.rw * 0.30), int(st.rh * 0.42),
           int(st.rw * 0.62), int(st.rh * 0.74))
    zoom = 3
    side_by_side([("NEAREST (blocky blocks)", _crop_zoom(raw_near, box, zoom)),
                  ("BILINEAR (smooth transitions)", _crop_zoom(raw_bilin, box, zoom))],
                 "filter_nearest_vs_bilinear",
                 "Part B extension A: bilinear texture filtering  (3x zoom of the same pixels)",
                 "internal resolution " + f"{st.rw}x{st.rh}")

    # ---------- 3. 棋盘走样（纹理走样 / 过滤的直观证据）----------
    print("[3/5] checker aliasing")
    st.checker = True
    st.camera.pitch = 0.22
    st.camera.yaw = 0.0
    st.advance(0.40, move=(1.0, 0.0))
    st.bilinear = False
    raw_ck_n = st.shot("10_checker_nearest",
                       caption="checker test texture, NEAREST  --  internal "
                               f"{st.rw}x{st.rh}")
    st.bilinear = True
    raw_ck_b = st.shot("11_checker_bilinear",
                       caption="checker test texture, BILINEAR  --  internal "
                               f"{st.rw}x{st.rh}")
    cbox = (int(st.rw * 0.28), int(st.rh * 0.30),
            int(st.rw * 0.72), int(st.rh * 0.62))
    side_by_side([("NEAREST: harsh moire", _crop_zoom(raw_ck_n, cbox, 2)),
                  ("BILINEAR: softened", _crop_zoom(raw_ck_b, cbox, 2))],
                 "checker_aliasing",
                 "Texture aliasing test with a high frequency checkerboard (2x zoom)",
                 "internal resolution " + f"{st.rw}x{st.rh}")
    st.checker = False

    # ---------- 4. 深度雾（Part B 扩展 B）----------
    print("[4/5] depth fog")
    st.camera.set_preset(3)
    if st.camera.mode == "orthographic":
        st.camera.toggle_projection()
    st.bilinear = False
    st.advance(0.30)
    fog_start0, fog_end0 = C.FOG_START, C.FOG_END
    C.FOG_ENABLED = False
    raw_fog_off = st.shot("12_fog_off",
                          caption="DEPTH FOG OFF  --  internal "
                                  f"{st.rw}x{st.rh}")
    # 为了在静态对比图里看清效果，对比图使用更近的雾区间（6..22），
    # 游戏内默认是 7..30（见 config.py），截图后会自动还原。
    C.FOG_START, C.FOG_END = 6.0, 22.0
    C.FOG_ENABLED = True
    raw_fog_on = st.shot("13_fog_on",
                         caption="DEPTH FOG ON, demo range 6..22 (in-game default 7..30)  --  internal "
                                 f"{st.rw}x{st.rh}")
    C.FOG_START, C.FOG_END = fog_start0, fog_end0
    scaled = lambda img: Image.fromarray(img).resize(
        (st.rw, st.rh), Image.NEAREST)
    side_by_side([("FOG OFF", scaled(raw_fog_off)), ("FOG ON", scaled(raw_fog_on))],
                 "depth_fog_before_after",
                 "Part B extension B: depth fog from the z-buffer (demo range 6..22)",
                 "internal resolution " + f"{st.rw}x{st.rh}")

    # ---------- 5. bloom 泛光（Part B 扩展 C：图像处理类）----------
    print("[5/5] bloom")
    st.camera.set_preset(1)
    if st.camera.mode == "orthographic":
        st.camera.toggle_projection()
    st.camera.pitch = 0.26
    st.camera.yaw = 0.0
    st.checker = False
    st.bilinear = True
    st.advance(0.90, move=(1.0, 0.0))
    st.bloom = False
    raw_bloom_off = st.shot("14_bloom_off",
                            caption="BLOOM OFF, night garden theme  --  internal "
                                    f"{st.rw}x{st.rh}")
    st.bloom = True
    raw_bloom_on = st.shot("15_bloom_on",
                           caption="BLOOM ON: bright-pass + blur, added back after tone mapping  --  internal "
                                   f"{st.rw}x{st.rh}")
    side_by_side([("BLOOM OFF", scaled(raw_bloom_off)),
                  ("BLOOM ON", scaled(raw_bloom_on))],
                 "bloom_before_after",
                 "Part B extension C: screen-space bloom (bright pass + box blur)",
                 "internal resolution " + f"{st.rw}x{st.rh}")
    bbox = (int(st.rw * 0.26), int(st.rh * 0.34),
            int(st.rw * 0.62), int(st.rh * 0.68))
    side_by_side([("BLOOM OFF (2x zoom)", _crop_zoom(raw_bloom_off, bbox, 2)),
                  ("BLOOM ON (2x zoom)", _crop_zoom(raw_bloom_on, bbox, 2))],
                 "bloom_zoom",
                 "Bloom detail: the fluorescent worm, apples and moon glow bleed into neighbours",
                 "internal resolution " + f"{st.rw}x{st.rh}")

    pygame.quit()
    print("done")


if __name__ == "__main__":
    main(sys.argv[1:])
