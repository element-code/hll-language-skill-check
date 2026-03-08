from datetime import datetime, timedelta
import time
import random
import os
import unicodedata
from requests import HTTPError
from shared.config import Server, PlayerSkillCheck, Word
from shared.shared import logger, Printable

logger = logger('checker')

def normalize_german_text(text: str) -> str:
    """Normalize German text for comparison, handling umlauts and their ASCII equivalents."""
    # First normalize Unicode to NFC form
    text = unicodedata.normalize('NFC', text).lower()

    # Replace ASCII equivalents with umlauts
    replacements = {
        'ue': 'ü',
        'ae': 'ä',
        'oe': 'ö',
        'ss': 'ß'
    }

    for ascii_form, umlaut in replacements.items():
        text = text.replace(ascii_form, umlaut)

    return text

class QueuedAction:
    """Base class for queued actions"""
    pass

class QueuedKick(QueuedAction):
    def __init__(self, server: Server, player_id: str, player_name: str, message: str):
        self.server = server
        self.player_id = player_id
        self.player_name = player_name
        self.message = message

class QueuedPunish(QueuedAction):
    def __init__(self, server: Server, player_id: str, player_name: str, message: str):
        self.server = server
        self.player_id = player_id
        self.player_name = player_name
        self.message = message

class QueuedMessage(QueuedAction):
    def __init__(self, server: Server, player_id: str, player_name: str, message: str):
        self.server = server
        self.player_id = player_id
        self.player_name = player_name
        self.message = message

class QueuedFlag(QueuedAction):
    def __init__(self, server: Server, player_id: str, player_name: str, flag: str, comment: str):
        self.server = server
        self.player_id = player_id
        self.player_name = player_name
        self.flag = flag
        self.comment = comment

class CycleStats(Printable):
    def __init__(self):
        self.total_players = 0
        self.unassigned_players_without_skill = 0
        self.assigned_players_without_skill = 0
        self.pending_skill_checks = 0
        self.skill_gained_this_cycle = 0
        self.player_punishes = 0
        self.removed_offline_checks = 0

