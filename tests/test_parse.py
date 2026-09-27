import datetime
import io
import tomllib
import unittest
from contextlib import redirect_stdout

from tomllite.cli import main as cli_main
from tomllite.parse import TomlError, parse, parse_scalar


class ScalarTest(unittest.TestCase):
    def test_string(self):
        self.assertEqual(parse_scalar('"hi"'), "hi")

    def test_integer(self):
        self.assertEqual(parse_scalar("42"), 42)

    def test_float(self):
        self.assertEqual(parse_scalar("1.5"), 1.5)

    def test_boolean(self):
        self.assertIs(parse_scalar("true"), True)
        self.assertIs(parse_scalar("false"), False)

    def test_bare_word(self):
        self.assertEqual(parse_scalar("bare"), "bare")

    def test_string_escapes(self):
        self.assertEqual(parse_scalar(r'"a\nb\"c\\d\te"'), 'a\nb"c\\d\te')

    def test_unicode_escape(self):
        self.assertEqual(parse_scalar(r'"A"'), "A")

    def test_integer_underscore(self):
        self.assertEqual(parse_scalar("1_000_000"), 1000000)

    def test_integer_hex(self):
        self.assertEqual(parse_scalar("0xDEADBEEF"), 0xDEADBEEF)
        self.assertEqual(parse_scalar("0o755"), 0o755)
        self.assertEqual(parse_scalar("0b1010"), 0b1010)

    def test_float_exponent(self):
        self.assertEqual(parse_scalar("1e10"), 1e10)
        self.assertEqual(parse_scalar("1.5e-3"), 0.0015)

    def test_datetime_kept_as_string(self):
        self.assertEqual(parse_scalar("1979-05-27"), "1979-05-27")
        self.assertEqual(
            parse_scalar("1979-05-27T07:32:00Z"), "1979-05-27T07:32:00Z"
        )
        self.assertEqual(parse_scalar("07:32:00"), "07:32:00")

    def test_illegal_escape_has_position(self):
        with self.assertRaises(TomlError) as ctx:
            parse_scalar(r'"bad\q"')
        self.assertIn("第 1 行第 6 列", str(ctx.exception))
        self.assertIn("非法转义", str(ctx.exception))

    def test_unclosed_string_has_position(self):
        with self.assertRaises(TomlError) as ctx:
            parse('a = "unclosed')
        self.assertIn("第 1 行第 5 列", str(ctx.exception))
        self.assertIn("未闭合", str(ctx.exception))


class ArrayTest(unittest.TestCase):
    def test_int_array(self):
        self.assertEqual(parse("a = [1, 2, 3]"), {"a": [1, 2, 3]})

    def test_empty_array(self):
        self.assertEqual(parse("a = []"), {"a": []})

    def test_nested_array(self):
        self.assertEqual(parse("a = [[1, 2], [3]]"), {"a": [[1, 2], [3]]})

    def test_array_of_inline_tables(self):
        self.assertEqual(
            parse("a = [{x = 1}, {x = 2}]"), {"a": [{"x": 1}, {"x": 2}]}
        )

    def test_multiline_array_with_trailing_comma(self):
        self.assertEqual(parse("a = [1,\n2,\n3,]"), {"a": [1, 2, 3]})

    def test_mixed_type_array_rejected(self):
        with self.assertRaises(TomlError) as ctx:
            parse('a = [1, "x"]')
        self.assertIn("类型混杂", str(ctx.exception))
        self.assertIn("第 1 行", str(ctx.exception))

    def test_unclosed_array(self):
        with self.assertRaises(TomlError) as ctx:
            parse("a = [1, 2")
        self.assertIn("未闭合", str(ctx.exception))


class InlineTableTest(unittest.TestCase):
    def test_inline_table(self):
        self.assertEqual(parse("p = {x = 1, y = 2}"), {"p": {"x": 1, "y": 2}})

    def test_nested_inline_table(self):
        self.assertEqual(
            parse("p = {a = {b = [1, 2]}}"), {"p": {"a": {"b": [1, 2]}}}
        )

    def test_duplicate_key_in_inline_table(self):
        with self.assertRaises(TomlError) as ctx:
            parse("p = {x = 1, x = 2}")
        self.assertIn("重复键 x", str(ctx.exception))


