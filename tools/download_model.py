"""提前准备固定版本的本地转写模型；不访问收费语言模型 API。"""

import argparse
from pathlib import Path

from faster_whisper.utils import download_model
from web.pipeline import MODEL_NAME, MODEL_REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-files-only", action="store_true", help="只检查已下载的模型")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = download_model(MODEL_NAME, cache_dir=str(root / ".singlish-cache" / "models"),
                          revision=MODEL_REVISION, local_files_only=args.local_files_only)
    print(f"本地模型已就绪：{MODEL_NAME}，修订版 {MODEL_REVISION}")
    # 只报告模型目录；这里不读取 .env。
    print(path)


if __name__ == "__main__":
    main()
