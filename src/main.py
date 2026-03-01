import logging
from os.path import isfile

import dotenv

logger = logging.getLogger()
try:
    from shared.shared import logger

    logger = logger('main')

    import os
    import threading
    import subprocess
    import time
    import psutil
    import json
    from shared.config import Server, Word
    import checker
    from pathlib import Path

    if __name__ == "__main__":
        app_path = Path(__file__).resolve().parent.parent.parent

        dotenv_path = os.path.join(app_path, ".env")
        if isfile(dotenv_path):
            logger.info('loading .env file')
            dotenv.load_dotenv(dotenv_path=dotenv_path)
        else:
            logger.info('no .env found')

        servers = []
        for i in range(1, 9):
            api_base_url = os.getenv(f'CRCON_{i}_API_BASE_URL')
            api_key = os.getenv(f'CRCON_{i}_API_KEY')
            if api_base_url and api_key:
                servers.append(Server(api_base_url, api_key))

        words_path = os.path.join(app_path, "words.json")
        words = []
        if isfile(words_path):
            logger.info('loading words.json file')
            with open(words_path, 'r', encoding='utf-8') as f:
                words_data = json.load(f)
                for word_data in words_data:
                    words.append(Word(
                        description=word_data['description'],
                        matches=word_data['matches']
                    ))
            logger.info(f'loaded {len(words)} words')
        else:
            raise RuntimeError('words.json not found')

        try:
            checker.invoke(servers, words)
        except KeyboardInterrupt:
            psutil.Process(os.getpid()).terminate()
        except BaseException as exception:
            logger.exception(exception)
            psutil.Process(os.getpid()).terminate()

except BaseException as exception:
    logger.exception(exception)
    psutil.Process(os.getpid()).terminate()
