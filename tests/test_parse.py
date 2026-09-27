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


class ParseTest(unittest.TestCase):
    def test_simple_key(self):
        self.assertEqual(parse("a = 1"), {"a": 1})

    def test_table(self):
        self.assertEqual(parse("[server]\nport = 80"), {"server": {"port": 80}})

    def test_comments_are_skipped(self):
        self.assertEqual(parse("# x\na = 1"), {"a": 1})

    def test_empty_text(self):
        self.assertEqual(parse(""), {})

    def test_missing_equals(self):
        with self.assertRaises(TomlError):
            parse("just text")
