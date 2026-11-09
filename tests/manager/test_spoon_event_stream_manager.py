import json
import unittest
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Self, cast
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import (
    ClientResponseError,
)

from spoonbot.dto.event.ChatEvent import ChatEvent
from spoonbot.dto.event.DonationEvent import GiftEvent
from spoonbot.dto.event.EndEvent import EndEvent
from spoonbot.dto.event.FollowEvent import FollowEvent
from spoonbot.dto.event.JoinEvent import JoinEvent
from spoonbot.dto.event.LikeEvent import LikeEvent
from spoonbot.dto.PresenceBody import PresenceType
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization
from spoonbot.enums.TokenStatus import TokenStatus
from spoonbot.exception.BackoffRetryException import BackoffRetryException
from spoonbot.exception.NonBackoffRetryException import NonBackoffRetryException
from spoonbot.exception.NonRetryException import NonRetryException
from spoonbot.exception.TokenRefreshException import TokenRefreshException
from spoonbot.httpclient.SpoonApiClient import SpoonApiClient
from spoonbot.manager.SpoonEventStreamManager import (
    SpoonEventStreamManager,
    logger,
)
from spoonbot.spoon_bot import SpoonBot

NOW = 4_000_000_000

CHAT_PAYLOAD = {
    "user": {"id": "user-1", "nickname": "spoon"},
    "isDj": False,
    "message": "hello",
    "sentTime": "2026-01-01T00:00:00Z",
}
PRESENCE_PAYLOAD = {
    "user": {"id": "user-1", "nickname": "spoon"},
    "type": "JOIN",
    "fanRank": None,
    "isManager": False,
    "favoriteTemperature": None,
    "time": "2026-01-01T00:00:00Z",
}
LIKE_PAYLOAD = {
    "user": {"id": "user-1", "nickname": "spoon"},
    "type": "FREE",
    "totalAmount": 10,
    "amount": 1,
    "extraAmount": 0,
    "combo": None,
    "time": "2026-01-01T00:00:00Z",
}
DONATION_PAYLOAD = {
    "user": {"id": "user-1", "nickname": "spoon"},
    "amount": 100,
    "message": "thank you",
    "time": "2026-01-01T00:00:00Z",
}
FOLLOW_PAYLOAD = {
    "user": {"id": "user-1", "nickname": "spoon"},
    "time": "2026-01-01T00:00:00Z",
}


def make_authorization(
    authorization_id: str = "user-1",
    expire_at: int = NOW + 100_000,
    refresh_expire_at: int = NOW + 1_000_000,
) -> SpoonAuthorization:
    return SpoonAuthorization(
        id=authorization_id,
        access_token="access-token",
        token_type="Bearer",
        expire_at=expire_at,
        refresh_expire_at=refresh_expire_at,
        refresh_token="refresh-token",
        scope="scope",
        token_status=TokenStatus.DEFAULT,
    )


@dataclass
class FakeEvent:
    type: str
    data: str


