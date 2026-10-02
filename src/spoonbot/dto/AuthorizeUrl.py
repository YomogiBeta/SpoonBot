from dataclasses import dataclass


@dataclass
class AuthorizeUrl:
    url: str
    state: str
