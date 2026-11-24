"""一键运行全部单元测试：python run_tests.py [-v]

不依赖 pygame / 显示设备，只用到 vendor 里的 numpy 和 Pillow。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))


def main(argv):
    verbosity = 2 if "-v" in argv or "--verbose" in argv else 1
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(HERE, "tests"), pattern="test_*.py",
                            top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    print()
    print(f"tests run: {result.testsRun}  failures: {len(result.failures)}  "
          f"errors: {len(result.errors)}  skipped: {len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
