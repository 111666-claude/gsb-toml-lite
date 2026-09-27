"""TOML 子集解析：表、标量、数组、内联表。只用标准库。"""

import re

__all__ = ["TomlError", "parse", "parse_scalar"]


class TomlError(Exception):
    """TOML 不合法，消息里带行号与列号。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


_DATE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"([Tt ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})?)?\Z"
)
_TIME_RE = re.compile(r"\d{2}:\d{2}:\d{2}(\.\d+)?\Z")

_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
}

_TOKEN_DELIMS = set(" \t\r\n,]}#")
_BARE_KEY_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


class _Parser:
    """单遍解析器：按字符扫描，跟踪行号与列号。"""

    def __init__(self, text):
        self.text = text
        self.n = len(text)
        self.pos = 0
        self.line = 1
        self.line_start = 0
        self.root = {}
        self.current = self.root
        # id(表) -> {键: 首次定义行号}，用于重复键报错
        self.key_lines = {id(self.root): {}}
        # 已被表头显式定义过的表
        self.explicit_tables = set()

    @property
    def col(self):
        return self.pos - self.line_start + 1

    def error(self, message, line=None, col=None):
        line = self.line if line is None else line
        col = self.col if col is None else col
        raise TomlError("第 %d 行第 %d 列：%s" % (line, col, message))

    def peek(self):
        if self.pos < self.n:
            return self.text[self.pos]
        return ""

    def advance(self):
        c = self.text[self.pos]
        self.pos += 1
        if c == "\n":
            self.line += 1
            self.line_start = self.pos
        return c

    def skip_inline_ws(self):
        while self.pos < self.n and self.text[self.pos] in " \t\r":
            self.pos += 1

    def skip_trivia(self):
        """跳过空白、换行与 # 注释。"""
        while self.pos < self.n:
            c = self.text[self.pos]
            if c == "\n":
                self.advance()
            elif c in " \t\r":
                self.pos += 1
            elif c == "#":
                end = self.text.find("\n", self.pos)
                self.pos = self.n if end < 0 else end
            else:
                return

    def parse(self):
        while True:
            self.skip_trivia()
            if self.pos >= self.n:
                return self.root
            if self.peek() == "[":
                self.parse_header()
            else:
                self.parse_keyval(self.current)

    def parse_header(self):
        start_line, start_col = self.line, self.col
        self.advance()  # [
        self.skip_inline_ws()
        if self.peek() == "]":
            self.error("空表名", start_line, start_col)
        parts = self.parse_key_parts()
        self.skip_inline_ws()
        if self.peek() != "]":
            self.error("表头未闭合，缺少 ]", start_line, start_col)
        self.advance()  # ]
        table = self.root
        for part in parts[:-1]:
            existing = table.get(part)
            if existing is None:
                existing = {}
                table[part] = existing
                self.key_lines[id(existing)] = {}
            elif not isinstance(existing, dict):
                self.error(
                    "键 %s 已被定义为值，不能作为表" % part, start_line, start_col
                )
            table = existing
        name = parts[-1]
        existing = table.get(name)
        if existing is None:
            existing = {}
            table[name] = existing
            self.key_lines[id(existing)] = {}
        elif not isinstance(existing, dict):
            self.error(
                "键 %s 已被定义为值，不能作为表" % name, start_line, start_col
            )
        elif id(existing) in self.explicit_tables:
            self.error("表 %s 重复定义" % ".".join(parts), start_line, start_col)
        self.explicit_tables.add(id(existing))
        self.current = existing

    def parse_key_parts(self):
        parts = []
        while True:
            self.skip_inline_ws()
            c = self.peek()
            if c == '"':
                parts.append(self.parse_basic_string())
            elif c == "'":
                parts.append(self.parse_literal_string())
            else:
                start = self.pos
                while self.pos < self.n and self.text[self.pos] in _BARE_KEY_CHARS:
                    self.pos += 1
                if self.pos == start:
                    self.error("键名为空或含非法字符")
                parts.append(self.text[start:self.pos])
            self.skip_inline_ws()
            if self.peek() == ".":
                self.advance()
            else:
                return parts

    def parse_keyval(self, table):
        parts = self.parse_key_parts()
        self.skip_inline_ws()
        if self.peek() != "=":
            self.error("缺少 =")
        self.advance()  # =
        self.skip_inline_ws()
        if self.pos >= self.n or self.text[self.pos] == "\n":
            self.error("缺少值")
        value = self.parse_value()
        target = table
        for part in parts[:-1]:
            existing = target.get(part)
            if existing is None:
                existing = {}
                target[part] = existing
                self.key_lines[id(existing)] = {}
                self.key_lines[id(target)][part] = self.line
            elif not isinstance(existing, dict):
                self.error("键 %s 已被定义为值，不能嵌套" % part)
            target = existing
        key = parts[-1]
        if key in target:
            first = self.key_lines[id(target)].get(key, "?")
            raise TomlError(
                "重复键 %s（第 %s 行与第 %d 行）" % (key, first, self.line)
            )
        target[key] = value
        self.key_lines[id(target)][key] = self.line

    def parse_value(self):
        c = self.peek()
        if c == '"':
            return self.parse_basic_string()
        if c == "'":
            return self.parse_literal_string()
        if c == "[":
            return self.parse_array()
        if c == "{":
            return self.parse_inline_table()
        return self.parse_token()

    def parse_basic_string(self):
        start_line, start_col = self.line, self.col
        self.advance()  # "
        out = []
        while True:
            if self.pos >= self.n or self.text[self.pos] == "\n":
                self.error("字符串未闭合", start_line, start_col)
            c = self.advance()
            if c == '"':
                return "".join(out)
            if c == "\\":
                if self.pos >= self.n or self.text[self.pos] == "\n":
                    self.error("字符串未闭合", start_line, start_col)
                esc_line, esc_col = self.line, self.col
                esc = self.advance()
                if esc in _ESCAPES:
                    out.append(_ESCAPES[esc])
                elif esc == "u":
                    out.append(self.parse_unicode_escape(4, esc_line, esc_col))
                elif esc == "U":
                    out.append(self.parse_unicode_escape(8, esc_line, esc_col))
                else:
                    self.error("非法转义 \\%s" % esc, esc_line, esc_col)
            else:
                out.append(c)

    def parse_unicode_escape(self, digits, esc_line, esc_col):
        if self.pos + digits > self.n:
            self.error("非法转义：\\u 后十六进制位数不足", esc_line, esc_col)
        hex_digits = self.text[self.pos:self.pos + digits]
        if not all(ch in "0123456789abcdefABCDEF" for ch in hex_digits):
            self.error("非法转义：\\u 后不是十六进制", esc_line, esc_col)
        for _ in range(digits):
            self.advance()
        try:
            return chr(int(hex_digits, 16))
        except (ValueError, OverflowError):
            self.error("非法转义：码点超出范围", esc_line, esc_col)

    def parse_literal_string(self):
        start_line, start_col = self.line, self.col
        self.advance()  # '
        end = self.text.find("'", self.pos)
        if end < 0 or ("\n" in self.text[self.pos:end]):
            self.error("字符串未闭合", start_line, start_col)
        value = self.text[self.pos:end]
        while self.pos <= end:
            self.advance()
        return value

    def parse_array(self):
        start_line, start_col = self.line, self.col
        self.advance()  # [
        items = []
        elem_type = None
        while True:
            self.skip_trivia()
            if self.pos >= self.n:
                self.error("数组未闭合，缺少 ]", start_line, start_col)
            if self.peek() == "]":
                self.advance()
                return items
            value_line, value_col = self.line, self.col
            value = self.parse_value()
            value_type = type(value)
            if elem_type is None:
                elem_type = value_type
            elif value_type is not elem_type:
                self.error("数组元素类型混杂", value_line, value_col)
            items.append(value)
            self.skip_trivia()
            if self.pos >= self.n:
                self.error("数组未闭合，缺少 ]", start_line, start_col)
            c = self.peek()
            if c == ",":
                self.advance()
            elif c == "]":
                self.advance()
                return items
            else:
                self.error("数组元素后缺少 , 或 ]")

    def parse_inline_table(self):
        start_line, start_col = self.line, self.col
        self.advance()  # {
        table = {}
        self.key_lines[id(table)] = {}
        self.skip_trivia()
        if self.peek() == "}":
            self.advance()
            return table
        while True:
            self.parse_keyval(table)
            self.skip_trivia()
            if self.pos >= self.n:
                self.error("内联表未闭合，缺少 }", start_line, start_col)
            c = self.peek()
            if c == ",":
                self.advance()
                self.skip_trivia()
            elif c == "}":
                self.advance()
                return table
            else:
                self.error("内联表键值后缺少 , 或 }")

    def parse_token(self):
        start = self.pos
        while self.pos < self.n and self.text[self.pos] not in _TOKEN_DELIMS:
            self.pos += 1
        token = self.text[start:self.pos]
        if not token:
            self.error("缺少值")
        if token == "true":
            return True
        if token == "false":
            return False
        if _DATE_RE.match(token) or _TIME_RE.match(token):
            return token
        try:
            return int(token, 0)
        except ValueError:
            pass
        try:
            return float(token)
        except ValueError:
            pass
        return token


def parse(text):
    """解析 TOML 文本，返回嵌套字典。空输入返回 {}。"""
    return _Parser(text).parse()


def parse_scalar(text):
    """解析单个值（标量、数组或内联表）。"""
    parser = _Parser(text)
    parser.skip_trivia()
    if parser.pos >= parser.n:
        parser.error("缺少值")
    value = parser.parse_value()
    parser.skip_trivia()
    if parser.pos < parser.n:
        parser.error("值后有多余内容")
    return value
