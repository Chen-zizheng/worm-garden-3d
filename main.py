"""
Worm Garden Adventure 3D —— 主程序

窗口用 pygame 显示，画面由纯 NumPy 写的软件光栅化器渲染：
    世界空间 -> 相机空间 -> 近平面裁剪 -> 透视/正交投影 -> 背面剔除
    -> 逐像素重心坐标填充 + Z-Buffer 深度缓冲

按键：
    W A S D / 方向键   移动
    空格               跳跃
    1 / 2 / 3          相机预设（跟随 / 俯视 / 全景）
    P                  切换透视 / 正交投影
    R                  重开本局
    B                  切换纹理过滤（最近邻 / 双线性）
    T                  切换实验用棋盘纹理（观察走样）
    F                  开关深度雾（Part B 扩展 B）
    G                  开关 bloom 泛光（Part B 扩展 C）
    F1 / F2 / F3       内部渲染分辨率（480x300 / 800x500 / 1120x700）
    F12                截图到 screenshots/
    鼠标拖动           环绕相机
    ESC                退出

用法：
    python main.py               正常游玩
    python main.py --bench       只渲染不操作，测真实帧率
    python main.py --quality N   启动时的内部渲染分辨率档（0/1/2，默认 0 = 480x300）
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)

import numpy as np
import pygame

import config as C
from camera import Camera
from raster import Renderer
from render_scene import draw_world
from world import World

WINDOW_W, WINDOW_H = 1280, 800
TITLE = "Worm Garden Adventure 3D"
FONT_CANDIDATES = "consolas,couriernew,segoeui"
SHOT_DIR = os.path.join(HERE, "screenshots")

# 移动方向不再用世界坐标常量：按键是"屏幕方向"，由 camera.ground_basis()
# 每帧换算成世界方向。鼠标把相机转到任意方位，↑ 都还是往屏幕里走。
PRESET_NAMES = {1: "CHASE", 2: "TOP-DOWN", 3: "OVERVIEW"}
# 被送回起点时 HUD 上弹出的一行说明（和原版 2D 规则一致）
EVENT_TEXT = {
    "water": "SPLASH!  a water hole sent you back to the start  (jump over it with SPACE)",
    "bird": "OUCH!  a bird sent you back to the start",
    "finish": "NOT YET!  collect all 4 apples before the finish flag",
}

# 固定时间步长：不管渲染多慢，世界逻辑都按 60 Hz 推进，
# 避免"帧率一低整个游戏就变慢、按键像没反应"。
SIM_DT = 1.0 / C.FPS
MAX_SIM_STEPS = 8


def render_hint(font_cache, text, max_width, color=(225, 235, 245)):
    """把按键提示排成一行；一行放不下就折成两行（窗口宽度固定 1280，提示较长）。"""
    for size in (16, 15, 14, 13, 12):
        f = font_cache.get(size) or pygame.font.SysFont(FONT_CANDIDATES, size)
        font_cache[size] = f
        surf = f.render(text, True, color)
        if surf.get_width() <= max_width:
            return surf
    groups = text.split("   ")
    mid = max(1, len(groups) // 2)
    lines = ["   ".join(groups[:mid]), "   ".join(groups[mid:])]
    f = font_cache.get(14) or pygame.font.SysFont(FONT_CANDIDATES, 14)
    font_cache[14] = f
    surfs = [f.render(t, True, color) for t in lines]
    width = max(s.get_width() for s in surfs)
    height = sum(s.get_height() for s in surfs)
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    y = 0
    for s in surfs:
        out.blit(s, (0, y))
        y += s.get_height()
    return out


class App:
    def __init__(self, seed=7, quality=0, size=(WINDOW_W, WINDOW_H)):
        self.quality = quality
        self.rw, self.rh = C.QUALITY_PRESETS[quality]
        self.window = size
        self.world = World(seed=seed)
        self.camera = Camera()
        self.renderer = Renderer(self.rw, self.rh)

        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode(size)
        pygame.display.set_caption(TITLE)
        # 关键：关掉 SDL 的 IME 文本输入。否则中文输入法会把字母键吞掉，
        # 只剩数字键和空格能进到游戏里（P/B/T/F/R/WASD 全部失灵）。
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass
        self.font = pygame.font.SysFont(FONT_CANDIDATES, 20, bold=True)
        self.font_small = pygame.font.SysFont(FONT_CANDIDATES, 16)
        self.event_font = pygame.font.SysFont(FONT_CANDIDATES, 20, bold=True)
        self.clock = pygame.time.Clock()
        self.hint_fonts = {}

        os.makedirs(SHOT_DIR, exist_ok=True)
        self.time = 0.0
        self.frames = 0
        self.fps = 0.0
        self.frame_ms = 0.0
        self.jump_pressed = False
        self.dragging = False
        self.bilinear = C.TEXTURE_BILINEAR
        self.checker = False
        self.fog = C.FOG_ENABLED
        self.bloom = C.BLOOM_ENABLED
        self.last_key = ""

    # ------------------------------------------------------------------
    # 输入
    # ------------------------------------------------------------------
    def read_keys(self):
        """返回 (forward, right)：屏幕方向的输入分量，不是世界方向。

        ↑/W = 往屏幕里走，↓/S = 往屏幕外走，←/A = 屏幕左，→/D = 屏幕右。
        真正的世界方向由 camera.ground_basis() 换算（见 step()），
        这样无论相机被鼠标转到什么方位，按键和画面上的方向都是一致的。
        """
        keys = pygame.key.get_pressed()
        forward = 0.0
        right = 0.0
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            forward += 1.0
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            forward -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            right += 1.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            right -= 1.0
        return forward, right

    def handle_event(self, event):
        log_path = os.environ.get("WORM_KEYLOG")
        if log_path and event.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.MOUSEBUTTONDOWN):
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    if event.type == pygame.KEYDOWN:
                        f.write(f"KEYDOWN {pygame.key.name(event.key)} key={event.key} "
                                f"scancode={event.scancode} mod={event.mod} "
                                f"unicode={event.unicode!r}\n")
                    elif event.type == pygame.KEYUP:
                        f.write(f"KEYUP   {pygame.key.name(event.key)} key={event.key}\n")
                    else:
                        f.write(f"MOUSEDOWN button={event.button}\n")
            except Exception:
                pass
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            try:
                self.last_key = pygame.key.name(event.key).upper()
            except Exception:
                self.last_key = str(event.key)
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_SPACE:
                self.jump_pressed = True
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.camera.set_preset(event.key - pygame.K_0)
            elif event.key in (pygame.K_p, pygame.K_TAB):
                self.camera.toggle_projection()
            elif event.key in (pygame.K_r, pygame.K_F5):
                self.world.restart()
            elif event.key in (pygame.K_b, pygame.K_F6):
                self.bilinear = not self.bilinear
            elif event.key in (pygame.K_t, pygame.K_F7):
                self.checker = not self.checker
            elif event.key in (pygame.K_f, pygame.K_F8):
                C.FOG_ENABLED = not C.FOG_ENABLED
                self.fog = C.FOG_ENABLED
            elif event.key in (pygame.K_g, pygame.K_F9):
                self.bloom = not self.bloom
                C.BLOOM_ENABLED = self.bloom
            elif event.key == pygame.K_F12:
                self.save_screenshot("manual")
            elif event.key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
                self.set_quality(event.key - pygame.K_F1)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.dragging = True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.camera.orbit(*event.rel)
        return True

    def set_quality(self, quality):
        if quality == self.quality:
            return
        self.quality = quality
        self.rw, self.rh = C.QUALITY_PRESETS[quality]
        self.renderer = Renderer(self.rw, self.rh)

    # ------------------------------------------------------------------
    # 一帧
    # ------------------------------------------------------------------
    def step(self, dt, forward, right):
        if forward or right:
            fwd_dir, right_dir = self.camera.ground_basis()
            move = fwd_dir * forward + right_dir * right
            n = float(np.linalg.norm(move))
            move = move / n if n > 1e-9 else np.zeros(2)
        else:
            move = np.zeros(2)
        self.world.update(dt, move, self.jump_pressed)
        self.jump_pressed = False
        # 只有"基本朝前走"的时候才让相机自动转到虫子背后；
        # 左右平移时相机不转，否则左右键的相对方向会不停变化。
        align = forward > 0.5 and abs(right) < 0.3
        self.camera.update(self.world, dt, align=align)
        self.time += dt

    def render(self):
        t0 = time.perf_counter()
        draw_world(self.renderer, self.world, self.camera, self.time,
                   bilinear=self.bilinear, checker=self.checker, bloom=self.bloom)
        img = self.renderer.to_image()
        surface = pygame.surfarray.make_surface(img.swapaxes(0, 1))
        if surface.get_size() != self.window:
            surface = pygame.transform.smoothscale(surface, self.window)
        self.frame_ms = (time.perf_counter() - t0) * 1000.0
        # 无窗口脚本模式（demo/bench）不会经过主循环的平滑，这里直接给瞬时帧率
        self.fps = 1000.0 / max(self.frame_ms, 1e-6)
        return surface

    def draw_hud(self, surface):
        w = self.world
        panel = pygame.Surface((self.window[0], 34), pygame.SRCALPHA)
        panel.fill((4, 8, 20, 150))
        surface.blit(panel, (0, 0))

        left = (f"LEVEL {w.level}   SCORE {w.score}   "
                f"APPLES {w.collected}/{C.TOTAL_MEDALS}   TIME {w.time:5.1f}s")
        filt = "BILINEAR" if self.bilinear else "NEAREST"
        fog = "FOG" if self.fog else "-"
        glow = "BLOOM" if self.bloom else "-"
        right = (f"{PRESET_NAMES[self.camera.preset]}  "
                 f"{self.camera.mode.upper()}  {filt}  {fog}  {glow}  "
                 f"{self.fps:4.1f} FPS  {self.rw}x{self.rh}")
        surface.blit(self.font.render(left, True, (240, 246, 255)), (12, 6))
        txt = self.font.render(right, True, (140, 235, 215))
        surface.blit(txt, (self.window[0] - txt.get_width() - 12, 6))

        h = render_hint(self.hint_fonts, C.HINT_TEXT, self.window[0] - 40)
        bg = pygame.Surface((h.get_width() + 16, h.get_height() + 8), pygame.SRCALPHA)
        bg.fill((4, 8, 20, 140))
        surface.blit(bg, (self.window[0] // 2 - bg.get_width() // 2,
                          self.window[1] - bg.get_height() - 8))
        surface.blit(h, (self.window[0] // 2 - h.get_width() // 2,
                         self.window[1] - bg.get_height() + 4 - 8))
        # 被送回起点时说清楚"为什么"：原版 2D 游戏里落水/撞鸟就是把球送回起点，
        # 起点旗不是存档点，所以这里必须给个显式提示，否则玩家以为按键失灵。
        msg = EVENT_TEXT.get(w.event or "", "")
        if msg and w.event_timer > 0.0:
            alpha = 255 if w.event_timer > 0.6 else int(255.0 * w.event_timer / 0.6)
            t = self.event_font.render(msg, True, (255, 238, 210))
            band = pygame.Surface((t.get_width() + 36, t.get_height() + 16), pygame.SRCALPHA)
            band.fill((150, 52, 32, int(200 * alpha / 255)))
            band.blit(t, (18, 8))
            band.set_alpha(alpha)
            surface.blit(band, (self.window[0] // 2 - band.get_width() // 2, 42))
        if self.last_key:
            # 现场排查用：看一眼就知道按键到底有没有进到窗口里
            k = self.font_small.render(f"last key: {self.last_key}", True, (255, 232, 150))
            kb = pygame.Surface((k.get_width() + 12, k.get_height() + 6), pygame.SRCALPHA)
            kb.fill((8, 14, 22, 140))
            kb.blit(k, (6, 3))
            surface.blit(kb, (18, self.window[1] - bg.get_height() - kb.get_height() - 14))

    def save_screenshot(self, tag):
        surface = self.render()
        self.draw_hud(surface)
        path = os.path.join(SHOT_DIR, f"{tag}.png")
        pygame.image.save(surface, path)
        print("screenshot:", path)
        return path

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(self):
        running = True
        acc = 0.0
        while running:
            real_dt = min(self.clock.tick(C.FPS) / 1000.0, 0.20)
            for event in pygame.event.get():
                running = self.handle_event(event)
                if not running:
                    break
            keys = pygame.key.get_pressed()
            # Q / E 手动转视角（鼠标拖动也可以）；这也是"屏幕方向"按键的参照系
            if keys[pygame.K_q]:
                self.camera.yaw -= real_dt * 1.8
            if keys[pygame.K_e]:
                self.camera.yaw += real_dt * 1.8
            forward, right = self.read_keys()
            # 固定时间步长：渲染慢的时候多跑几个逻辑步，游戏速度保持真实，
            # 掉帧只是画面少，不是"世界变慢、按键没反应"。
            acc += real_dt
            steps = 0
            while acc >= SIM_DT and steps < MAX_SIM_STEPS:
                self.step(SIM_DT, forward, right)
                acc -= SIM_DT
                steps += 1
            if steps >= MAX_SIM_STEPS:
                acc = 0.0
            surface = self.render()
            self.draw_hud(surface)
            # render() 返回的是新的缩放后 Surface，必须显式贴到显示表面上，
            # 否则 display.flip() 翻的是从未被画过的黑屏。
            self.screen.blit(surface, (0, 0))
            pygame.display.flip()
            self.frames += 1
            self.fps = self.fps * 0.9 + (1.0 / max(real_dt, 1e-6)) * 0.1
        pygame.quit()

def bench(app, seconds=5.0):
    """只跑主循环（含渲染+HUD），统计真实帧率。"""
    frames = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        app.clock.tick(C.FPS)
        for event in pygame.event.get():
            app.handle_event(event)
        app.step(1.0 / C.FPS, 0.0, 1.0)
        surface = app.render()
        app.draw_hud(surface)
        pygame.display.flip()
        frames += 1
    elapsed = time.perf_counter() - t0
    print(f"bench {app.rw}x{app.rh}: {frames} frames in {elapsed:.2f}s "
          f"-> {frames / elapsed:.1f} fps ({elapsed / frames * 1000:.1f} ms/frame)")
    pygame.quit()


def main(argv):
    quality = 0
    seed = 7
    if "--quality" in argv:
        quality = max(0, min(2, int(argv[argv.index("--quality") + 1])))
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    app = App(seed=seed, quality=quality)
    if "--bench" in argv:
        bench(app)
    else:
        app.run()


if __name__ == "__main__":
    main(sys.argv[1:])
