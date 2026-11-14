"""TEMPORARY probe: what Splunk Web's own role editor lets an admin change.

The owner wants easyadmin to change only what Settings > Roles can. This walks
the editor on the live instance for a throwaway role, opens every tab of the
edit dialog, and records what each shows (screenshots plus the text and form
controls) in build/reports/ui/easyadmin/role-editor-*.png and
role-editor.json. Nothing is saved: the page is left with Cancel.

Delete this file once easyadmin's tabs have been matched to the editor.
"""

import json
import logging
import os

log = logging.getLogger("splk.ui.probe")


def _controls(scope):
    """Every form control in ``scope`` with its name, type and accessible label."""
    return scope.evaluate(
        """(root) => Array.from(root.querySelectorAll('input, select, textarea, [role=checkbox],'
                + ' [role=combobox], [role=switch], [role=radio], [role=listbox]'))
            .map(el => ({tag: el.tagName.toLowerCase(), type: el.getAttribute('type'),
                         name: el.getAttribute('name'), role: el.getAttribute('role'),
                         label: el.getAttribute('aria-label') || el.getAttribute('placeholder')
                                || (el.labels && el.labels[0] ? el.labels[0].innerText : null),
                         disabled: !!el.disabled}))""")


def test_probe_role_editor(web, page, sandbox, artifacts):
    role = sandbox.create_role(label="probe", srchIndexesAllowed="main")
    report = {"role": role, "steps": [], "tabs": []}
    # web.open adds the locale prefix.
    web.open(page, "/manager/launcher/authorization/roles")
    page.wait_for_load_state("networkidle")
    web.screenshot(page, os.path.join(artifacts, "role-editor-list.png"))

    # Narrow the list to the throwaway role if there is a filter box.
    try:
        box = page.locator("input[type=text], input[type=search]").first
        box.fill(role, timeout=5000)
        page.wait_for_timeout(1500)
        report["steps"].append("filtered the list")
    except Exception as exc:  # noqa: BLE001 - a probe records, it does not fail
        report["steps"].append("no filter box: %s" % str(exc).splitlines()[0])

    # On 10.6.1 the role name opens a full "Edit Role <name>" page (not a
    # modal dialog), with its own tab strip and Cancel / Save Role buttons.
    try:
        page.get_by_text(role, exact=True).first.click(timeout=10000)
        page.get_by_text("Edit Role %s" % role).first.wait_for(timeout=15000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        report["steps"].append("opened the edit page: %s" % page.url)
    except Exception as exc:  # noqa: BLE001
        report["steps"].append("could not open the editor: %s" % str(exc).splitlines()[0])
        web.screenshot(page, os.path.join(artifacts, "role-editor-failed.png"))
        _write(artifacts, report)
        raise AssertionError("PROBE could not open the role editor; see role-editor.json")

    tabs = page.locator("[role=tab]")
    labels = [t.strip() for t in tabs.all_inner_texts()]
    report["tab_labels"] = labels
    body = page.locator("body")
    for index, label in enumerate(labels or ["(no tabs)"]):
        if labels:
            tabs.nth(index).click()
            page.wait_for_timeout(2000)
        shot = os.path.join(artifacts, "role-editor-tab-%d.png" % (index + 1))
        web.screenshot(page, shot)
        report["tabs"].append({"label": label, "text": body.inner_text()[:20000],
                               "controls": _controls(body)})
    # Leave without saving: Cancel discards the form.
    try:
        page.get_by_role("button", name="Cancel").first.click(timeout=5000)
        report["steps"].append("left with Cancel")
    except Exception as exc:  # noqa: BLE001
        report["steps"].append("no Cancel button: %s" % str(exc).splitlines()[0])
    _write(artifacts, report)
    log.info("Role editor probe written to %s", artifacts)


def _write(artifacts, report):
    with open(os.path.join(artifacts, "role-editor.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
