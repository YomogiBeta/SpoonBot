import unittest
from unittest.mock import patch

from pydantic import ValidationError

from spoonbot.dto.SpoonAuthorization import (
    END_REFRESH_TOKEN_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS_LEAST,
    TOKEN_EXPIRE_SECONDS_LEAST,
    SpoonAuthorization,
)
from spoonbot.enums.TokenStatus import TokenStatus

NOW = 1_700_000_000


def make_authorization(
    expire_at: int = NOW + 1_000,
    refresh_expire_at: int = NOW + 100_000,
) -> SpoonAuthorization:
    return SpoonAuthorization(
        id="user-1",
        access_token="access-token",
        token_type="Bearer",
        expire_at=expire_at,
        refresh_expire_at=refresh_expire_at,
        refresh_token="refresh-token",
        scope="scope",
        token_status=TokenStatus.DEFAULT,
    )


class SpoonAuthorizationTestBase(unittest.TestCase):
    def setUp(self) -> None:
        time_patcher = patch(
            "spoonbot.dto.SpoonAuthorization.time.time", return_value=NOW
        )
        time_patcher.start()
        self.addCleanup(time_patcher.stop)


class ConstructionTest(SpoonAuthorizationTestBase):
    def test_creates_model_from_fields(self) -> None:
        authorization = make_authorization()

        self.assertEqual(authorization.id, "user-1")
        self.assertEqual(authorization.access_token, "access-token")
        self.assertEqual(authorization.token_type, "Bearer")
        self.assertEqual(authorization.expire_at, NOW + 1_000)
        self.assertEqual(authorization.refresh_expire_at, NOW + 100_000)
        self.assertEqual(authorization.refresh_token, "refresh-token")
        self.assertEqual(authorization.scope, "scope")
        self.assertIs(authorization.token_status, TokenStatus.DEFAULT)

    def test_converts_token_status_string_to_enum(self) -> None:
        authorization = SpoonAuthorization.model_validate(
            {
                "id": "user-1",
                "access_token": "access-token",
                "token_type": "Bearer",
                "expire_at": NOW,
                "refresh_expire_at": NOW,
                "refresh_token": "refresh-token",
                "scope": "scope",
                "token_status": "CHAT_BLOCK",
            }
        )

        self.assertIs(authorization.token_status, TokenStatus.CHAT_BLOCK)

    def test_model_is_frozen(self) -> None:
        authorization = make_authorization()

        with self.assertRaises(ValidationError):
            authorization.__setattr__("id", "changed")


class ValidAccessTokenTest(SpoonAuthorizationTestBase):
    def test_returns_true_when_remaining_time_exceeds_threshold(self) -> None:
        authorization = make_authorization(
            expire_at=NOW + TOKEN_EXPIRE_SECONDS_LEAST + 1
        )

        self.assertTrue(authorization.valid_access_token())

    def test_returns_false_when_remaining_time_equals_threshold(self) -> None:
        authorization = make_authorization(expire_at=NOW + TOKEN_EXPIRE_SECONDS_LEAST)

        self.assertFalse(authorization.valid_access_token())

    def test_returns_false_when_token_is_expired(self) -> None:
        authorization = make_authorization(expire_at=NOW - 1)

        self.assertFalse(authorization.valid_access_token())


class ValidRefreshTokenTest(SpoonAuthorizationTestBase):
    def test_returns_true_when_remaining_time_exceeds_threshold(self) -> None:
        authorization = make_authorization(
            refresh_expire_at=NOW + REFRESH_TOKEN_EXPIRE_SECONDS_LEAST + 1
        )

        self.assertTrue(authorization.valid_refresh_token())

    def test_returns_false_when_remaining_time_equals_threshold(self) -> None:
        authorization = make_authorization(
            refresh_expire_at=NOW + REFRESH_TOKEN_EXPIRE_SECONDS_LEAST
        )

        self.assertFalse(authorization.valid_refresh_token())

    def test_returns_false_when_refresh_token_is_expired(self) -> None:
        authorization = make_authorization(refresh_expire_at=NOW - 1)

        self.assertFalse(authorization.valid_refresh_token())


class EndRefreshTokenTest(SpoonAuthorizationTestBase):
    def test_returns_true_when_remaining_time_equals_threshold(self) -> None:
        authorization = make_authorization(
            refresh_expire_at=NOW + END_REFRESH_TOKEN_SECONDS
        )

        self.assertTrue(authorization.end_refresh_token())

    def test_returns_false_when_remaining_time_exceeds_threshold(self) -> None:
        authorization = make_authorization(
            refresh_expire_at=NOW + END_REFRESH_TOKEN_SECONDS + 1
        )

        self.assertFalse(authorization.end_refresh_token())

    def test_returns_true_when_refresh_token_is_expired(self) -> None:
        authorization = make_authorization(refresh_expire_at=NOW - 1)

        self.assertTrue(authorization.end_refresh_token())


if __name__ == "__main__":
    unittest.main()
