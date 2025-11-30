import sys
import pathlib

# プロジェクトルート（/ayame）をimportパスへ追加
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
