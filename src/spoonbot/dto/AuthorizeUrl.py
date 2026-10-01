from dataclasses import dataclass


@dataclass
class AuthorizeUrl():
    def __init__(self, url: str, state: str) -> None:
        self.url = url
        self.state = state