import json
import tomllib
import unittest

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

    def test_integer_underscore(self):
        self.assertEqual(parse_scalar("1_000_000"), 1000000)

    def test_integer_hex(self):
        self.assertEqual(parse_scalar("0x1F"), 31)
        self.assertEqual(parse_scalar("0xdead_beef"), 0xDEADBEEF)

    def test_float_exponent(self):
        self.assertEqual(parse_scalar("1e5"), 100000.0)
        self.assertEqual(parse_scalar("1.5e-3"), 0.0015)

    def test_date_kept_as_string(self):
        self.assertEqual(parse_scalar("2024-01-01"), "2024-01-01")


class StringEscapeTest(unittest.TestCase):
    def test_escapes(self):
        self.assertEqual(parse_scalar(r'"a\nb"'), "a\nb")
        self.assertEqual(parse_scalar(r'"a\tb"'), "a\tb")
        self.assertEqual(parse_scalar(r'"a\"b"'), 'a"b')
        self.assertEqual(parse_scalar(r'"a\\b"'), "a\\b")

    def test_illegal_escape_has_position(self):
        with self.assertRaises(TomlError) as ctx:
            parse('a = "x\\qy"')
        err = ctx.exception
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 7)
        self.assertIn("非法转义", str(err))

    def test_unclosed_string_has_position(self):
        with self.assertRaises(TomlError) as ctx:
            parse('a = "abc')
        err = ctx.exception
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 5)
        self.assertIn("未闭合", str(err))


class ArrayTest(unittest.TestCase):
    def test_int_array(self):
        self.assertEqual(parse("a = [1, 2, 3]"), {"a": [1, 2, 3]})

    def test_empty_array(self):
        self.assertEqual(parse("a = []"), {"a": []})

    def test_nested_array(self):
        self.assertEqual(parse("a = [[1, 2], [3, 4]]"), {"a": [[1, 2], [3, 4]]})

    def test_inline_table_in_array(self):
        self.assertEqual(
            parse("a = [{x = 1}, {x = 2}]"), {"a": [{"x": 1}, {"x": 2}]}
        )

    def test_array_of_strings_with_commas(self):
        self.assertEqual(parse('a = ["x,y", "z"]'), {"a": ["x,y", "z"]})

    def test_trailing_comma(self):
        self.assertEqual(parse("a = [1, 2,]"), {"a": [1, 2]})

    def test_mixed_types_error_with_position(self):
        with self.assertRaises(TomlError) as ctx:
            parse('a = [1, "two"]')
        err = ctx.exception
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 9)
        self.assertIn("类型混杂", str(err))

    def test_unclosed_array(self):
        with self.assertRaises(TomlError) as ctx:
            parse("a = [1, 2")
        self.assertIn("未闭合", str(ctx.exception))


class DuplicateKeyTest(unittest.TestCase):
    def test_duplicate_key_reports_both_lines(self):
        with self.assertRaises(TomlError) as ctx:
            parse("a = 1\na = 2")
        err = ctx.exception
        self.assertIn("重复键 a（第 1 行与第 2 行）", str(err))
        self.assertEqual(err.line, 2)

    def test_same_key_in_different_tables_ok(self):
        self.assertEqual(
            parse("[a]\nk = 1\n[b]\nk = 2"), {"a": {"k": 1}, "b": {"k": 2}}
        )

    def test_duplicate_key_in_nested_table(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[t]\nx = 1\nx = 2")
        self.assertIn("重复键 x（第 2 行与第 3 行）", str(ctx.exception))


class TableTest(unittest.TestCase):
    def test_nested_table(self):
        self.assertEqual(
            parse("[a.b]\nc = 1"), {"a": {"b": {"c": 1}}}
        )

    def test_deep_nested_table(self):
        self.assertEqual(
            parse("[a.b.c]\nv = true"), {"a": {"b": {"c": {"v": True}}}}
        )

    def test_explicit_parent_after_child_ok(self):
        self.assertEqual(
            parse("[a.b]\nx = 1\n[a]\ny = 2"),
            {"a": {"b": {"x": 1}, "y": 2}},
        )

    def test_unclosed_header(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[abc")
        err = ctx.exception
        self.assertEqual(err.line, 1)
        self.assertIn("表头未闭合", str(err))

    def test_empty_table_name(self):
        for text in ("[]", "[ ]", "[a..b]"):
            with self.assertRaises(TomlError) as ctx:
                parse(text)
            self.assertIn("空表名", str(ctx.exception))

    def test_table_redefined(self):
        with self.assertRaises(TomlError) as ctx:
            parse("[a]\nx = 1\n[a]\ny = 2")
        err = ctx.exception
        self.assertEqual(err.line, 3)
        self.assertIn("重复定义", str(err))


class InlineTableTest(unittest.TestCase):
    def test_inline_table(self):
        self.assertEqual(parse("a = {x = 1, y = 2}"), {"a": {"x": 1, "y": 2}})

    def test_nested_inline_table(self):
        self.assertEqual(
            parse("a = {b = {c = 1}}"), {"a": {"b": {"c": 1}}}
        )


class ParseTest(unittest.TestCase):
    def test_simple_key(self):
        self.assertEqual(parse("a = 1"), {"a": 1})

    def test_table(self):
        self.assertEqual(parse("[server]\nport = 80"), {"server": {"port": 80}})

    def test_comments_are_skipped(self):
        self.assertEqual(parse("# x\na = 1"), {"a": 1})

    def test_trailing_comment(self):
        self.assertEqual(parse("a = 1 # one"), {"a": 1})

    def test_empty_text(self):
        self.assertEqual(parse(""), {})

    def test_missing_equals(self):
        with self.assertRaises(TomlError) as ctx:
            parse("just text")
        err = ctx.exception
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 1)

    def test_error_position_points_into_line(self):
        with self.assertRaises(TomlError) as ctx:
            parse("ok = 1\nbad line here")
        err = ctx.exception
        self.assertEqual(err.line, 2)
        self.assertEqual(err.col, 1)

    def test_deterministic(self):
        text = "[a]\nx = [1, 2]\ny = \"s\"\n[b]\nz = 0x10"
        self.assertEqual(parse(text), parse(text))


class TomllibParityTest(unittest.TestCase):
    DOC = (
        'title = "demo"\n'
        "count = 1_000\n"
        "hex = 0xFF\n"
        "ratio = 2.5\n"
        "big = 1e6\n"
        "flag = true\n"
        "tags = [1, 2, 3]\n"
        "names = [\"a\", \"b\"]\n"
        "point = {x = 1, y = 2}\n"
        "\n"
        "[server]\n"
        "port = 8080\n"
        "\n"
        "[server.tls]\n"
        "enabled = false\n"
    )

    def test_matches_tomllib(self):
        mine = parse(self.DOC)
        theirs = json.loads(json.dumps(tomllib.loads(self.DOC)))
        self.assertEqual(mine, theirs)


if __name__ == "__main__":
    unittest.main()
