from datetime import datetime
from .shared import Printable
from .crcon_api import CRCONApi


class Server(Printable):
    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url: str = api_base_url
        self.api_key: str = api_key
        self.api: CRCONApi = CRCONApi(api_base_url, api_key)

class Word(Printable):
    def __init__(self, description: str, matches: list[str]):
        self.description: str = description
        self.matches: list[str] = matches

class PlayerSkillCheck(Printable):
    def __init__(self, name: str, player_id: str, requested_on: datetime, word: Word):
        self.name: str = name
        self.player_id: str = player_id
        self.requested_on: datetime = requested_on
        self.word: Word = word
        self.question_changes_remaining: int = 2
