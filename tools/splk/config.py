"""Splunk target configuration.

A *target* is a Splunk instance splk can deploy to and test against. Targets
are declared in ``config/targets.toml`` (committed, no secrets); credentials
come from the environment or a gitignored ``.env`` file.

Adding a second instance later (a disposable Docker Splunk, a staging search
head) is a new ``[targets.<name>]`` table, with no code changes.
"""

import os

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised on the 3.9 CI leg
    import tomli as tomllib

from splk import paths
from splk.logs import get_logger

log = get_logger("config")

# Environment variable that overrides the default target for one invocation.
TARGET_ENV_VAR = "SPLK_TARGET"


class ConfigError(Exception):
    """Raised for missing or malformed target configuration."""


class Target(object):
    """Connection details for one Splunk instance."""

    def __init__(self, name, host, port=8089, scheme="https", verify_tls=True,
                 token_env="SPLUNK_TOKEN", token=None, allow_restart=False,
                 stage_dir=None, server_stage_dir=None, test_index="splk_test",
                 web_url=None, web_locale="en-US", web_user_env="SPLUNK_WEB_USERNAME",
                 web_password_env="SPLUNK_WEB_PASSWORD"):
        self.name = name
        self.host = host
        self.port = int(port)
        self.scheme = scheme
        self.verify_tls = bool(verify_tls)
        self.token_env = token_env
        self.token = token
        # Restarting splunkd is disruptive, so it is opt-in per target and
        # still requires an explicit --restart flag on the command line.
        self.allow_restart = bool(allow_restart)
        # When splunkd cannot read the repo's dist/ directly (Splunk in Docker
        # or WSL), packages are copied to stage_dir and splunkd is told to read
        # them from server_stage_dir, the same folder as splunkd sees it.
        self.stage_dir = stage_dir
        self.server_stage_dir = server_stage_dir
        # Index live tests may write seed events into. Never a production one.
        self.test_index = test_index
        # Splunk Web (port 8000), used only by browser tests and `splk shot`.
        # It cannot take a token: the browser signs in with a username and
        # password named by these env vars, so a target without web_url simply
        # has no UI stage.
        self.web_url = web_url.rstrip("/") if web_url else None
        self.web_locale = web_locale
        self.web_user_env = web_user_env
        self.web_password_env = web_password_env

    @property
    def base_url(self):
        return "%s://%s:%d" % (self.scheme, self.host, self.port)

    def describe(self):
        """Safe one-line summary for logs: never includes the token."""
        return "%s (%s, tls_verify=%s)" % (self.name, self.base_url, self.verify_tls)


def load_env_file(path=None, environ=None):
    """Load KEY=VALUE lines from a .env file into ``environ`` without overriding.

    Deliberately minimal (no interpolation, no export keyword handling beyond
    stripping it) so there is no dependency on python-dotenv. Values already
    set in the real environment win, which lets CI inject secrets directly.
    """
    path = path or paths.ENV_FILE
    environ = os.environ if environ is None else environ
    if not os.path.isfile(path):
        log.debug("No .env file at %s", path)
        return 0

    loaded = 0
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            # Skip blanks and comments.
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            # Strip one layer of matching quotes.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if key and key not in environ:
                environ[key] = value
                loaded += 1
    log.debug("Loaded %d variable(s) from %s", loaded, path)
    return loaded


def load_targets_file(path=None):
    """Parse targets.toml and return the raw dict."""
    path = path or paths.TARGETS_FILE
    if not os.path.isfile(path):
        raise ConfigError("Target config not found: %s" % path)
    with open(path, "rb") as handle:
        try:
            return tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError("Invalid TOML in %s: %s" % (path, exc))


# A target with `from_env = true` takes these keys from SPLK_TARGET_<KEY>
# (e.g. SPLK_TARGET_HOST). It is for an instance the owner runs elsewhere,
# such as the one the dev container (docker/) tests against: its host and
# shared folder are the owner's and stay out of the public repo. Opt-in per
# target, so the local target can never be redirected by a stray variable.
ENV_OVERRIDE_PREFIX = "SPLK_TARGET_"
_ENV_OVERRIDABLE = {
    "host": str, "port": int, "scheme": str, "verify_tls": "bool", "allow_restart": "bool",
    "stage_dir": str, "server_stage_dir": str, "test_index": str, "web_url": str,
}


def _parse_bool(key, value):
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError("%s%s must be true or false, not %r" % (ENV_OVERRIDE_PREFIX, key.upper(), value))


def _env_overrides(environ):
    overrides = {}
    for key, kind in _ENV_OVERRIDABLE.items():
        value = environ.get(ENV_OVERRIDE_PREFIX + key.upper())
        if value is None or value == "":
            continue
        if kind == "bool":
            overrides[key] = _parse_bool(key, value)
        elif kind is int:
            try:
                overrides[key] = int(value)
            except ValueError:
                raise ConfigError("%s%s must be a number, not %r" % (ENV_OVERRIDE_PREFIX, key.upper(), value))
        else:
            overrides[key] = value
    return overrides


def resolve_target(name=None, path=None, environ=None, require_token=True):
    """Return the named target (or the default) with its token filled in.

    Resolution order for the name: explicit argument, ``SPLK_TARGET``, then
    ``default_target`` in the file.
    """
    environ = os.environ if environ is None else environ
    data = load_targets_file(path)
    targets = data.get("targets") or {}
    # In an unattended `splk loop` step the target choice and its overrides
    # come only from the .env file the owner's set-up wrote, never from the
    # step's environment: otherwise one step command
    # (SPLK_TARGET_HOST=elsewhere splk doctor) could send the token to another
    # host or turn restarts on.
    source = environ
    if environ.get("SPLK_LOOP") == "1":
        source = {}
        load_env_file(environ=source)
        pinned = source.get(TARGET_ENV_VAR) or data.get("default_target")
        # --target in a step would deploy to one target while the live and
        # UI tests (which resolve again in a subprocess) used the pinned one.
        if name and name != pinned:
            raise ConfigError("Loop steps use target %r (from .env); --target %s is not allowed"
                              % (pinned, name))
    chosen = name or source.get(TARGET_ENV_VAR) or data.get("default_target")
    if not chosen:
        raise ConfigError("No target named and no default_target in targets.toml")
    if chosen not in targets:
        raise ConfigError(
            "Unknown target %r. Known targets: %s"
            % (chosen, ", ".join(sorted(targets)) or "(none)")
        )

    spec = dict(targets[chosen])
    if spec.pop("from_env", False):
        spec.update(_env_overrides(source))
    if "host" not in spec:
        raise ConfigError("Target %r has no host" % chosen)

    # Only known keys reach the constructor, so a typo fails loudly here
    # rather than being silently ignored.
    allowed = {
        "host", "port", "scheme", "verify_tls", "token_env", "allow_restart",
        "stage_dir", "server_stage_dir", "test_index",
        "web_url", "web_locale", "web_user_env", "web_password_env",
    }
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ConfigError("Target %r has unknown key(s): %s" % (chosen, ", ".join(unknown)))

    target = Target(name=chosen, **spec)
    target.token = environ.get(target.token_env)
    if require_token and not target.token:
        raise ConfigError(
            "Target %r needs a token in $%s (set it in .env; see .env.example)"
            % (chosen, target.token_env)
        )
    log.debug("Resolved target %s", target.describe())
    return target
