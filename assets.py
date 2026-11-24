"""
assets.py —— 用 Pillow 生成 / 加载纹理（手册 Section 10）。

纹理是本方案中唯一的“图像处理”素材来源：
    * textureless 的纯色多边形 -> 带 (u,v) 的贴图三角形
    * 纹理图由 Pillow 程序化生成，保存为 PNG（提交物的一部分），运行时再读回

坐标约定：图像左上角为 (0,0)，u 向右、v 向下（与手册一致）。
采样器在 raster.py 中实现（最近邻 / 双线性）。
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(HERE, "textures")

# 贴图分辨率（必须是 2 的幂：采样时用位与实现 wrap，见 raster.py）
TEX_SIZE = 128

# 材质名 -> 文件名（场景里 mesh["tex"] 用材质名引用）
MATERIALS = {
    "grass": "grass.png",
    "stone": "stone.png",
    "checker": "checker.png",
}


# ----------------------------------------------------------------------
# 程序化纹理生成
# ----------------------------------------------------------------------
def make_grass(size=TEX_SIZE, seed=12):
    """草地：绿色底 + 随机草叶，参考手册 10.1 的示例并按视觉需要加强。"""
    rng = np.random.default_rng(seed)
    base = np.empty((size, size, 3), np.uint8)
    base[..., 0] = 40
    base[..., 1] = 112
    base[..., 2] = 52
    # 低频明暗斑块，避免整块地面死板
    coarse = rng.random((size // 8, size // 8)) * 18.0 - 9.0
    coarse = np.kron(coarse, np.ones((8, 8)))[:size, :size]
    base = np.clip(base.astype(np.float32) + coarse[..., None], 0, 255).astype(np.uint8)

    img = Image.fromarray(base, "RGB")
    draw = ImageDraw.Draw(img)
    tones = [(30, 90, 42), (54, 130, 63), (72, 148, 78), (94, 160, 86), (24, 74, 36)]
    for _ in range(1100):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        tone = tones[int(rng.integers(0, len(tones)))]
        length = int(rng.integers(2, 5))
        draw.line((x, y, x + int(rng.integers(-1, 2)), y - length), fill=tone, width=1)
    # 很轻微的模糊，让 1 像素的草叶在放大后不那么“噪点化”
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return img


def make_stone(size=TEX_SIZE, seed=7):
    """石墙：砖块 + 灰缝 + 颗粒噪声（砖缝用于验证透视插值是否拉斜）。"""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (size, size), (116, 116, 120))
    draw = ImageDraw.Draw(img)

    brick_h = 32
    brick_w = 64
    mortar = (74, 72, 76)
    for row, y in enumerate(range(0, size, brick_h)):
        offset = 0 if row % 2 == 0 else brick_w // 2
        for x in range(-brick_w, size + brick_w, brick_w):
            x0 = x + offset
            shade = int(rng.integers(-16, 17))
            tone = (int(np.clip(122 + shade, 40, 200)),
                    int(np.clip(118 + shade, 40, 200)),
                    int(np.clip(112 + shade, 40, 200)))
            draw.rectangle((x0 + 2, y + 2, x0 + brick_w - 3, y + brick_h - 3), fill=tone)
            # 砖块上缘高光、下缘阴影，让平贴图在光照外还有一点体积感
            draw.line((x0 + 2, y + 2, x0 + brick_w - 3, y + 2), fill=tuple(min(255, c + 22) for c in tone))
            draw.line((x0 + 2, y + brick_h - 3, x0 + brick_w - 3, y + brick_h - 3),
                      fill=tuple(max(0, c - 26) for c in tone))
        draw.line((0, y, size, y), fill=mortar)
    # 颗粒噪声
    arr = np.asarray(img, np.int16)
    noise = rng.normal(0.0, 7.0, (size, size, 1)).repeat(3, axis=2)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def make_checker(size=TEX_SIZE, squares=8):
    """黑白棋盘：用于对比最近邻与双线性采样的走样（手册 Section 10 的对照实验）。"""
    img = Image.new("RGB", (size, size), (232, 232, 226))
    draw = ImageDraw.Draw(img)
    step = max(1, size // squares)
    for j in range(squares):
        for i in range(squares):
            if (i + j) % 2 == 0:
                continue
            draw.rectangle((i * step, j * step, (i + 1) * step - 1, (j + 1) * step - 1),
                           fill=(38, 40, 46))
    return img


_BUILDERS = {"grass": make_grass, "stone": make_stone, "checker": make_checker}


# ----------------------------------------------------------------------
def tex_path(name):
    return os.path.join(TEX_DIR, MATERIALS[name])


def ensure_textures(force=False):
    """把缺失的纹理生成到 textures/ 下，返回实际生成的文件列表。"""
    os.makedirs(TEX_DIR, exist_ok=True)
    made = []
    for name, builder in _BUILDERS.items():
        path = tex_path(name)
        if force or not os.path.exists(path):
            builder().save(path)
            made.append(path)
    return made


def load_texture(name):
    """读回一张纹理，返回 (H, W, 3) 的 float32 数组，取值 0~1。"""
    path = tex_path(name)
    if not os.path.exists(path):
        ensure_textures()
    arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    return np.ascontiguousarray(arr)


def load_textures(names=None):
    names = list(MATERIALS) if names is None else names
    return {n: load_texture(n) for n in names}
