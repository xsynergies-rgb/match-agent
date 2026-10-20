"""Request ids and log hygiene.

Every log line carries the id of the request it belongs to, so one request can be followed
through the logs. No line carries a bearer token, a JWT or a full phone number.
"""

import contextvars
import json
import logging
import re

request_id_var = contextvars.ContextVar("request_id", default="-")

_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_PHONE = re.compile(r"\+\d{8,15}")


def redact(text):
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _JWT.sub("[jwt]", text)
    return _PHONE.sub(lambda match: f"{match.group()[:4]}…{match.group()[-2:]}", text)


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        try:
            message = record.getMessage()
        except Exception:  # a malformed log call should not lose the line
            message = str(record.msg)
        record.msg, record.args = redact(message), None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)
