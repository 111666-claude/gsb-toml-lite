"""TOML 子集解析：表、标量、数组、内联表。只用标准库。

单遍逐行解析；值（标量/数组/内联表）用递归下降，不用正则。
所有错误都带行号与列号。
"""


class TomlError(Exception):
    """TOML 不合法。带行号（line）与列号（col），均从 1 开始。"""

    def __init__(self, message, line=None, col=None):
        self.message = message
        self.line = line
        self.col = col
        if line is not None and col is not None:
            super().__init__("第 %d 行第 %d 列：%s" % (line, col, message))
        else:
            super().__init__(message)


_TYPE_NAMES = {
    str: "字符串",
    bool: "布尔",
    int: "整数",
    float: "浮点",
    list: "数组",
    dict: "内联表",
}

_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}

_BARE_STOP = " \t,]}#"


def _type_name(kind):
    return _TYPE_NAMES.get(kind, kind.__name__)


def _skip_spaces(text, index):
    while index < len(text) and text[index] in " \t":
        index += 1
    return index


def _parse_string(text, index, line, col0):
    """解析双引号字符串，text[index] 是开引号。返回 (值, 下一位置)。"""
    start = index
    index += 1
    out = []
    while index < len(text):
        char = text[index]
        if char == '"':
            return "".join(out), index + 1
        if char == "\\":
            if index + 1 >= len(text):
                raise TomlError("字符串未闭合", line, col0 + start + 1)
            esc = text[index + 1]
            if esc not in _ESCAPES:
                raise TomlError("非法转义：\\%s" % esc, line, col0 + index + 1)
            out.append(_ESCAPES[esc])
            index += 2
        else:
            out.append(char)
            index += 1
    raise TomlError("字符串未闭合", line, col0 + start + 1)


def _token_to_scalar(token, line, col):
    if token == "true":
        return True
    if token == "false":
        return False
    try:
        return int(token)  # 十进制，支持下划线（如 1_000）
    except ValueError:
        pass
    if token[:2].lower() == "0x":
        try:
            return int(token, 16)
        except ValueError:
            raise TomlError("非法十六进制整数：%r" % token, line, col)
    try:
        return float(token)  # 支持指数（如 1e5、1.5e-3）
    except ValueError:
        pass
    # 日期时间等按字符串原样保留
    return token


def _parse_bare(text, index, line, col0):
    """解析裸标量（布尔/整数/浮点/日期字符串）。返回 (值, 下一位置)。"""
    end = index
    while end < len(text) and text[end] not in _BARE_STOP:
        end += 1
    token = text[index:end]
    if not token:
        raise TomlError("缺少值", line, col0 + index + 1)
    return _token_to_scalar(token, line, col0 + index + 1), end


def _parse_array(text, index, line, col0):
    """解析数组：按逗号切分并递归解析元素。返回 (列表, 下一位置)。"""
    start = index
    index += 1
    items = []
    positions = []
    while True:
        index = _skip_spaces(text, index)
        if index >= len(text):
            raise TomlError("数组未闭合", line, col0 + start + 1)
        if text[index] == "]":
            index += 1
            break
        positions.append(index)
        value, index = _parse_value(text, index, line, col0)
        items.append(value)
        index = _skip_spaces(text, index)
        if index >= len(text):
            raise TomlError("数组未闭合", line, col0 + start + 1)
        if text[index] == ",":
            index += 1
            continue
        if text[index] == "]":
            index += 1
            break
        raise TomlError("数组元素后应为 , 或 ]", line, col0 + index + 1)
    if items:
        first_type = type(items[0])
        for value, pos in zip(items[1:], positions[1:]):
            if type(value) is not first_type:
                raise TomlError(
                    "数组元素类型混杂：%s 与 %s"
                    % (_type_name(first_type), _type_name(type(value))),
                    line,
                    col0 + pos + 1,
                )
    return items, index


