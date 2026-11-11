"""Logging setup shared by every splk command.

Two sinks:

* stderr, human-readable, INFO by default (DEBUG with ``-v``). stdout is kept
  free for machine-readable output such as ``--json`` results.
* ``.agent/logs/splk.log``, rotating, always DEBUG, one JSON object per line,
  so a later session (or the learner agent) can reconstruct what happened.

Secrets never reach either sink: a filter masks anything that looks like a
Splunk token or an Authorization header before the record is formatted.
"""

import json
import logging
import logging.handlers
import os
import re

from splk import paths

LOGGER_NAME = "splk"

# Splunk auth tokens are JWTs (three base64url segments). Session keys are long
# opaque strings; both only ever appear after "Bearer " or "Splunk ".
_SECRET_PATTERNS = [
    re.compile(r"(Bearer|Splunk)\s+[A-Za-z0-9._\-+/=]{16,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
]


class SecretMaskingFilter(logging.Filter):
    """Replace token-shaped substrings in the final message with a marker."""

    def filter(self, record):
        message = record.getMessage()
        masked = message
        for pattern in _SECRET_PATTERNS:
            masked = pattern.sub("<redacted>", masked)
        if masked != message:
            # Freeze the masked text so formatters cannot re-expand args.
            record.msg = masked
            record.args = None
        return True


class JsonLineFormatter(logging.Formatter):
    """One JSON object per line: easy to grep, easy to parse."""

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(verbose=False, log_dir=None):
    """Configure the ``splk`` logger once and return it.

    Safe to call repeatedly: existing handlers are replaced, not duplicated,
    which matters for tests that invoke ``main()`` several times.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    masking = SecretMaskingFilter()

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    console.addFilter(masking)
    logger.addHandler(console)

    # The file sink is best-effort: a read-only checkout must not stop splk.
    target_dir = log_dir or paths.LOG_DIR
    try:
        os.makedirs(target_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(target_dir, "splk.log"),
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonLineFormatter())
        file_handler.addFilter(masking)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("File logging disabled: %s", exc)

    return logger


def get_logger(name):
    """Child logger under ``splk`` so every module shares the handlers above."""
    return logging.getLogger("%s.%s" % (LOGGER_NAME, name))
