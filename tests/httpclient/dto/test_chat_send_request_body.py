import unittest

from pydantic import ValidationError

from spoonbot.httpclient.dto.ChatSendRequestBody import (
    MAX_SIZE,
    ChatSendRequestBody,
    _utf16_length,
)


def make_body(message: str) -> ChatSendRequestBody:
    return ChatSendRequestBody(message=message)


class StripMessageTest(unittest.TestCase):
    def test_strips_leading_and_trailing_whitespace(self) -> None:
        body = make_body("  hello world  ")

        self.assertEqual(body.message, "hello world")

    def test_strips_tabs_and_newlines(self) -> None:
        body = make_body("\t\nhello\n\t")

        self.assertEqual(body.message, "hello")

    def test_keeps_internal_whitespace(self) -> None:
        body = make_body("  hello   world  ")

        self.assertEqual(body.message, "hello   world")

    def test_whitespace_only_becomes_empty(self) -> None:
        body = make_body(" \t\n ")

        self.assertEqual(body.message, "")


class ValidMessageTest(unittest.TestCase):
    def test_returns_true_for_normal_message(self) -> None:
        body = make_body("hello world")

        self.assertTrue(body.valid_message())

    def test_returns_false_for_empty_message(self) -> None:
        body = make_body("")

        self.assertFalse(body.valid_message())

    def test_returns_false_for_whitespace_only_message(self) -> None:
        body = make_body("   ")

        self.assertFalse(body.valid_message())

    def test_returns_true_when_utf16_length_equals_max_size(self) -> None:
        body = make_body("a" * MAX_SIZE)

        self.assertEqual(_utf16_length(body.message), MAX_SIZE)
        self.assertTrue(body.valid_message())

    def test_returns_false_when_utf16_length_exceeds_max_size(self) -> None:
        body = make_body("a" * (MAX_SIZE + 1))

        self.assertEqual(_utf16_length(body.message), MAX_SIZE + 1)
        self.assertFalse(body.valid_message())

    def test_counts_surrogate_pairs_as_two_utf16_units(self) -> None:
        body = make_body("😀" * (MAX_SIZE // 2))

        self.assertEqual(_utf16_length(body.message), MAX_SIZE)
        self.assertTrue(body.valid_message())

    def test_rejects_message_exceeding_max_size_with_surrogate_pairs(
        self,
    ) -> None:
        body = make_body("😀" * (MAX_SIZE // 2 + 1))

        self.assertGreater(_utf16_length(body.message), MAX_SIZE)
        self.assertFalse(body.valid_message())


class Utf16LengthTest(unittest.TestCase):
    def test_ascii_string_length(self) -> None:
        self.assertEqual(_utf16_length("hello"), 5)

    def test_empty_string_length(self) -> None:
        self.assertEqual(_utf16_length(""), 0)

    def test_surrogate_pair_length(self) -> None:
        self.assertEqual(_utf16_length("😀"), 2)

    def test_mixed_string_length(self) -> None:
        self.assertEqual(_utf16_length("a😀b"), 4)


class FrozenTest(unittest.TestCase):
    def test_model_is_frozen(self) -> None:
        body = make_body("hello")

        with self.assertRaises(ValidationError):
            body.__setattr__("message", "changed")


if __name__ == "__main__":
    unittest.main()
