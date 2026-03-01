import logging
import os
import re
import time
from datetime import datetime
from logging import LogRecord
from zoneinfo import ZoneInfo


class LogFormatter(logging.Formatter):
    @staticmethod
    def _count_placeholders_in_string(string: str):
        pattern = r'%[-+]?(\d+|\.\d+|\d+\.\d+)?[a-zA-Z]'
        matches = re.findall(pattern, string)
        return len(matches)

    def format(self, record: LogRecord) -> str:
        if record.args:
            safe_args = []
            for arg in record.args:
                try:
                    safe_args.append(str(arg))
                except BaseException:
                    safe_args.append(f'<non-stringable: {type(arg).__name__}>')

            record.args = tuple(safe_args)

        if not record.msg:
            record.msg = '<empty message>'

        try:
            record.msg = str(record.msg)
        except BaseException:
            record.msg = f'<non-stringable: {type(record.msg).__name__}>'

        required_placeholders = max(0, len(record.args) - self._count_placeholders_in_string(record.msg))
        record.msg = record.msg + ' ' + (', '.join(['%s'] * required_placeholders))

        try:
            return super().format(record)
        except BaseException as exception:
            message = f"<non-stringable: {type(exception).__name__}>"
            try:
                message = str(exception)
            except BaseException:
                pass

            logger('logger').exception(exception)
            return 'LOGGING ERROR: ' + message + str(record)


__logger_configured = None


def     logger(name: str = None):
    global __logger_configured

    if not __logger_configured:
        log_formatter = LogFormatter(u'%(asctime)s %(levelname)s %(name)s: %(message)s')
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(log_formatter)
        logging.basicConfig(level=logging.INFO, handlers=[stream_handler])

    return logging.getLogger(name)


class Printable:
    def __str__(self):
        attributes = ', '.join(f"{key}={value}" for key, value in self.__dict__.items())
        return f"{self.__class__.__name__}({attributes})"


def dump(obj, indent=0):
    spacer = "  " * indent
    if obj is None:
        print(f"{spacer}NoneType: None")
    elif isinstance(obj, (int, float, bool, str)):
        print(f"{spacer}{type(obj).__name__}: {repr(obj)}")
    elif isinstance(obj, (list, tuple, set)):
        print(f"{spacer}{type(obj).__name__}[len={len(obj)}]:")
        for i, item in enumerate(obj):
            print(f"{spacer}  [{i}]:")
            dump(item, indent + 2)
    elif isinstance(obj, dict):
        print(f"{spacer}{type(obj).__name__}[len={len(obj)}]:")
        for k, v in obj.items():
            print(f"{spacer}  {repr(k)} =>")
            dump(v, indent + 2)
    elif isinstance(obj, datetime):
        print(f"{spacer}{type(obj).__name__}: {obj.isoformat()}")
    elif hasattr(obj, "__dict__"):
        print(f"{spacer}{type(obj).__name__}:")
        for k, v in obj.__dict__.items():
            print(f"{spacer}  {k} =>")
            dump(v, indent + 2)
    else:
        print(f"{spacer}{type(obj).__name__}: {repr(obj)}")


def get_local_timezone() -> ZoneInfo:
    tz_name = os.environ.get("TZ")

    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass

    offset_hours = -time.timezone // 3600
    try:
        return ZoneInfo(f"Etc/GMT{'-' if offset_hours > 0 else '+'}{abs(offset_hours)}")
    except Exception:
        pass

    return ZoneInfo("UTC")


def now() -> datetime:
    tz = get_local_timezone()
    return datetime.now(tz)