class Checker:
    def __init__(self, servers: list[Server], words: list[Word]):
        self.servers = servers
        self.pending_skill_checks : dict[str, PlayerSkillCheck] = {}
        self.last_check : datetime|None = None
        self.words : list[Word] = words

        # Action queues
        self.kick_queue: list[QueuedKick] = []
        self.punish_queue: list[QueuedPunish] = []
        self.message_queue: list[QueuedMessage] = []
        self.flag_queue: list[QueuedFlag] = []

        self.language_skill_checked_flag = os.getenv('LANGUAGE_SKILL_CHECKED_FLAG')
        self.kick_after_minutes = int(os.getenv('KICK_AFTER_MINUTES', '5'))
        self.grace_period_minutes = int(os.getenv('GRACE_PERIOD_MINUTES', '4'))
        self.max_question_changes = int(os.getenv('MAX_QUESTION_CHANGES', '1'))
        self.remessage_every_n_cycles = int(os.getenv('REMESSAGE_EVERY_N_CYCLES', '3'))
        self.change_question_keyword = os.getenv('CHANGE_QUESTION_KEYWORD', 'hll-language-skill-check').lower()
        self.change_question_message = os.getenv('CHANGE_QUESTION_MESSAGE', 'CHANGE_QUESTION_MESSAGE\n\n{change_question_keyword}').replace('\\n', '\n').replace('\\"', '"')
        self.question_message = os.getenv('QUESTION_MESSAGE', 'QUESTION_MESSAGE\n\n{word_description}').replace('\\n', '\n').replace('\\"', '"')
        self.punish_message = os.getenv('PUNISH_MESSAGE', 'PUNISH_MESSAGE\n\n{word_description}').replace('\\n', '\n').replace('\\"', '"')
        self.kick_message = os.getenv('KICK_MESSAGE', 'KICK_MESSAGE hll-language-skill-check').replace('\\n', '\n').replace('\\"', '"')
        self.success_message = os.getenv('SUCCESS_MESSAGE', 'SUCCESS_MESSAGE').replace('\\n', '\n').replace('\\"', '"')
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

                # Remove pending checks for players who have been offline for too long
                offline_timeout = timedelta(minutes=self.kick_after_minutes + 5)
                players_to_remove = []
                for player_id, player_check in self.pending_skill_checks.items():
                    if player_id not in current_players:
                        time_since_request = datetime.now() - player_check.requested_on
                        if time_since_request >= offline_timeout:
                            logger.info(
                                f"Removing pending check for offline player {player_check.name} ({player_id}). "
                                f"Time since request: {time_since_request}"
                            )
                            players_to_remove.append(player_id)

                for player_id in players_to_remove:
                    del self.pending_skill_checks[player_id]
                    self.stats.removed_offline_checks += 1

                for player_id, player_data in current_players.items():
                    try:
                        self._process_player(server, player_id, player_data, logs_by_player.get(player_id, []))
                    except Exception as e:
                        logger.exception(f"Error processing player {player_data.get('name', 'Unknown')} ({player_id}): {e}", exc_info=e)

            # Process all queued actions
            self._process_queues()

            self.stats.pending_skill_checks = len(self.pending_skill_checks)
            logger.info(f"cycle complete - {self.stats}")

            logger.debug("Waiting 30 seconds before next check...")
            time.sleep(30)

    def _process_player(self, server: Server, player_id: str, player_data: dict, logs: list[dict]):
        player_name = player_data.get("name", "Unknown")
        logger.debug(f"Checking player {player_name} ({player_id})")
        profile = player_data.get("profile", {})
        # sometimes the player profile doesn't yet exist when the player just joined
        # it should be included in the next cycle, so we can just skip the check for now
        if profile is None:
            logger.warning(f"Player {player_name} ({player_id}) has no profile data, skipping")
            return

        # Prüfe ob Spieler bereits das Flag hat
        flags = profile.get("flags", [])
        has_checked_flag = any(
            flag.get("flag") == self.language_skill_checked_flag
            for flag in flags
        )

        if has_checked_flag:
            logger.debug(f"Player {player_id} already has language skill checked flag")
            return

        if player_data.get("unit_name", None) == "unassigned":
            logger.debug(f"Player {player_name} ({player_id}) is not assigned to a unit, skipping")
            self.stats.unassigned_players_without_skill += 1
            return

        self.stats.assigned_players_without_skill += 1
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

        self.message_queue.append(QueuedMessage(server, player_id, player_name, message))

        self.pending_skill_checks[player_id] = player_check

        logger.debug(f"Started language check for player {player_name} ({player_id}): {word.description}")

    def _verify_pending_skill_check(self, server: Server, player_id: str, logs: list[dict]):
        player_check = self.pending_skill_checks[player_id]

        if logs:
            logger.debug(f"Player {player_check.name} ({player_id}) has {len(logs)} message(s): {';'.join(log.get('content', '') for log in logs)}")
        else:
            logger.debug(f"Player {player_check.name} ({player_id}) has no messages")

        for log in logs:
            message = log.get("content", "")
            # Normalize message for comparison (handles umlauts and ASCII equivalents)
            normalized_message = normalize_german_text(message)

            logger.debug(f"Checking message from {player_check.name}: '{message}' (normalized: '{normalized_message}')")

            # Check against all possible matches
            for match in player_check.word.matches:
                # Normalize match text as well
                normalized_match = normalize_german_text(match)
                logger.debug(f"Comparing against match '{match}' (normalized: '{normalized_match}')")

                if normalized_match in normalized_message:
                    logger.info(f"Player {player_check.name} ({player_id}) answered correctly: {message}")

                    self.flag_queue.append(QueuedFlag(
                        server,
                        player_id,
                        player_check.name,
                        self.language_skill_checked_flag,
                        f"Language check passed: {player_check.word.description} with answer '{message}' at {datetime.now().isoformat()}"
                    ))

                    del self.pending_skill_checks[player_id]
                    self.stats.skill_gained_this_cycle += 1

                    self.message_queue.append(QueuedMessage(server, player_id, player_check.name, self.success_message))

                    return

            # Check if player requests another question
            if self.change_question_keyword in normalized_message:
                if player_check.question_changes_remaining > 0:
                    player_check.question_changes_remaining -= 1

                    available_words = [w for w in self.words if w.description != player_check.word.description]
                    new_word = random.choice(available_words)
                    player_check.word = new_word
                    player_check.requested_on = datetime.now()
                    player_check.cycles_since_last_message = 0

                    logger.info(
                        f"Player {player_check.name} ({player_id}) requested new question. "
                        f"Remaining changes: {player_check.question_changes_remaining}"
                    )

                    message_text = self.question_message.format(
                        word_description=player_check.word.description,
                        question_changes_remaining=player_check.question_changes_remaining
                    )
                    if player_check.question_changes_remaining > 0:
                        message_text += "\n\n\n" + self.change_question_message.format(
                            change_question_keyword=self.change_question_keyword
                        )

                    self.message_queue.append(QueuedMessage(server, player_id, player_check.name, message_text))
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
                    self.message_queue.append(QueuedMessage(server, player_id, player_check.name, message_text))

        # No correct answer found
        time_elapsed = datetime.now() - player_check.requested_on
        logger.info(
            f"Player {player_check.name} ({player_id}) no correct answer. "
            f"Time elapsed: {str(time_elapsed).split('.')[0]} "
        )

        # Increment cycle counter
        player_check.cycles_since_last_message += 1

        # Just re-message the player during grace period (only every N cycles)
        if time_elapsed < timedelta(minutes=self.grace_period_minutes):
            if player_check.cycles_since_last_message >= self.remessage_every_n_cycles:
                message_text = self.question_message.format(
                    word_description=player_check.word.description,
                    question_changes_remaining=player_check.question_changes_remaining
                )
                if player_check.question_changes_remaining > 0:
                    message_text += "\n\n\n" + self.change_question_message.format(
                        change_question_keyword=self.change_question_keyword
                    )

                self.message_queue.append(QueuedMessage(server, player_id, player_check.name, message_text))
                player_check.cycles_since_last_message = 0
            return

        # Kick after total time expired
        elif time_elapsed >= timedelta(minutes=self.kick_after_minutes):
            logger.info(
                f"Kicking player {player_check.name} ({player_id}) for exceeding time limit. "
                f"Time elapsed: {str(time_elapsed).split('.')[0]}"
            )
            self.kick_queue.append(QueuedKick(server, player_id, player_check.name, self.kick_message))
            del self.pending_skill_checks[player_id]

        # Punish with message (the message serves as reminder)
        else:
            logger.info(f"Punishing player {player_check.name} ({player_id}) for not answering")
            # omit the other question part
            punish_msg = self.punish_message.format(
                word_description=player_check.word.description,
                question_changes_remaining=player_check.question_changes_remaining
            )
            self.punish_queue.append(QueuedPunish(server, player_id, player_check.name, f"\n\n{punish_msg}\n\n"))
            self.stats.player_punishes += 1


    def _process_queues(self):
        """Process all queued actions in order: kicks, punishes (with fallback to messages), flags, messages"""

        sleep_time = 0.4

        # Process kicks first
        for action in self.kick_queue:
            try:
                action.server.api.kick_player(action.player_id, action.message)
                logger.debug(f"Kicked player {action.player_name} ({action.player_id})")
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Failed to kick player {action.player_name} ({action.player_id}): {e}")

        self.kick_queue.clear()

        # Process punishes, if they fail, add to message queue
        for action in self.punish_queue:
            try:
                action.server.api.punish_player(action.player_id, action.message)
                logger.debug(f"Punished player {action.player_name} ({action.player_id})")
                time.sleep(sleep_time)
            except HTTPError as e:
                logger.debug(f"Punish failed for {action.player_name} ({action.player_id}), sending message instead")
                # Add to message queue as fallback
                self.message_queue.append(QueuedMessage(
                    action.server,
                    action.player_id,
                    action.player_name,
                    action.message.strip()
                ))
            except Exception as e:
                logger.error(f"Failed to punish player {action.player_name} ({action.player_id}): {e}")

        self.punish_queue.clear()

        # Process flags
        for action in self.flag_queue:
            try:
                action.server.api.add_flag_to_player(action.player_id, action.flag, action.comment)
                logger.debug(f"Added flag to player {action.player_name} ({action.player_id})")
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Failed to add flag to player {action.player_name} ({action.player_id}): {e}")

        self.flag_queue.clear()

        # Process messages last
        for action in self.message_queue:
            try:
                action.server.api.message_player(action.player_id, action.message)
                logger.debug(f"Sent message to player {action.player_name} ({action.player_id})")
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Failed to send message to player {action.player_name} ({action.player_id}): {e}")

        self.message_queue.clear()

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