class FakeEventSource:
    def __init__(self, events: list[FakeEvent]) -> None:
        self.events = events

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    def __aiter__(self) -> AsyncIterator[FakeEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[FakeEvent]:
        for event in self.events:
            yield event


class FakeApiClient:
    def __init__(self, event_source: FakeEventSource) -> None:
        self.event_source = event_source
        self.stream_calls: list[SpoonAuthorization] = []

    def stream_live(self, authorization: SpoonAuthorization) -> FakeEventSource:
        self.stream_calls.append(authorization)
        return self.event_source


class FakeSpoonBot:
    def __init__(self, refreshed: SpoonAuthorization) -> None:
        self.refreshed = refreshed
        self.get_calls: list[SpoonAuthorization] = []
        self.save_calls: list[tuple[SpoonAuthorization, bool]] = []

    async def get_authorization_by_refresh_token(
        self, authorization: SpoonAuthorization
    ) -> SpoonAuthorization:
        self.get_calls.append(authorization)
        return self.refreshed

    async def save_authorization(
        self, authorization: SpoonAuthorization, force: bool = False
    ) -> None:
        self.save_calls.append((authorization, force))


class SpoonEventStreamManagerTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.manager = SpoonEventStreamManager()
        self.manager.tasks = {}
        self.manager.chat_callbacks = []
        self.manager.presence_callbacks = []
        self.manager.like_callbacks = []
        self.manager.donation_callbacks = []
        self.manager.follow_callbacks = []
        self.manager.end_callbacks = []
        self.api_client = FakeApiClient(FakeEventSource([]))
        self.manager.api_client = cast(SpoonApiClient, self.api_client)


class InitTest(SpoonEventStreamManagerTestBase):
    async def test_init_stores_dependencies(self) -> None:
        app = MagicMock()
        api_client = MagicMock()
        spoon_bot = MagicMock()

        await self.manager.init(app, api_client, spoon_bot)

        self.assertIs(self.manager.app, app)
        self.assertIs(self.manager.api_client, api_client)
        self.assertIs(self.manager.spoon_bot, spoon_bot)


class AddConnectionTest(SpoonEventStreamManagerTestBase):
    async def test_add_connection_creates_and_stores_task(self) -> None:
        authorization = make_authorization()

        with patch.object(
            self.manager,
            "_stream",
            new=AsyncMock(side_effect=NonRetryException()),
        ):
            result = await self.manager.add_connection(authorization)
            task = self.manager.tasks[authorization.id]
            await task

        self.assertTrue(result)
        self.assertNotIn(authorization.id, self.manager.tasks)

    async def test_add_connection_returns_false_for_existing_connection(
        self,
    ) -> None:
        authorization = make_authorization()
        existing_task = MagicMock()
        self.manager.tasks[authorization.id] = existing_task

        result = await self.manager.add_connection(authorization)

        self.assertFalse(result)
        self.assertIs(self.manager.tasks[authorization.id], existing_task)


class RemoveConnectionTest(SpoonEventStreamManagerTestBase):
    async def test_remove_connection_cancels_task(self) -> None:
        task = MagicMock()
        self.manager.tasks["user-1"] = task

        await self.manager.remove_connection("user-1")

        task.cancel.assert_called_once_with()

    async def test_remove_connection_ignores_unknown_id(self) -> None:
        await self.manager.remove_connection("unknown")


class CallbackAppendTest(SpoonEventStreamManagerTestBase):
    def test_callback_append_adds_to_matching_list(self) -> None:
        cases = [
            ("chat_callback_append", "chat_callbacks"),
            ("presence_callback_append", "presence_callbacks"),
            ("like_callback_append", "like_callbacks"),
            ("donation_callback_append", "donation_callbacks"),
            ("follow_callback_append", "follow_callbacks"),
            ("end_callback_append", "end_callbacks"),
        ]

        for method_name, list_name in cases:
            with self.subTest(method_name=method_name):
                callback = MagicMock()
                getattr(self.manager, method_name)(callback)
                self.assertIn(callback, getattr(self.manager, list_name))


class ChatProcessTest(SpoonEventStreamManagerTestBase):
    async def test_chat_process_builds_event_and_invokes_callbacks(self) -> None:
        authorization = make_authorization()
        received: list[ChatEvent] = []

        def on_chat(event: ChatEvent) -> None:
            received.append(event)

        async_callback: Any = AsyncMock()
        self.manager.chat_callbacks = [on_chat, async_callback]

        await self.manager.chat_process(CHAT_PAYLOAD, authorization)

        self.assertEqual(len(received), 1)
        event = received[0]
        self.assertEqual(event.chat_body.message, "hello")
        self.assertEqual(event.chat_body.user.id, "user-1")
        self.assertIs(event.authorization, authorization)
        async_callback.assert_awaited_once_with(event)


class PresenceProcessTest(SpoonEventStreamManagerTestBase):
    async def test_presence_process_builds_event_and_invokes_callbacks(
        self,
    ) -> None:
        authorization = make_authorization()
        received: list[JoinEvent] = []

        def on_presence(event: JoinEvent) -> None:
            received.append(event)

        async_callback: Any = AsyncMock()
        self.manager.presence_callbacks = [on_presence, async_callback]

        await self.manager.presence_process(PRESENCE_PAYLOAD, authorization)

        self.assertEqual(len(received), 1)
        event = received[0]
        self.assertIs(event.presence_body.type, PresenceType.JOIN)
        self.assertEqual(event.presence_body.user.id, "user-1")
        self.assertIs(event.authorization, authorization)
        async_callback.assert_awaited_once_with(event)


class LikeProcessTest(SpoonEventStreamManagerTestBase):
    async def test_like_process_builds_event_and_invokes_callbacks(self) -> None:
        authorization = make_authorization()
        received: list[LikeEvent] = []

        def on_like(event: LikeEvent) -> None:
            received.append(event)

        async_callback: Any = AsyncMock()
        self.manager.like_callbacks = [on_like, async_callback]

        await self.manager.like_process(LIKE_PAYLOAD, authorization)

        self.assertEqual(len(received), 1)
        event = received[0]
        self.assertEqual(event.like_body.amount, 1)
        self.assertEqual(event.like_body.user.id, "user-1")
        self.assertIs(event.authorization, authorization)
        async_callback.assert_awaited_once_with(event)


class DonationProcessTest(SpoonEventStreamManagerTestBase):
    async def test_donation_process_builds_event_and_invokes_callbacks(
        self,
    ) -> None:
        authorization = make_authorization()
        received: list[GiftEvent] = []

        def on_donation(event: GiftEvent) -> None:
            received.append(event)

        async_callback: Any = AsyncMock()
        self.manager.donation_callbacks = [on_donation, async_callback]

        await self.manager.donation_process(DONATION_PAYLOAD, authorization)

        self.assertEqual(len(received), 1)
        event = received[0]
        self.assertEqual(event.donation_body.amount, 100)
        self.assertEqual(event.donation_body.user.id, "user-1")
        self.assertIs(event.authorization, authorization)
        async_callback.assert_awaited_once_with(event)


class FollowProcessTest(SpoonEventStreamManagerTestBase):
    async def test_follow_process_builds_event_and_invokes_callbacks(
        self,
    ) -> None:
        authorization = make_authorization()
        received: list[FollowEvent] = []

        def on_follow(event: FollowEvent) -> None:
            received.append(event)

        async_callback: Any = AsyncMock()
        self.manager.follow_callbacks = [on_follow, async_callback]

        await self.manager.follow_process(FOLLOW_PAYLOAD, authorization)

        self.assertEqual(len(received), 1)
        event = received[0]
        self.assertEqual(event.follow_body.user.id, "user-1")
        self.assertIs(event.authorization, authorization)
        async_callback.assert_awaited_once_with(event)


class StreamTest(SpoonEventStreamManagerTestBase):
    async def test_stream_dispatches_events_to_processors(self) -> None:
        authorization = make_authorization()
        events = [
            FakeEvent("CHAT", json.dumps(CHAT_PAYLOAD)),
            FakeEvent("presence", json.dumps(PRESENCE_PAYLOAD)),
            FakeEvent("LIKE", json.dumps(LIKE_PAYLOAD)),
            FakeEvent("donation", json.dumps(DONATION_PAYLOAD)),
            FakeEvent("FOLLOW", json.dumps(FOLLOW_PAYLOAD)),
            FakeEvent("end", json.dumps({"reason": "RECONNECT"})),
            FakeEvent("unknown", "{}"),
        ]
        self.api_client.event_source = FakeEventSource(events)

        with (
            patch.object(self.manager, "chat_process", new=AsyncMock()) as chat_process,
            patch.object(
                self.manager, "presence_process", new=AsyncMock()
            ) as presence_process,
            patch.object(self.manager, "like_process", new=AsyncMock()) as like_process,
            patch.object(
                self.manager, "donation_process", new=AsyncMock()
            ) as donation_process,
            patch.object(
                self.manager, "follow_process", new=AsyncMock()
            ) as follow_process,
            patch.object(self.manager, "end_process", new=AsyncMock()) as end_process,
        ):
            await self.manager._stream(authorization)

        self.assertEqual(self.api_client.stream_calls, [authorization])
        chat_process.assert_awaited_once_with(CHAT_PAYLOAD, authorization)
        presence_process.assert_awaited_once_with(PRESENCE_PAYLOAD, authorization)
        like_process.assert_awaited_once_with(LIKE_PAYLOAD, authorization)
        donation_process.assert_awaited_once_with(DONATION_PAYLOAD, authorization)
        follow_process.assert_awaited_once_with(FOLLOW_PAYLOAD, authorization)
        end_process.assert_awaited_once_with({"reason": "RECONNECT"})

    async def test_stream_continues_after_forbidden_response_error(
        self,
    ) -> None:
        authorization = make_authorization()
        self.api_client.event_source = FakeEventSource(
            [
                FakeEvent("chat", "{}"),
                FakeEvent("chat", "{}"),
            ]
        )
        forbidden = ClientResponseError(
            cast(Any, None), (), status=403, message="forbidden"
        )

        with (
            patch.object(
                self.manager,
                "chat_process",
                new=AsyncMock(side_effect=[forbidden, None]),
            ) as chat_process,
            patch.object(logger, "warning") as warning,
        ):
            await self.manager._stream(authorization)

        self.assertEqual(chat_process.await_count, 2)
        warning.assert_called_once_with("forbidden")

    async def test_stream_reraises_non_forbidden_response_error(self) -> None:
        authorization = make_authorization()
        self.api_client.event_source = FakeEventSource([FakeEvent("chat", "{}")])
        error = ClientResponseError(
            cast(Any, None), (), status=500, message="server error"
        )

        with (
            patch.object(
                self.manager, "chat_process", new=AsyncMock(side_effect=error)
            ),
            self.assertRaises(ClientResponseError),
        ):
            await self.manager._stream(authorization)


class EndProcessTest(SpoonEventStreamManagerTestBase):
    async def test_end_process_raises_expected_exceptions(self) -> None:
        cases = [
            ("TOKEN_EXPIRED", TokenRefreshException),
            ("LIVE_ENDED", NonRetryException),
            ("DUPLICATE_CONNECTION", NonRetryException),
            ("RECONNECT", NonBackoffRetryException),
        ]

        for reason, exception_type in cases:
            with (
                self.subTest(reason=reason),
                self.assertRaises(exception_type),
            ):
                await self.manager.end_process({"reason": reason})

    async def test_end_process_ignores_unknown_reason(self) -> None:
        await self.manager.end_process({"reason": "UNKNOWN"})

    async def test_end_process_ignores_non_string_reason(self) -> None:
        await self.manager.end_process({"reason": 1})


class RefreshTokenTest(SpoonEventStreamManagerTestBase):
    async def test_refresh_token_saves_and_returns_new_authorization(
        self,
    ) -> None:
        authorization = make_authorization()
        refreshed = make_authorization(authorization_id="user-2")
        spoon_bot = FakeSpoonBot(refreshed)
        self.manager.spoon_bot = cast(SpoonBot, spoon_bot)

        result = await self.manager._refresh_token(authorization)

        self.assertIs(result, refreshed)
        self.assertEqual(spoon_bot.get_calls, [authorization])
        self.assertEqual(spoon_bot.save_calls, [(refreshed, True)])


class DoTaskTest(SpoonEventStreamManagerTestBase):
    async def test_do_task_streams_and_runs_end_callbacks(self) -> None:
        authorization = make_authorization()
        self.manager.tasks[authorization.id] = MagicMock()
        received: list[EndEvent] = []

        def on_end(event: EndEvent) -> None:
            received.append(event)

        async_callback: Any = AsyncMock()
        self.manager.end_callbacks = [on_end, async_callback]

        with patch.object(
            self.manager,
            "_stream",
            new=AsyncMock(side_effect=NonRetryException()),
        ) as stream:
            await self.manager._do_task(authorization)

        stream.assert_awaited_once_with(authorization)
        self.assertEqual(len(received), 1)
        self.assertIs(received[0].authorization, authorization)
        async_callback.assert_awaited_once_with(received[0])
        self.assertNotIn(authorization.id, self.manager.tasks)

    async def test_do_task_refreshes_invalid_tokens_before_streaming(
        self,
    ) -> None:
        expired = make_authorization(expire_at=0, refresh_expire_at=0)
        refreshed = make_authorization()
        spoon_bot = FakeSpoonBot(refreshed)
        self.manager.spoon_bot = cast(SpoonBot, spoon_bot)

        with patch.object(
            self.manager,
            "_stream",
            new=AsyncMock(side_effect=NonRetryException()),
        ) as stream:
            await self.manager._do_task(expired)

        self.assertEqual(spoon_bot.get_calls, [expired])
        stream.assert_awaited_once_with(refreshed)

    async def test_do_task_refreshes_after_token_refresh_exception(
        self,
    ) -> None:
        authorization = make_authorization()
        refreshed = make_authorization(authorization_id="user-2")
        spoon_bot = FakeSpoonBot(refreshed)
        self.manager.spoon_bot = cast(SpoonBot, spoon_bot)

        with patch.object(
            self.manager,
            "_stream",
            new=AsyncMock(side_effect=[TokenRefreshException(), NonRetryException()]),
        ) as stream:
            await self.manager._do_task(authorization)

        self.assertEqual(spoon_bot.get_calls, [authorization])
        self.assertEqual(
            [call.args[0] for call in stream.await_args_list],
            [authorization, refreshed],
        )

    async def test_do_task_backs_off_on_backoff_retry_exception(self) -> None:
        authorization = make_authorization()

        with (
            patch.object(
                self.manager,
                "_stream",
                new=AsyncMock(
                    side_effect=[
                        BackoffRetryException(),
                        NonRetryException(),
                    ]
                ),
            ) as stream,
            patch(
                "spoonbot.manager.SpoonEventStreamManager.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
        ):
            await self.manager._do_task(authorization)

        sleep.assert_awaited_once()
        self.assertEqual(stream.await_count, 2)

    async def test_do_task_retries_without_backoff_on_non_backoff_exception(
        self,
    ) -> None:
        authorization = make_authorization()

        with (
            patch.object(
                self.manager,
                "_stream",
                new=AsyncMock(
                    side_effect=[
                        NonBackoffRetryException(),
                        NonRetryException(),
                    ]
                ),
            ) as stream,
            patch(
                "spoonbot.manager.SpoonEventStreamManager.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
        ):
            await self.manager._do_task(authorization)

        sleep.assert_not_awaited()
        self.assertEqual(stream.await_count, 2)

    async def test_do_task_backs_off_on_target_http_status(self) -> None:
        authorization = make_authorization()
        error = ClientResponseError(
            cast(Any, None), (), status=500, message="server error"
        )

        with (
            patch.object(
                self.manager,
                "_stream",
                new=AsyncMock(side_effect=[error, NonRetryException()]),
            ) as stream,
            patch(
                "spoonbot.manager.SpoonEventStreamManager.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
        ):
            await self.manager._do_task(authorization)

        sleep.assert_awaited_once()
        self.assertEqual(stream.await_count, 2)

    async def test_do_task_refreshes_on_unauthorized_response_error(
        self,
    ) -> None:
        authorization = make_authorization()
        refreshed = make_authorization(authorization_id="user-2")
        spoon_bot = FakeSpoonBot(refreshed)
        self.manager.spoon_bot = cast(SpoonBot, spoon_bot)
        error = ClientResponseError(
            cast(Any, None), (), status=401, message="unauthorized"
        )

        with (
            patch.object(self.manager, "_stream", new=AsyncMock(side_effect=error)),
            patch.object(logger, "exception") as log_exception,
        ):
            await self.manager._do_task(authorization)

        self.assertEqual(spoon_bot.get_calls, [authorization])
        log_exception.assert_called_once()

    async def test_do_task_swallows_non_retry_exception(self) -> None:
        authorization = make_authorization()
        end_callback: Any = AsyncMock()
        self.manager.end_callbacks = [end_callback]

        with patch.object(
            self.manager,
            "_stream",
            new=AsyncMock(side_effect=NonRetryException()),
        ):
            await self.manager._do_task(authorization)

        end_callback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
