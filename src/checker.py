from datetime import datetime, timedelta
import time
import random
import os

from shared.config import Server, PlayerCheck, Word
from shared.shared import logger

logger = logger('publisher')


class Checker:
    def __init__(self, servers: list[Server], words: list[Word]):
        self.servers = servers
        self.started_checks : dict[str, PlayerCheck] = {}
        self.last_check : datetime|None = None
        self.words : list[Word] = words
        self.language_skill_checked_flag = os.getenv('LANGUAGE_SKILL_CHECKED_FLAG')
        self.action_after_minutes = int(os.getenv('ACTION_AFTER_MINUTES', '5'))

        if not self.language_skill_checked_flag:
            raise RuntimeError('LANGUAGE_SKILL_CHECKED_FLAG not set in environment variables')

    def run(self):
        while True:
            previous_check = self.last_check
            self.last_check = datetime.now()

            for server in self.servers:
                logger.info(f"checking {server.api_base_url}")

                current_players = server.api.get_detailed_players()

                logs_by_player = self._fetch_logs(server, previous_check)

                for player_id, player_data in current_players.items():
                    self._process_player(server, player_id, player_data, previous_check, logs_by_player.get(player_id, []))

            logger.info("Waiting 30 seconds before next check...")
            time.sleep(30)

    def _process_player(self, server: Server, player_id: str, player_data: dict, previous_check: datetime|None, logs: list[dict]):
        """Verarbeite einen einzelnen Spieler."""
        logger.info(f"Checking player {player_data.get("name", "Unknown")} ({player_id})")
        profile = player_data.get("profile", {})

        # Prüfe ob Spieler bereits das Flag hat
        flags = profile.get("flags", [])
        has_checked_flag = any(
            flag.get("flag") == self.language_skill_checked_flag
            for flag in flags
        )

        if has_checked_flag:
            logger.info(f"Player {player_id} already has language skill checked flag")
            return

        if player_id in self.started_checks:
            self._check_existing_player(server, player_id, player_data, previous_check, logs)
        else:
            self._start_new_check(server, player_id, player_data)

    def _start_new_check(self, server: Server, player_id: str, player_data: dict):
        """Starte eine neue Überprüfung für einen Spieler."""
        if not self.words:
            logger.warning("No words available to check")
            return

        # Wähle zufälliges Wort
        word = random.choice(self.words)

        # Erstelle PlayerCheck
        player_name = player_data.get("name", "Unknown")
        player_check = PlayerCheck(
            name=player_name,
            id=player_id,
            requested_on=datetime.now(),
            word=word
        )

        # Sende Nachricht an Spieler
        message = f"Beantworte die folgende Frage im Chat: {word.description}"
        server.api.message_player(player_id, message)

        # Speichere in started_checks
        self.started_checks[player_id] = player_check
        logger.info(f"Started language check for player {player_name} ({player_id})")

    def _check_existing_player(self, server: Server, player_id: str, player_data: dict, previous_check: datetime|None, logs: list[dict]):
        """Überprüfe einen Spieler mit laufender Überprüfung."""
        player_check = self.started_checks[player_id]

        # Prüfe, ob eine Nachricht ein Match enthält
        for log in logs:
            message = log.get("content", "").lower()
            # Prüfe gegen alle möglichen Matches
            for match in player_check.word.matches:
                if match.lower() in message:
                    logger.info(f"Player {player_check.name} ({player_id}) answered correctly: {message}")
                    # Setze Flag
                    server.api.add_flag_to_player(
                        player_id,
                        self.language_skill_checked_flag,
                        f"Language check passed: {player_check.word.description}"
                    )
                    # Entferne aus started_checks
                    del self.started_checks[player_id]
                    return

        logger.info(f"Player {player_check.name} ({player_id}) no answer in this cycle: \"{player_check.word.description}\": {', '.join(player_check.word.matches)}")

        # Keine richtige Antwort gefunden - prüfe Zeitlimit
        time_elapsed = datetime.now() - player_check.requested_on
        if time_elapsed > timedelta(minutes=self.action_after_minutes):
            logger.info(f"Player {player_check.name} ({player_id}) exceeded time limit, kicking")
            kick_message = f"Du wurdest gekickt, weil du die Frage nicht innerhalb von {self.action_after_minutes} Minuten beantwortet hast."
            server.api.kick_player(player_id, kick_message)
            # Entferne aus started_checks
            del self.started_checks[player_id]


    def _fetch_logs(self, server: Server, since: datetime|None) -> dict:
        """Hole Chat-Logs und gruppiere sie nach Spieler-ID."""
        if not since:
            return {}

        logs = server.api.get_historical_logs(since, action="CHAT", exact_action=False)

        # Gruppiere Logs nach player_id
        logs_by_player = {}
        for message_log in logs:
            player_id = message_log.get("player1_id")
            if player_id:
                if player_id not in logs_by_player:
                    logs_by_player[player_id] = []
                logs_by_player[player_id].append(message_log)

        return logs_by_player


def invoke(servers: list[Server], words: list[Word]):
    try:
        Checker(servers, words).run()
    except BaseException as exception:
        logger.exception(exception)
