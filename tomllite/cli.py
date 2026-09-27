"""命令行入口：解析 TOML 并打印 JSON。"""

import argparse
import json
import sys

from .parse import TomlError, parse


def build_parser():
    parser = argparse.ArgumentParser(prog="toml-lite", description="TOML 子集解析")
    parser.add_argument("--file", help="TOML 文件")
    parser.add_argument("--text", help="直接给 TOML 文本（用 \\n 表示换行）")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.text is not None:
            text = args.text.replace("\\n", "\n")
        elif args.file:
            with open(args.file, encoding="utf-8") as handle:
                text = handle.read()
        else:
            print("错误：需要 --file 或 --text", file=sys.stderr)
            return 2
        result = parse(text)
    except (OSError, TomlError) as error:
        print("错误：%s" % error, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
