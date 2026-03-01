"""
CRCON API wrapper module for Hell Let Loose server communication.
"""
from datetime import datetime, timezone
import requests
from .shared import logger

logger = logger('crcon_api')


class CRCONApi:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def _build_headers(self, content_type: str = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def get_detailed_players(self) -> dict:
        """Hole alle aktuellen Spieler vom Server.

        Returns:
            dict: Dictionary mit player_id als Key und Spielerdaten als Value
        """
        url = f"{self.base_url}/get_detailed_players"

        response = requests.get(url, headers=self._build_headers())
        response.raise_for_status()

        data = response.json()
        players = data.get("result", {}).get("players", {})

        return players

    def get_historical_logs(self, from_datetime: datetime, action: str = "CHAT",
                           exact_action: bool = False) -> list[dict]:
        """Hole historische Logs vom Server.

        Args:
            from_datetime: Startzeit für Logs
            action: Log-Action-Type (default: CHAT)
            exact_action: Ob exakte Action-Übereinstimmung erforderlich ist

        Returns:
            list[dict]: Liste von Log-Einträgen
        """
        url = f"{self.base_url}/get_historical_logs"

        # Konvertiere zu UTC
        from_utc = from_datetime.astimezone(timezone.utc)

        params = {
            "from_": from_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "exact_action": str(exact_action).lower()
        }

        response = requests.get(url, params=params, headers=self._build_headers())
        response.raise_for_status()

        data = response.json()
        return data.get("result", [])

    def message_player(self, player_id: str, message: str) -> None:
        """Sends the message to the player"""
        url = f"{self.base_url}/message_player"
        payload = {
            "player_id": player_id,
            "message": message,
            "by": "hll-language-skill-check"
        }

        response = requests.post(url, headers=self._build_headers("application/json"),
                                 json=payload)
        response.raise_for_status()
        logger.debug(f"Sent message to player {player_id}")

    def kick_player(self, player_id: str, reason: str) -> None:
        """Kick a player from the server."""
        url = f"{self.base_url}/kick"
        payload = {
            "player_id": player_id,
            "reason": reason,
            "by": "hll-language-skill-check"
        }

        response = requests.post(url, headers=self._build_headers("application/json"), json=payload)
        response.raise_for_status()
        logger.debug(f"Kicked player {player_id}")

    def punish_player(self, player_id: str, reason: str) -> None:
        """Punish a player (kills them)."""
        url = f"{self.base_url}/punish"
        payload = {
            "player_id": player_id,
            "reason": reason,
            "by": "hll-language-skill-check"
        }

        response = requests.post(url, headers=self._build_headers("application/json"), json=payload)
        response.raise_for_status()
        logger.debug(f"Punished player {player_id}")

    def add_flag_to_player(self, player_id: str, flag: str, comment: str = None) -> None:
        """Add a flag to a player.

        Args:
            player_id: Player ID
            flag: Flag content (e.g. Unicode emoji like 🇩🇪)
            comment: Optional - Comment for the flag
        """
        url = f"{self.base_url}/flag_player"
        payload = {
            "player_id": player_id,
            "flag": flag
        }
        if comment:
            payload["comment"] = comment

        response = requests.post(
            url,
            headers=self._build_headers("application/json"),
            json=payload
        )
        response.raise_for_status()
        logger.debug(f"Added flag {flag} to player {player_id}")