class DuplicateKeyTest(unittest.TestCase):
    def test_duplicate_key_reports_both_lines(self):
        with self.assertRaises(TomlError) as ctx:
            parse("a = 1\na = 2")
        self.assertEqual(str(ctx.exception), "重复键 a（第 1 行与第 2 行）")

    def test_same_key_in_different_tables_is_legal(self):
        self.assertEqual(
            parse("[t1]\na = 1\n[t2]\na = 2"), {"t1": {"a": 1}, "t2": {"a": 2}}
        )

    def test_duplicate_key_after_table_header(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[s]\na = 1\nb = 2\na = 3")
        self.assertEqual(str(ctx.exception), "重复键 a（第 2 行与第 4 行）")


class TableTest(unittest.TestCase):
    def test_table(self):
        self.assertEqual(parse("[server]\nport = 80"), {"server": {"port": 80}})

    def test_nested_table(self):
        self.assertEqual(
            parse("[a.b]\nc = 1"), {"a": {"b": {"c": 1}}}
        )

    def test_implicit_parent_can_be_defined_later(self):
        self.assertEqual(
            parse("[a.b]\nx = 1\n[a]\ny = 2"),
            {"a": {"b": {"x": 1}, "y": 2}},
        )

    def test_unclosed_header(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[abc")
        self.assertIn("第 1 行第 1 列", str(ctx.exception))
        self.assertIn("表头未闭合", str(ctx.exception))

    def test_empty_table_name(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[]")
        self.assertIn("空表名", str(ctx.exception))

    def test_duplicate_table_definition(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[a]\nx = 1\n[a]\ny = 2")
        self.assertIn("第 3 行", str(ctx.exception))
        self.assertIn("重复定义", str(ctx.exception))


class ErrorPositionTest(unittest.TestCase):
    def test_missing_equals(self):
        with self.assertRaises(TomlError) as ctx:
            parse("just text")
        self.assertIn("第 1 行", str(ctx.exception))
        self.assertIn("列", str(ctx.exception))

    def test_missing_value(self):
        with self.assertRaises(TomlError) as ctx:
            parse("a = ")
        self.assertIn("缺少值", str(ctx.exception))

    def test_error_line_counts_newlines(self):
        with self.assertRaises(TomlError) as ctx:
            parse("a = 1\nb = 2\nbad line here")
        self.assertIn("第 3 行", str(ctx.exception))


class ParseTest(unittest.TestCase):
    def test_simple_key(self):
        self.assertEqual(parse("a = 1"), {"a": 1})

    def test_comments_are_skipped(self):
        self.assertEqual(parse("# x\na = 1"), {"a": 1})

    def test_comment_after_value(self):
        self.assertEqual(parse("a = 1 # one"), {"a": 1})

    def test_empty_text(self):
        self.assertEqual(parse(""), {})

    def test_deterministic(self):
        text = "[t]\na = [1, 2]\nb = {x = \"y\"}\n"
        self.assertEqual(parse(text), parse(text))


class TomllibCompatTest(unittest.TestCase):
    DOC = """
title = "demo"
count = 1_000
hexed = 0xDEADBEEF
pi = 3.14
big = 1e10
flag = true
day = 1979-05-27
moment = 1979-05-27T07:32:00Z
clock = 07:32:00
tags = ["a", "b"]
nums = [1, 2, 3]
nested = [[1, 2], [3]]
point = {x = 1, y = 2}

[owner]
name = "Tom"

[database.ports]
a = 8000
"""

    @staticmethod
    def norm_stdlib(node):
        if isinstance(node, dict):
            return {k: TomllibCompatTest.norm_stdlib(v) for k, v in node.items()}
        if isinstance(node, list):
            return [TomllibCompatTest.norm_stdlib(v) for v in node]
        if isinstance(node, (datetime.datetime, datetime.date, datetime.time)):
            return node.isoformat()
        return node

    @staticmethod
    def norm_ours(node):
        if isinstance(node, dict):
            return {k: TomllibCompatTest.norm_ours(v) for k, v in node.items()}
        if isinstance(node, list):
            return [TomllibCompatTest.norm_ours(v) for v in node]
        if isinstance(node, str) and node.endswith("Z") and "T" in node:
            return node[:-1] + "+00:00"
        return node

    def test_matches_tomllib(self):
        self.assertEqual(
            self.norm_ours(parse(self.DOC)),
            self.norm_stdlib(tomllib.loads(self.DOC)),
        )


class ScaleTest(unittest.TestCase):
    def test_ten_mb_single_pass(self):
        header = '[server]\nhost = "example.com"\nports = [8000, 8001]\n'
        rows = []
        total = len(header)
        i = 0
        while total < 10_000_000:
            row = "key_%d = %d\n" % (i, i)
            rows.append(row)
            total += len(row)
            i += 1
        result = parse(header + "".join(rows))
        self.assertEqual(result["server"]["key_0"], 0)
        self.assertEqual(result["server"]["key_%d" % (i - 1)], i - 1)


class CliTest(unittest.TestCase):
    def run_cli(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli_main(argv)
        return code, out.getvalue()

    def test_text_array_output_format(self):
        code, out = self.run_cli(["--text", "a = [1, 2, 3]"])
        self.assertEqual(code, 0)
        self.assertEqual(out, '{"a": [1, 2, 3]}\n')

    def test_text_duplicate_key_fails(self):
        code, _ = self.run_cli(["--text", "a = 1\\na = 2"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
