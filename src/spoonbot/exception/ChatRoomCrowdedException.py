class ChatRoomCrowdedException(Exception):
    def __init__(self):
        super().__init__("""The message could not be sent because too many messages were being sent in the chat room at once.
Hint: This does not mean the bot itself is sending too many messages. It means the total number of comments posted by all listeners, managers, and DJs in the room, including the bot, has exceeded the limit within a certain period.
                         """)  # noqa: E501
