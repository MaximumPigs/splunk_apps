"""Offline tests for the splk tooling: config, logging, run log, AppInspect parsing.

None of these need Splunk; the REST client is covered against a fake server in
test_splk_rest.py.
"""

import json
import logging
import os

import pytest

from splk import config, logs, runlog, stages

TARGETS = """\
default_target = "local"

[targets.local]
host = "localhost"
verify_tls = false

[targets.other]
host = "splunk.example"
port = 18089
token_env = "OTHER_TOKEN"
"""


@pytest.fixture
def targets_file(tmp_path):
    path = tmp_path / "targets.toml"
    path.write_text(TARGETS)
    return str(path)


# --------------------------------------------------------------------- config

def test_env_file_does_not_override_real_environment(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nSPLUNK_TOKEN="from-file"\nexport EXTRA=1\nBAD LINE\n')
    environ = {"SPLUNK_TOKEN": "from-env"}
    loaded = config.load_env_file(str(env_file), environ)
    assert environ == {"SPLUNK_TOKEN": "from-env", "EXTRA": "1"}
    assert loaded == 1


def test_default_target_resolves_with_token(targets_file):
    target = config.resolve_target(path=targets_file, environ={"SPLUNK_TOKEN": "SECRET123"})
    assert target.name == "local"
    assert target.base_url == "https://localhost:8089"
    assert target.verify_tls is False
    assert target.token == "SECRET123"
    # describe() is used in logs and must never include the token.
    assert "SECRET123" not in target.describe()


def test_env_var_selects_target(targets_file):
    environ = {"SPLK_TARGET": "other", "OTHER_TOKEN": "x"}
    target = config.resolve_target(path=targets_file, environ=environ)
    assert target.name == "other"
    assert target.base_url == "https://splunk.example:18089"


def test_missing_token_is_a_config_error(targets_file):
    with pytest.raises(config.ConfigError, match="SPLUNK_TOKEN"):
        config.resolve_target(path=targets_file, environ={})


def test_unknown_target_lists_known_ones(targets_file):
    with pytest.raises(config.ConfigError, match="local, other"):
        config.resolve_target("nope", path=targets_file, environ={})


def test_unknown_key_fails_loudly(tmp_path):
    path = tmp_path / "targets.toml"
    path.write_text('default_target = "a"\n[targets.a]\nhost = "h"\nverfy_tls = false\n')
    with pytest.raises(config.ConfigError, match="verfy_tls"):
        config.resolve_target(path=str(path), environ={"SPLUNK_TOKEN": "t"})


def test_repo_targets_file_is_valid():
    """The committed config must always parse and name a real default."""
    data = config.load_targets_file()
    assert data["default_target"] in data["targets"]


# -------------------------------------------------------------------- logging

def test_tokens_are_masked_in_logs(tmp_path, caplog):
    logger = logs.setup_logging(log_dir=str(tmp_path))
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJlc2lnbmF0dXJl"
    logs.get_logger("test").info("header Bearer %s sent", jwt)
    for handler in logger.handlers:
        handler.flush()
    written = (tmp_path / "splk.log").read_text()
    assert jwt not in written
    assert "<redacted>" in written
    # One JSON object per line.
    assert json.loads(written.strip().splitlines()[-1])["level"] == "INFO"
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logging.getLogger("splk").propagate = True


# -------------------------------------------------------------------- run log

def test_runlog_round_trip_and_fixed_failures(tmp_path):
    runs = str(tmp_path)
    runlog.record("dev", "app1", "live", False, "1 failed", ["t::x: boom"], runs_dir=runs)
    runlog.record("dev", "app1", "build", True, "built", runs_dir=runs)
    runlog.record("dev", "app1", "live", True, "1 passed", runs_dir=runs)
    runlog.record("dev", "app2", "inspect", False, "failure=1", runs_dir=runs)
    entries = runlog.read_since(0, runs_dir=runs)
    assert [e["stage"] for e in entries] == ["live", "build", "live", "inspect"]

    fixed = runlog.fixed_failures(entries)
    assert len(fixed) == 1
    (app, stage), failed, passed = fixed[0]
    assert (app, stage) == ("app1", "live")
    assert failed["details"] == ["t::x: boom"]


def test_runlog_skips_torn_lines(tmp_path):
    (tmp_path / "2026-01-01.jsonl").write_text('{"epoch": 1, "ok": true}\n{"epoch": 2, "ok"\n')
    assert len(runlog.read_since(0, runs_dir=str(tmp_path))) == 1


# ---------------------------------------------------------------- AppInspect

def _report(*checks):
    """Build a report in the shape splunk-appinspect 4.x writes with --data-format json."""
    return {"reports": [{"groups": [{"name": "g", "checks": [
        {"name": n, "result": r, "messages": [{"message": m}] if m else []} for n, r, m in checks
    ]}]}]}


def test_appinspect_clean_report_passes():
    ok, summary, details = stages.summarise_appinspect(_report(
        ("check_a", "success", ""), ("check_b", "warning", "meh"), ("check_c", "not_applicable", ""),
    ))
    assert ok and details == []
    assert summary == "not_applicable=1, success=1, warning=1"


def test_appinspect_failures_and_unreviewed_manual_checks_fail():
    ok, _summary, details = stages.summarise_appinspect(
        _report(("check_fail", "failure", "bad thing\nmore"), ("check_manual", "manual_check", "look"),
                ("check_reviewed", "manual_check", "seen")),
        reviewed_manual={"check_reviewed"},
    )
    assert not ok
    assert details == ["FAILURE check_fail: bad thing", "UNREVIEWED manual_check check_manual: look"]


def test_appinspect_waived_failure_passes():
    ok, _s, details = stages.summarise_appinspect(
        _report(("check_waived", "failure", "x")), waived={"check_waived"})
    assert ok and details == []


def test_yaml_keys_read_without_pyyaml(tmp_path):
    path = tmp_path / "manual.yaml"
    path.write_text("# header\n#   check_commented:\ncheck_one:\n  comment: \"ok\"\ncheck_two:\n  comment: x\n")
    assert stages._yaml_top_level_keys(str(path)) == {"check_one", "check_two"}


def test_junit_failures(tmp_path):
    path = tmp_path / "r.xml"
    path.write_text(
        '<testsuites><testsuite>'
        '<testcase classname="tests.a" name="ok"/>'
        '<testcase classname="tests.a" name="bad"><failure message="assert 1 == 2&#10;more">x</failure></testcase>'
        '<testcase classname="tests.b" name="err"><error message="boom">y</error></testcase>'
        '</testsuite></testsuites>'
    )
    assert stages.junit_failures(str(path)) == ["tests.a::bad: assert 1 == 2", "tests.b::err: boom"]


# --------------------------------------------------------------------- build

def test_build_uses_repo_packager(tmp_path, monkeypatch):
    monkeypatch.setattr(runlog, "record", lambda *a, **k: None)
    result = stages.build("fillcontinuous", outdir=str(tmp_path))
    assert result.ok, result.summary
    assert os.path.basename(result.artifact).startswith("fillcontinuous-")
    assert result.artifact.endswith(".spl")


def test_build_unknown_app_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(runlog, "record", lambda *a, **k: None)
    result = stages.build("no_such_app", outdir=str(tmp_path))
    assert not result.ok
    assert "No such app" in result.summary
