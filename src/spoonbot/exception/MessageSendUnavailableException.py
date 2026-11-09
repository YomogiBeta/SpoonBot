class MessageSendUnavailableException(Exception):
    def __init__(self):
        super().__init__(
            """The chat is frozen, or the bot is prohibited from sending messages in the chat."""  # noqa: E501
        )
