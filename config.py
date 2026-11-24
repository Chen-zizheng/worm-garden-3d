"""
全局配置：所有长度都以“世界单位”计。
换算规则（来自手册）：原 2D 游戏中 50 像素 = 1 世界单位。
"""

# ---------------- 迷宫 ----------------
COLS = 23
ROWS = 15
CELL = 1.0

MAZE_W = COLS * CELL
MAZE_H = ROWS * CELL

# ---------------- 墙 ----------------
WALL_H = 0.75          # 手册：墙高 0.75 世界单位
WALL_T = 8 / 50.0      # 手册：墙厚 8 像素 -> 0.16 世界单位

# ---------------- 玩家（虫） ----------------
BALL_RADIUS = 11 / 50.0
BALL_SPEED = 230 / 50.0
JUMP_V0 = 3.2          # 手册：起跳初速度 3.2
GRAVITY = 10.0         # 手册：重力加速度 10

# ---------------- 水坑 ----------------
WATER_HOLE_COUNT = 9
WATER_HOLE_RADIUS = 13 / 50.0

# ---------------- 鸟 ----------------
ENEMY_RADIUS = 10 / 50.0
ENEMY_SPEED = 75 / 50.0

# ---------------- 苹果 ----------------
MEDAL_RADIUS = 9 / 50.0
MEDAL_HOVER = 0.30
SILVER_VALUE = 50
GOLD_VALUE = 100
TOTAL_MEDALS = 4

# ---------------- 关卡 ----------------
START_CELL = (0, ROWS // 2)
FINISH_CELL = (COLS - 1, ROWS // 2)
FINISH_RADIUS = 17 / 50.0

# ---------------- 相机 ----------------
FOV_Y = 60.0
NEAR = 0.1             # 手册：近平面 0.1
FAR = 120.0
CAMERA_PRESETS = {
    1: "third_person",
    2: "top_down",
    3: "overview",
}

# ---------------- 渲染 ----------------
RENDER_W = 800
RENDER_H = 500
AMBIENT = 0.34
LIGHT_DIR = (-0.45, 0.82, -0.35)
FILL_DIR = (0.55, 0.35, 0.75)     # 补光方向：照亮主光打不到的面
FILL_WEIGHT = 0.45
GROUND_MARGIN = 26.0              # 地面向迷宫外延伸的世界单位
FPS = 60

# 画质档位：(宽, 高)，内部渲染分辨率，窗口再放大
QUALITY_PRESETS = ((480, 300), (800, 500), (1120, 700))

# 底部操作提示（main.py 与 make_screenshots.py 共用，避免两处文案不一致）
HINT_TEXT = ("WASD/ARROWS move   Q/E rotate view   SPACE jump   1/2/3 camera   "
             "TAB projection   F6 filter   F7 checker   F8 fog   F9 bloom   "
             "F5 restart   F12 screenshot")

# ---------------- 美术方向：暮色花园（Night Garden） ----------------
# 天空 / 月亮 / 星星 / 调色 / bloom 全部集中在这一段：
# 想换一个美术方向，只改这里的数值，其余代码不用动。
SKY_TOP = (0.02, 0.04, 0.12)        # 天顶：深蓝夜色
SKY_HORIZON = (0.10, 0.16, 0.32)    # 地平线
# 月亮：(屏幕归一化 x, y, 高斯 sigma, 强度, 颜色)
MOON = (0.20, 0.16, 0.030, 0.75, (0.85, 0.90, 1.00))
STARS = 1600                        # 星星数量（只画在屏幕上半部）
STAR_SEED = 5
VIGNETTE = 0.50                     # 屏幕四周压暗强度，0 = 关
GRADE = (1.02, 1.06, 1.14)          # 最后的通道增益（轻微冷调）

# 屏幕空间 bloom（Part B 扩展 3：图像处理类）
# 亮度超过阈值的像素降采样 -> 盒式模糊 -> 叠回原图，让苹果/荧光虫/月亮发光。
BLOOM_ENABLED = True
BLOOM_THRESHOLD = 0.50
BLOOM_RADIUS = 10                   # 降采样空间里的模糊半径（像素）
BLOOM_STRENGTH = 0.70
BLOOM_SCALE = 4                     # 降采样倍数（1/4 分辨率做模糊）

# ---------------- 纹理（Part A 贴图 + Part B 双线性过滤） ----------------
# 纹理尺寸必须是 2 的幂（光栅化里用位与做重复采样）
TEX_TILE_GROUND = 2.0     # 一个草地纹理重复对应多少世界单位
TEX_TILE_WALL = 0.9       # 一个石墙纹理重复对应多少世界单位
TEXTURE_BILINEAR = False  # 默认最近邻过滤；游戏里按 B 键切换
COL_GROUND_TINT = (0.36, 0.72, 0.82)       # 纹理颜色 = tex * tint（夜色下草地偏青）
COL_WALL_TINT = (0.62, 0.82, 1.25)
COL_WALL_TOP_TINT = (0.80, 1.02, 1.50)

# ---------------- 深度雾（Part B 扩展 2：全屏后处理） ----------------
FOG_ENABLED = True
FOG_START = 7.0
FOG_END = 34.0
FOG_COLOR = (0.12, 0.22, 0.38)

# ---------------- 粒子 ----------------
MAX_PARTICLES = 250
SPARK_INTERVAL = 0.02

# ---------------- 颜色（0~1） ----------------
COL_GROUND = (0.10, 0.24, 0.26)
COL_GROUND_DARK = (0.08, 0.20, 0.22)
COL_WALL = (0.26, 0.34, 0.48)
COL_WALL_TOP = (0.38, 0.52, 0.70)
COL_WORM = (0.45, 1.05, 0.55)
COL_WORM_DARK = (0.15, 0.50, 0.22)
COL_WATER = (0.25, 0.80, 1.20)
COL_SILVER = (1.70, 1.80, 1.90)
COL_GOLD = (1.80, 1.45, 0.50)
COL_BIRD = (0.06, 0.06, 0.10)
COL_START = (0.35, 1.10, 0.50)
COL_FINISH = (1.60, 0.50, 0.40)
COL_SPARK = (1.00, 0.55, 0.12)
