"""
CRCON API wrapper module for Hell Let Loose server communication.
"""
from datetime import datetime, timezone
import requests
from .shared import logger

logger = logger('crcon_api')


class CRCONApi:
    """Wrapper für CRCON API Aufrufe."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def _get_headers(self, content_type: str = None) -> dict:
        """Erstelle Standard-Headers für API-Anfragen."""
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

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        data = response.json()
        players = data.get("result", {}).get("players", {})

        return players

    def get_historical_logs(self, from_datetime: datetime, action: str = "CHAT",
                           exact_action: bool = False) -> list[dict]:
        """Hole historische Logs vom Server.

        Args:
            from_datetime: Startzeit für Logs (wird zu UTC konvertiert)
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

        response = requests.get(url, params=params, headers=self._get_headers())
        response.raise_for_status()

        data = response.json()
        return data.get("result", [])

    def message_player(self, player_id: str, message: str) -> None:
        """Sende eine Nachricht an einen Spieler.

        Args:
            player_id: ID des Spielers
            message: Nachricht die gesendet werden soll
        """
        url = f"{self.base_url}/message_player"
        payload = {
            "player_id": player_id,
            "message": message
        }

        response = requests.post(url, headers=self._get_headers("application/json"),
                                json=payload)
        response.raise_for_status()
        logger.debug(f"Sent message to player {player_id}")

    def kick_player(self, player_id: str, reason: str) -> None:
        """Kicke einen Spieler vom Server.

        Args:
            player_id: ID des Spielers
            reason: Grund für den Kick
        """
        url = f"{self.base_url}/kick"
        payload = {
            "player_id": player_id,
            "reason": reason,
            "by": "hll-language-skill-check"
        }

        response = requests.post(url, headers=self._get_headers("application/json"), json=payload)
        response.raise_for_status()
        logger.info(f"Kicked player {player_id}")

    def add_flag_to_player(self, player_id: str, flag: str, comment: str = None) -> None:
        """Füge einem Spieler ein Flag hinzu.

        Args:
            player_id: ID des Spielers
            flag: Flag-Content (z.B. Unicode Emoji wie 🇩🇪)
            comment: Optional - Kommentar zum Flag
        """
        url = f"{self.base_url}/flag_player"
        payload = {
            "player_id": player_id,
            "flag": flag
        }
        if comment:
            payload["comment"] = comment

        response = requests.post(url, headers=self._get_headers("application/json"),
                                json=payload)
        response.raise_for_status()
        logger.info(f"Added flag {flag} to player {player_id}")