def _parse_inline_table(text, index, line, col0):
    """解析内联表 {k = v, ...}。返回 (字典, 下一位置)。"""
    start = index
    index += 1
    result = {}
    while True:
        index = _skip_spaces(text, index)
        if index >= len(text):
            raise TomlError("内联表未闭合", line, col0 + start + 1)
        if text[index] == "}":
            return result, index + 1
        key_start = index
        while index < len(text) and text[index] not in "= \t":
            index += 1
        key = text[key_start:index]
        index = _skip_spaces(text, index)
        if not key or index >= len(text) or text[index] != "=":
            raise TomlError("内联表缺少 =", line, col0 + key_start + 1)
        value, index = _parse_value(text, index + 1, line, col0)
        if key in result:
            raise TomlError(
                "重复键 %s（第 %d 行与第 %d 行）" % (key, line, line),
                line,
                col0 + key_start + 1,
            )
        result[key] = value
        index = _skip_spaces(text, index)
        if index >= len(text):
            raise TomlError("内联表未闭合", line, col0 + start + 1)
        if text[index] == ",":
            index += 1
            continue
        if text[index] == "}":
            return result, index + 1
        raise TomlError("内联表元素后应为 , 或 }", line, col0 + index + 1)


def _parse_value(text, index, line, col0):
    """解析一个值。col0 是 text[0] 在行内的 0 基列偏移。返回 (值, 下一位置)。"""
    index = _skip_spaces(text, index)
    if index >= len(text):
        raise TomlError("缺少值", line, col0 + index + 1)
    char = text[index]
    if char == '"':
        return _parse_string(text, index, line, col0)
    if char == "[":
        return _parse_array(text, index, line, col0)
    if char == "{":
        return _parse_inline_table(text, index, line, col0)
    return _parse_bare(text, index, line, col0)


def parse_scalar(text):
    """解析单个值文本（标量、数组或内联表）。"""
    value, _ = _parse_value(text.strip(), 0, 1, 1)
    return value


def _first_col(line):
    return len(line) - len(line.lstrip()) + 1


def parse(text):
    """解析 TOML 文本。重复键、非法语法都报 TomlError（带行号列号）。"""
    out = {}
    table = out
    defined_tables = set()  # 显式定义过的表路径（元组）
    key_lines = {id(out): {}}  # 每张表：键 -> 首次出现的行号
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            bracket_col = line.index("[") + 1
            if not stripped.endswith("]"):
                raise TomlError("表头未闭合", lineno, bracket_col)
            name = stripped[1:-1].strip()
            parts = [part.strip() for part in name.split(".")]
            if not name or any(not part for part in parts):
                raise TomlError("空表名", lineno, bracket_col)
            table = out
            path = ()
            for part in parts:
                path += (part,)
                existing = table.get(part)
                if existing is None:
                    existing = {}
                    table[part] = existing
                elif not isinstance(existing, dict):
                    raise TomlError("键 %s 已存在且不是表" % part, lineno, bracket_col)
                table = existing
            if path in defined_tables:
                raise TomlError("表 %s 重复定义" % name, lineno, bracket_col)
            defined_tables.add(path)
            key_lines.setdefault(id(table), {})
            continue
        eq = line.find("=")
        if eq < 0:
            raise TomlError("不是键值对：%r" % stripped, lineno, _first_col(line))
        key = line[:eq].strip()
        if not key:
            raise TomlError("空键", lineno, eq + 1)
        rest = line[eq + 1 :]
        value, end = _parse_value(rest, 0, lineno, eq + 1)
        tail = rest[end:].strip()
        if tail and not tail.startswith("#"):
            raise TomlError("值后有多余内容：%r" % tail, lineno, eq + 1 + end + 1)
        lines = key_lines.setdefault(id(table), {})
        if key in table:
            first = lines.get(key)
            if first is None:
                raise TomlError("键 %s 与已有表冲突" % key, lineno, _first_col(line))
            raise TomlError(
                "重复键 %s（第 %d 行与第 %d 行）" % (key, first, lineno),
                lineno,
                _first_col(line),
            )
        lines[key] = lineno
        table[key] = value
    return out
