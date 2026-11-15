"""Unit tests for editing the individual settings of a knowledge object.

Behaviour copied from what was observed on Splunk 10.6.1 (the plan's probes,
pinned live by tests/live/easyadmin/test_easyadmin_settings_live.py): a write
through ``configs/conf-<conf>/<stanza>`` lands only the posted keys in the
object's local file (the owner's folder for a private object), and for props
and tags splunkd can answer 200 and write nothing, so the files are read back.
"""

import pytest

import easyadmin_apps_core as apps
from test_easyadmin_apps_core import ConfGateway, change, entry


# ------------------------------------------------------- reading settings

def test_explicit_settings_keep_the_lower_layers_for_show_default():
    files = {"default": "[m]\ndefinition = base\nerrormsg = a\n", "local": "[m]\ndefinition = mine\n",
             "user": "[m]\ndefinition = private\n"}
    by_name = dict((s["name"], s) for s in apps.explicit_settings(files, "m"))
    assert by_name["definition"]["layer"] == "user" and by_name["definition"]["value"] == "private"
    assert [(o["layer"], o["value"]) for o in by_name["definition"]["overrides"]] == [
        ("default", "base"), ("local", "mine")]
    assert by_name["errormsg"]["overrides"] == []


def test_explicit_settings_mask_secrets_in_the_hidden_values_too():
    files = {"default": "[a]\npassword = old\n", "local": "[a]\npassword = new\n"}
    (setting,) = apps.explicit_settings(files, "a")
    assert setting["value"] == "********" and setting["secret"] is True
    assert setting["overrides"][0]["value"] == "********"


def test_a_props_object_is_only_its_one_line():
    files = {"local": "[sourcetype1]\nEXTRACT-a = (?<x>a)\nEXTRACT-b = (?<y>b)\n[other]\nEXTRACT-a = z\n"}
    settings = apps.explicit_settings(files, "sourcetype1", only="EXTRACT-b")
    assert [(s["name"], s["value"]) for s in settings] == [("EXTRACT-b", "(?<y>b)")]


def _details(gateway, type_id, name, ns="nobody", app="search"):
    status, body = apps.handle_request("GET", None, {"type": type_id, "ns": ns, "app": app, "name": name}, gateway)
    assert status == 200
    return body


FIELDS = {"required": ["definition"], "optional": ["args", "eai:appName", "errormsg", "password"],
          "wildcard": ["action\\..*"]}


def test_details_say_what_can_be_edited_and_added():
    macro = entry("macro", "m1", "search", content={"definition": "x"}, fields=FIELDS)
    body = _details(ConfGateway([("macro", macro)], files={"local": "[m1]\ndefinition = x\n"}), "macro", "m1")
    assert body["editable"] is True and body["edit_layer"] == "local" and body["edit_note"] is None
    # Not its own setting, not eai:*, not a secret name.
    assert body["addable"] == ["args", "errormsg"]
    assert body["addable_patterns"] == ["action\\..*"] and body["free_text"] is False


def test_a_private_object_is_edited_in_the_owners_folder():
    macro = entry("macro", "mine", "search", owner="alice", sharing="user", fields=FIELDS)
    body = _details(ConfGateway([("macro", macro)]), "macro", "mine", ns="alice")
    assert body["editable"] is True and body["edit_layer"] == "user"


def test_editing_needs_admin_all_objects():
    gateway = ConfGateway([("macro", entry("macro", "m1", "search", fields=FIELDS))], capabilities=("search",))
    body = _details(gateway, "macro", "m1")
    assert body["editable"] is False and body["edit_note"] == "capability" and body["addable"] == []


def test_editing_needs_write_access_to_the_object():
    gateway = ConfGateway([("macro", entry("macro", "m1", "search", fields=FIELDS, can_write=False))])
    body = _details(gateway, "macro", "m1")
    assert body["editable"] is False and body["edit_note"] == "write"
    assert body["explicit"] == []   # it can still be read


@pytest.mark.parametrize("type_id", ["view", "nav", "panel", "lookupfile"])
def test_dashboards_navigation_panels_and_lookup_files_are_not_editable(type_id):
    gateway = ConfGateway([(type_id, entry(type_id, "x", "search"))])
    body = _details(gateway, type_id, "x")
    assert body["editable"] is False and body["edit_note"] == "kind"


@pytest.mark.parametrize("type_id", ["tag", "alertaction"])
def test_tags_and_alert_actions_take_free_text_names(type_id):
    gateway = ConfGateway([(type_id, entry(type_id, "x", "search", fields={"optional": ["tags", "eai:data"]}))])
    body = _details(gateway, type_id, "x")
    assert body["editable"] is True and body["free_text"] is True and body["addable"] == []


def _props(type_id="extraction", name="EXTRACT-a", stanza="st", attribute="EXTRACT-a"):
    return entry(type_id, name, "search", content={"stanza": stanza, "attribute": attribute, "value": "x"})


