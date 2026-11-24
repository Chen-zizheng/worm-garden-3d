"""
make_textures.py —— 生成 textures/ 下的 PNG 纹理（Pillow）。

用法：
    python make_textures.py            # 只生成缺失的
    python make_textures.py --force    # 全部重新生成

纹理是提交物的一部分（手册第 22 页要求 GitHub 上包含纹理素材），
所以它们随仓库一起提交；本脚本保证在别的机器上也能一键重建。
"""
import sys

import assets


def main(argv):
    force = "--force" in argv
    made = assets.ensure_textures(force=force)
    if not made:
        print("textures already exist; use --force to rebuild")
        return 0
    for path in made:
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
