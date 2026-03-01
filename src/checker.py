from datetime import datetime, timedelta
import time
import random
import os
from requests import HTTPError
from shared.config import Server, PlayerCheck, Word
from shared.shared import logger

logger = logger('checker')


class Checker:
    def __init__(self, servers: list[Server], words: list[Word]):
        self.servers = servers
        self.started_checks : dict[str, PlayerCheck] = {}
        self.last_check : datetime|None = None
        self.words : list[Word] = words
        self.language_skill_checked_flag = os.getenv('LANGUAGE_SKILL_CHECKED_FLAG')
        self.action_after_minutes = int(os.getenv('ACTION_AFTER_MINUTES', '2'))
        self.grace_period_minutes = int(os.getenv('GRACE_PERIOD_MINUTES', '1'))
        self.max_question_changes = int(os.getenv('MAX_QUESTION_CHANGES', '1'))
        self.other_question_keyword = os.getenv('OTHER_QUESTION_KEYWORD', 'hll-language-skill-check').lower()
        self.question_message = os.getenv('QUESTION_MESSAGE', '{word_description}')
        self.punish_message = os.getenv('PUNISH_MESSAGE', '{word_description}')
        self.kick_message = os.getenv('KICK_MESSAGE', 'hll-language-skill-check')

        if not self.language_skill_checked_flag:
            raise RuntimeError('LANGUAGE_SKILL_CHECKED_FLAG not set in environment variables')

    def run(self):
        while True:
            previous_check = self.last_check
            self.last_check = datetime.now()

            total_players = 0
            players_without_flag = 0
            confirmed_players = 0

            for server in self.servers:
                logger.debug(f"Checking server {server.api_base_url}")

                current_players = server.api.get_detailed_players()
                total_players += len(current_players)

                logs_by_player = self._fetch_logs(server, previous_check)

                for player_id, player_data in current_players.items():
                    result = self._process_player(server, player_id, player_data, previous_check, logs_by_player.get(player_id, []))
                    if result == "no_flag":
                        players_without_flag += 1
                    elif result == "confirmed":
                        confirmed_players += 1

            # Ein zusammenfassendes Info-Log pro Zyklus
            logger.info(f"Cycle complete - Players: {total_players}, Without flag: {players_without_flag}, "
                       f"Confirmed: {confirmed_players}, Open checks: {len(self.started_checks)}")

            logger.debug("Waiting 30 seconds before next check...")
            time.sleep(30)

    def _process_player(self, server: Server, player_id: str, player_data: dict, previous_check: datetime|None, logs: list[dict]):
        """Verarbeite einen einzelnen Spieler. Gibt Status zurück: 'has_flag', 'no_flag', 'confirmed'"""
        player_name = player_data.get("name", "Unknown")
        logger.debug(f"Checking player {player_name} ({player_id})")
        profile = player_data.get("profile", {})

        # Prüfe ob Spieler bereits das Flag hat
        flags = profile.get("flags", [])
        has_checked_flag = any(
            flag.get("flag") == self.language_skill_checked_flag
            for flag in flags
        )

        if has_checked_flag:
            logger.debug(f"Player {player_id} already has language skill checked flag")
            return "has_flag"

        if player_id in self.started_checks:
            return self._check_existing_player(server, player_id, player_data, previous_check, logs)
        else:
            self._start_new_check(server, player_id, player_data)
            return "no_flag"

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
        player_check.question_changes_remaining = self.max_question_changes

        # Sende Nachricht an Spieler
        message = self.question_message.format(
            word_description=player_check.word.description,
            other_question_keyword=self.other_question_keyword,
            question_changes_remaining=player_check.question_changes_remaining
        )
        server.api.message_player(player_id, message)

        # Speichere in started_checks
        self.started_checks[player_id] = player_check
        logger.debug(f"Started language check for player {player_name} ({player_id}): {word.description}")

    def _check_existing_player(self, server: Server, player_id: str, player_data: dict, previous_check: datetime|None, logs: list[dict]):
        """Check a player with an ongoing verification."""
        player_check = self.started_checks[player_id]

        # Check chat logs for correct answers or question change requests
        for log in logs:
            message = log.get("content", "").lower()

            # Check if player requests another question
            if self.other_question_keyword in message:
                if player_check.question_changes_remaining > 0:
                    player_check.question_changes_remaining -= 1

                    # Select new question (exclude current word)
                    available_words = [w for w in self.words if w.description != player_check.word.description]
                    if not available_words:
                        # Fallback if only one word exists
                        available_words = self.words
                    new_word = random.choice(available_words)
                    player_check.word = new_word
                    player_check.requested_on = datetime.now()

                    # Send new question
                    message_text = self.question_message.format(
                        word_description=player_check.word.description,
                        other_question_keyword=self.other_question_keyword,
                        question_changes_remaining=player_check.question_changes_remaining
                    )
                    server.api.message_player(player_id, message_text)

                    logger.info(f"Player {player_check.name} ({player_id}) requested new question. "
                               f"Remaining changes: {player_check.question_changes_remaining}")
                    return
                else:
                    logger.debug(f"Player {player_check.name} ({player_id}) tried to change question but no changes remaining")

            # Check against all possible matches
            for match in player_check.word.matches:
                if match.lower() in message:
                    logger.info(f"Player {player_check.name} ({player_id}) answered correctly: {message}")
                    # Set flag
                    server.api.add_flag_to_player(
                        player_id,
                        self.language_skill_checked_flag,
                        f"Language check passed: {player_check.word.description}"
                    )
                    # Remove from started_checks
                    del self.started_checks[player_id]
                    return

        # No correct answer found
        time_elapsed = datetime.now() - player_check.requested_on
        logger.debug(f"Player {player_check.name} ({player_id}) no correct answer. "
                    f"Time elapsed: {int(time_elapsed.total_seconds() / 60)} minutes")

        # Wait during grace period
        if time_elapsed < timedelta(minutes=self.grace_period_minutes):
            return
        # Kick after total time expired
        elif time_elapsed >= timedelta(minutes=self.action_after_minutes):
            logger.info(f"Kicking player {player_check.name} ({player_id}) for exceeding time limit")
            server.api.kick_player(player_id, self.kick_message)
            del self.started_checks[player_id]
        # Punish with message (the message serves as reminder)
        else:
            logger.info(f"Punishing player {player_check.name} ({player_id}) for not answering")
            punish_msg = self.punish_message.format(
                word_description=player_check.word.description,
                other_question_keyword=self.other_question_keyword,
                question_changes_remaining=player_check.question_changes_remaining
            )
            # Punishing will fail if the player isn't alive, we send them a message instead
            try:
                server.api.punish_player(player_id, punish_msg)
            except HTTPError as e:
                server.api.message_player(player_id, punish_msg)



    def _fetch_logs(self, server: Server, since: datetime|None) -> dict:
        """Fetch chat logs and group them by player ID."""
        if not since:
            return {}

        logs = server.api.get_historical_logs(since, action="CHAT", exact_action=False)

        # Group logs by player_id
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