def test_a_props_object_edits_its_line_and_adds_nothing():
    files = {"local": "[st]\nEXTRACT-a = (?<x>a)\nEXTRACT-b = other\n"}
    body = _details(ConfGateway([("extraction", _props())], files=files), "extraction", "EXTRACT-a")
    assert body["explicit_conf"] == "props" and body["editable"] is True
    assert [s["name"] for s in body["explicit"]] == ["EXTRACT-a"]
    assert body["addable"] == [] and body["free_text"] is False


def test_a_props_object_without_a_stanza_in_its_entry_is_not_editable():
    item = entry("extraction", "x", "search", content={"value": "x"})
    body = _details(ConfGateway([("extraction", item)]), "extraction", "x")
    assert body["editable"] is False and body["explicit"] is None


# ----------------------------------------------------------- validation

def setting(name, value, previous=None):
    return {"name": name, "value": value, "previous": previous}


def edit(type_id, name, settings, **more):
    out = change(type_id, name, "search", settings=settings)
    out.update(more)
    return out


@pytest.mark.parametrize("settings,message", [
    ([], "non-empty list"),
    ("x", "non-empty list"),
    ([setting("a b ", "v")], "not a name"),
    ([setting("a=b", "v")], "not a name"),
    ([setting("[x]", "v")], "not a name"),
    ([setting("#x", "v")], "not a name"),
    ([setting("eai:data", "v")], "not a name"),
    ([setting("x" * 257, "v")], "1 to 256"),
    ([setting("", "v")], "1 to 256"),
    ([setting("a\nb", "v")], "not a name"),
    ([setting("password", "v")], "secret"),
    ([setting("output_mode", "v")], "reserved"),
    ([setting("name", "v")], "reserved"),
    ([setting("owner", "v")], "reserved"),
    ([setting("sharing", "v")], "reserved"),
    ([setting("app", "v")], "reserved"),
    ([setting("count", "v")], "reserved"),
    ([setting("f", "v")], "reserved"),
    ([setting("a", "v"), setting("a", "w")], "twice"),
    ([setting("a", 5)], "must be text"),
    ([setting("a", "x" * (apps.MAX_SETTING_VALUE + 1))], "longer than"),
    ([setting("a", "bad\x00")], "control characters"),
    ([setting("a", "bad\r")], "control characters"),
    ([{"name": "a", "value": "v"}], "previous"),
    ([{"name": "a", "value": "v", "previous": 3}], "previous"),
    (["a"], "must be an object"),
    ([setting("n%d" % i, "v") for i in range(apps.MAX_SETTINGS_PER_OBJECT + 1)], "at most"),
])
def test_settings_are_validated(settings, message):
    with pytest.raises(apps.EasyAdminError) as caught:
        apps.parse_changes([edit("macro", "m", settings)])
    assert message in str(caught.value)


def test_settings_of_a_dashboard_are_refused():
    with pytest.raises(apps.EasyAdminError) as caught:
        apps.parse_changes([edit("view", "home", [setting("a", "v")])])
    assert "cannot be edited" in str(caught.value)


def test_settings_cannot_go_with_a_delete():
    with pytest.raises(apps.EasyAdminError):
        apps.parse_changes([edit("macro", "m", [setting("a", "v")], delete=True)])


def test_a_change_with_only_settings_is_valid_and_keeps_newlines():
    (parsed,) = apps.parse_changes([edit("macro", "m", [setting("definition", "a\n\tb", None)])])
    assert parsed["settings"] == [{"name": "definition", "value": "a\n\tb", "previous": None}]
    assert parsed["move_to"] is None and parsed["delete"] is False


# -------------------------------------------------------------- applying

class SettingsGateway(ConfGateway):
    """ConfGateway that also takes configs writes into its in-memory files.

    ``lands`` False copies splunkd answering 200 and writing nothing, which
    it did for props and tags (observed on 10.6.1).
    """

    def __init__(self, objects, files=None, lands=True, **kw):
        ConfGateway.__init__(self, objects, files=files or {"local": "[m1]\ndefinition = old\n"}, **kw)
        self.lands = lands
        self.writes = []

    def set_conf(self, ns, app, conf, stanza, postargs):
        self.writes.append((ns, app, conf, stanza, dict(postargs)))
        if not self.lands:
            return
        layer = "user" if ns != "nobody" else "local"
        text = self.files.get(layer) or ""
        # splunkd writes a multi-line value with continuation backslashes.
        self.files[layer] = text + "[%s]\n" % stanza + "".join(
            "%s = %s\n" % (k, v.replace("\n", "\\\n")) for k, v in postargs.items())


def macro_gateway(**kw):
    return SettingsGateway([("macro", entry("macro", "m1", "search", fields=FIELDS))], **kw)


def test_settings_are_written_in_one_call_with_only_the_changed_keys():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [
        setting("definition", "new", "old"), setting("errormsg", "oops", None)])], user="admin")
    result = body["results"][0]
    assert result["status"] == "applied" and result["settings_applied"] is True
    assert result["message"] == 'Changed 2 settings of search macro "m1".'
    assert gateway.writes == [("nobody", "search", "macros", "m1", {"definition": "new", "errormsg": "oops"})]


def test_a_value_changed_since_the_page_loaded_is_not_overwritten():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", "what the page saw")])])
    assert body["results"][0]["status"] == "error" and "changed since" in body["results"][0]["message"]
    assert body["results"][0]["settings_applied"] is False and gateway.writes == []


