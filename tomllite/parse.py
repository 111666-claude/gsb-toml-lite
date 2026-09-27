"""TOML 子集解析：表、标量、数组、内联表。只用标准库。"""


class TomlError(Exception):
    """TOML 不合法。缺陷：不带行号。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def parse_scalar(text):
    """解析标量。缺陷：数组只按整串处理，不切逗号。"""
    text = text.strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if text.startswith("[") and text.endswith("]"):
        # 缺陷：没有按逗号切分，也没有递归解析元素
        return text[1:-1]
    return text


def parse(text):
    """解析 TOML 文本。缺陷：重复键静默覆盖，也没有行号。"""
    out = {}
    table = out
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip()
            table = out.setdefault(name, {})
            continue
        if "=" not in stripped:
            raise TomlError("不是键值对：%r" % stripped)
        key, value = stripped.split("=", 1)
        # 缺陷：重复键直接覆盖
        table[key.strip()] = parse_scalar(value)
    return out
