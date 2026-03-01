from datetime import datetime, timedelta
import time
import random
import os
from requests import HTTPError
from shared.config import Server, PlayerSkillCheck, Word
from shared.shared import logger, Printable

logger = logger('checker')

class CycleStats(Printable):
    def __init__(self):
        self.total_players = 0
        self.players_without_skill = 0
        self.pending_skill_checks = 0
        self.skill_gained_this_cycle = 0
        self.player_punishes = 0

class Checker:
    def __init__(self, servers: list[Server], words: list[Word]):
        self.servers = servers
        self.pending_skill_checks : dict[str, PlayerSkillCheck] = {}
        self.last_check : datetime|None = None
        self.words : list[Word] = words
        self.language_skill_checked_flag = os.getenv('LANGUAGE_SKILL_CHECKED_FLAG')
        self.action_after_minutes = int(os.getenv('ACTION_AFTER_MINUTES', '2'))
        self.grace_period_minutes = int(os.getenv('GRACE_PERIOD_MINUTES', '1'))
        self.max_question_changes = int(os.getenv('MAX_QUESTION_CHANGES', '1'))
        self.change_question_keyword = os.getenv('CHANGE_QUESTION_KEYWORD', 'hll-language-skill-check').lower()
        self.change_question_message = os.getenv('CHANGE_QUESTION_MESSAGE', 'CHANGE_QUESTION_MESSAGE\n\n{change_question_keyword}').replace('\\n', '\n').replace('\\"', '"')
        self.question_message = os.getenv('QUESTION_MESSAGE', 'QUESTION_MESSAGE\n\n{word_description}').replace('\\n', '\n').replace('\\"', '"')
        self.punish_message = os.getenv('PUNISH_MESSAGE', 'PUNISH_MESSAGE\n\n{word_description}').replace('\\n', '\n').replace('\\"', '"')
        self.kick_message = os.getenv('KICK_MESSAGE', 'KICK_MESSAGE hll-language-skill-check').replace('\\n', '\n').replace('\\"', '"')
        self.stats : CycleStats = CycleStats()

        if not self.language_skill_checked_flag:
            raise RuntimeError('LANGUAGE_SKILL_CHECKED_FLAG not set in environment variables')

    def run(self):
        while True:
            previous_check = self.last_check
            self.last_check = datetime.now()

            self.stats = CycleStats()

            for server in self.servers:
                logger.debug(f"Checking server {server.api_base_url}")

                current_players = server.api.get_detailed_players()
                self.stats.total_players = len(current_players)

                logs_by_player = self._fetch_logs(server, previous_check)

                for player_id, player_data in current_players.items():
                    self._process_player(server, player_id, player_data, logs_by_player.get(player_id, []))

            self.stats.pending_skill_checks = len(self.pending_skill_checks)
            logger.info(f"cycle complete - {self.stats}")

            logger.debug("Waiting 30 seconds before next check...")
            time.sleep(30)

    def _process_player(self, server: Server, player_id: str, player_data: dict, logs: list[dict]):
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
            return

        self.stats.players_without_skill += 1
        if player_id in self.pending_skill_checks:
            self._verify_pending_skill_check(server, player_id, logs)
        else:
            self._start_new_skill_check(server, player_id, player_data)

    def _start_new_skill_check(self, server: Server, player_id: str, player_data: dict):
        if not self.words:
            logger.warning("No words available to check")
            return

        word = random.choice(self.words)

        player_name = player_data.get("name", "Unknown")
        player_check = PlayerSkillCheck(
            name=player_name,
            player_id=player_id,
            requested_on=datetime.now(),
            word=word
        )
        player_check.question_changes_remaining = self.max_question_changes

        message = self.question_message.format(
            word_description=player_check.word.description,
            question_changes_remaining=player_check.question_changes_remaining
        )
        if player_check.question_changes_remaining > 0:
            message += "\n\n\n" + self.change_question_message.format(change_question_keyword=self.change_question_keyword)

        server.api.message_player(player_id, message)

        self.pending_skill_checks[player_id] = player_check

        logger.debug(f"Started language check for player {player_name} ({player_id}): {word.description}")

    def _verify_pending_skill_check(self, server: Server, player_id: str, logs: list[dict]):
        player_check = self.pending_skill_checks[player_id]

        for log in logs:
            message = log.get("content", "").lower()

            # Check if player requests another question
            if self.change_question_keyword in message:
                if player_check.question_changes_remaining > 0:
                    player_check.question_changes_remaining -= 1

                    available_words = [w for w in self.words if w.description != player_check.word.description]
                    new_word = random.choice(available_words)
                    player_check.word = new_word
                    player_check.requested_on = datetime.now()

                    logger.info(f"Player {player_check.name} ({player_id}) requested new question. "
                               f"Remaining changes: {player_check.question_changes_remaining}")

                    message_text = self.question_message.format(
                        word_description=player_check.word.description,
                        question_changes_remaining=player_check.question_changes_remaining
                    )
                    if player_check.question_changes_remaining > 0:
                        message_text += "\n\n\n" + self.change_question_message.format(
                            change_question_keyword=self.change_question_keyword
                        )

                    server.api.message_player(player_id, message_text)
                    return
                # The player can't change their question anymore, so we send the current question again
                else:
                    logger.debug(f"Player {player_check.name} ({player_id}) tried to change question but no changes remaining")
                    message_text = self.question_message.format(
                        word_description=player_check.word.description,
                        question_changes_remaining=player_check.question_changes_remaining
                    )
                    if player_check.question_changes_remaining > 0:
                        message_text += "\n\n\n" + self.change_question_message.format(
                            change_question_keyword=self.change_question_keyword
                        )
                    server.api.message_player(player_id, message_text)

            # Check against all possible matches
            for match in player_check.word.matches:
                if match.lower() in message:
                    logger.info(f"Player {player_check.name} ({player_id}) answered correctly: {message}")

                    server.api.add_flag_to_player(
                        player_id,
                        self.language_skill_checked_flag,
                        f"Language check passed: {player_check.word.description} with answer '{message}' at {datetime.now().isoformat()}"
                    )

                    del self.pending_skill_checks[player_id]
                    self.stats.skill_gained_this_cycle += 1
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
            del self.pending_skill_checks[player_id]
        # Punish with message (the message serves as reminder)
        else:
            logger.info(f"Punishing player {player_check.name} ({player_id}) for not answering")
            # omit the other question part
            punish_msg = self.punish_message.format(
                word_description=player_check.word.description,
                question_changes_remaining=player_check.question_changes_remaining
            )
            # Punishing will fail if the player isn't alive, we send them a message instead
            try:
                server.api.punish_player(player_id, f"\n\n{punish_msg}\n\n")
            except HTTPError as e:
                server.api.message_player(player_id, punish_msg)

            self.stats.player_punishes += 1


    def _fetch_logs(self, server: Server, since: datetime|None) -> dict:
        """Fetch chat logs and group them by player ID."""
        if not since:
            return {}

        logs = server.api.get_historical_logs(since, action="CHAT", exact_action=False)

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