def test_a_setting_the_page_thought_was_new_but_exists_is_not_overwritten():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", None)])])
    assert body["results"][0]["status"] == "error" and gateway.writes == []


def test_a_name_splunkd_does_not_list_is_refused():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("surprise", "v", None)])])
    assert body["results"][0]["status"] == "error" and "not a setting splunkd lists" in body["results"][0]["message"]
    assert gateway.writes == []


def test_a_wildcard_name_is_accepted():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("action.email", "1", None)])])
    assert body["results"][0]["status"] == "applied"
    assert gateway.writes[0][4] == {"action.email": "1"}


def test_free_text_types_take_any_name():
    gateway = SettingsGateway([("tag", entry("tag", "host=a", "search", fields={"optional": ["tags"]}))],
                              files={"local": ""})
    body = apps.submit_changes(gateway, [edit("tag", "host=a", [setting("web", "enabled", None)])])
    assert body["results"][0]["status"] == "applied"
    assert gateway.writes == [("nobody", "search", "tags", "host=a", {"web": "enabled"})]


def test_a_props_object_writes_only_its_own_line_into_its_own_stanza():
    gateway = SettingsGateway([("extraction", _props(stanza="source::/var/log/x*"))],
                              files={"local": "[source::/var/log/x*]\nEXTRACT-a = old\n"})
    body = apps.submit_changes(gateway, [edit("extraction", "EXTRACT-a", [setting("EXTRACT-a", "new", "old")])])
    assert body["results"][0]["status"] == "applied"
    assert gateway.writes == [("nobody", "search", "props", "source::/var/log/x*", {"EXTRACT-a": "new"})]
    other = apps.submit_changes(gateway, [edit("extraction", "EXTRACT-a", [setting("EXTRACT-b", "v", None)])])
    assert other["results"][0]["status"] == "error" and len(gateway.writes) == 1
    assert "belong to other objects" in other["results"][0]["message"]


def test_a_write_that_does_not_reach_the_file_is_an_error():
    gateway = macro_gateway(lands=False)
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", "old")])])
    result = body["results"][0]
    assert result["status"] == "error" and "did not reach" in result["message"]
    assert gateway.writes and result["settings_applied"] is False


def test_a_private_object_is_verified_in_the_owners_folder():
    gateway = SettingsGateway([("macro", entry("macro", "mine", "search", owner="alice", sharing="user",
                                               fields=FIELDS))], files={"local": "[mine]\ndefinition = old\n"})
    body = apps.submit_changes(gateway, [change("macro", "mine", "search", ns="alice",
                                                settings=[setting("definition", "new", "old")])])
    assert body["results"][0]["status"] == "applied"
    assert gateway.writes[0][0] == "alice" and gateway.reads[-1] == ("macros", "search", "alice")


def test_multi_line_values_are_verified_ignoring_layout():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "a\nb", "old")])])
    assert body["results"][0]["status"] == "applied"


def test_without_the_capability_or_write_access_nothing_is_written():
    gateway = macro_gateway(capabilities=("search",))
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", "old")])])
    assert body["results"][0]["status"] == "error" and gateway.writes == []
    gateway = SettingsGateway([("macro", entry("macro", "m1", "search", fields=FIELDS, can_write=False))])
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", "old")])])
    assert body["results"][0]["status"] == "error" and gateway.writes == []


def test_settings_for_an_object_in_another_app_are_not_written():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [change("macro", "m1", "other", settings=[setting("definition", "n", "old")])])
    assert body["results"][0]["status"] == "error" and gateway.writes == []


def test_settings_go_first_and_a_later_failure_says_so():
    gateway = macro_gateway()
    gateway.refuse_acl.add(apps.object_path("macro", "nobody", "search", "m1"))
    acl = {"sharing": "global", "owner": "nobody", "read": ["*"], "write": []}
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", "old")], acl=acl)])
    result = body["results"][0]
    assert result["status"] == "error" and result["settings_applied"] is True
    assert result["message"].startswith('The settings of "m1" were changed, but the rest was not')
    assert len(gateway.writes) == 1


def test_settings_and_a_move_report_both():
    gateway = macro_gateway()
    body = apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "new", "old")], move_to="myapp")])
    result = body["results"][0]
    assert result["status"] == "applied" and result["moved_to"] == "myapp"
    assert result["message"].startswith('Changed 1 setting of search macro "m1".') and "Moved" in result["message"]
    assert [c[0] for c in gateway.calls if c[0] == "move"] == ["move"]


def test_the_audit_log_names_the_settings_and_never_their_values(caplog):
    gateway = macro_gateway()
    with caplog.at_level("INFO", logger="easyadmin"):
        apps.submit_changes(gateway, [edit("macro", "m1", [setting("definition", "TOPSECRETVALUE", "old")])],
                            user="admin")
    lines = [r.getMessage() for r in caplog.records if "action=settings" in r.getMessage()]
    assert len(lines) == 1 and '"definition"' in lines[0] and "TOPSECRETVALUE" not in lines[0]
