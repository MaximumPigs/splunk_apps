"""Opt-in timing probe for the App management filters on a large model.

Not an assertion test: it measures. Skipped unless EASYADMIN_PERF_PROBE=1:

    EASYADMIN_PERF_PROBE=1 PYTEST_ADDOPTS="-k perf_probe" splk test --ui easyadmin

It stubs the apps endpoint's list response with a few hundred apps and several
thousand objects built from the real response (nothing on the target changes),
times each filter keystroke to the next frame, times eight characters typed
30 ms apart until the page settles, and profiles which page functions the time
goes to. Results: build/reports/ui/easyadmin/probe-filter-perf.json.
"""

import collections
import json
import os
import urllib.parse

import pytest

APP = "easyadmin"
VIEW = "app_management"
ROOT = "#easyadmin-apps"
N_APPS = 300
N_OBJECTS = 5000


def _big(model):
    common = {t["id"] for t in model["types"] if t.get("common")}
    templates = [o for o in model["objects"] if o["type"] in common] or model["objects"]
    app_tmpl = next(a for a in model["apps"] if a.get("target") and not a.get("builtin"))
    apps = []
    for i in range(N_APPS):
        app = dict(app_tmpl)
        app.update(name="perfapp_%03d" % i, label="Perf app %03d" % i, builtin=False, target=True)
        apps.append(app)
    objects = []
    for i in range(N_OBJECTS):
        obj = json.loads(json.dumps(templates[i % len(templates)]))
        app = "perfapp_%03d" % (i % N_APPS)
        obj["name"] = "perf_obj_%05d" % i
        obj["app"] = app
        obj["key"] = "%s|perf|%s|%s" % (obj["type"], app, obj["name"])
        if isinstance(obj.get("acl"), dict):
            obj["acl"]["app"] = app
        objects.append(obj)
    model = dict(model)
    model["apps"] = model["apps"] + apps
    model["objects"] = model["objects"] + objects
    return model


def _install_stub(page):
    def handle(route):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query)
        if route.request.method != "GET" or "name" in query:
            route.continue_()
            return
        response = route.fetch()
        route.fulfill(response=response, body=json.dumps(_big(response.json())),
                      headers={**response.headers, "content-type": "application/json"})
    page.route("**/services/easyadmin/apps?**", handle)


# The page under test may delay a filter's render (a pause in typing). The
# grid then names the filter it was drawn with in data-filter / data-app-filter;
# "settled" waits for that. Code without the attribute settles at once.
SETTLED = """
  const frame = () => new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
  const settled = async (attr, text) => {
    for (;;) {
      await frame();
      const wrap = document.querySelector('#easyadmin-apps .ea-grid-wrap');
      if (!wrap || !wrap.hasAttribute(attr) || wrap.getAttribute(attr) === text) { return; }
    }
  };
"""

SEQ = """async ([selector, attr, texts]) => {
  const out = [];""" + SETTLED + """
  for (const text of texts) {
    const input = document.querySelector(selector);
    input.focus();
    const t0 = performance.now();
    input.value = text;
    input.dispatchEvent(new Event('input', {bubbles: true}));
    const handler = performance.now() - t0;
    await settled(attr, text);
    out.push({text, handler_ms: Math.round(handler), to_settled_ms: Math.round(performance.now() - t0),
      rows: document.querySelectorAll('#easyadmin-apps .ea-object').length,
      boxes: document.querySelectorAll('#easyadmin-apps .ea-app').length,
      nodes: document.querySelectorAll('#easyadmin-apps *').length});
  }
  return out;
}"""

TYPE = """async ([selector, attr, word, gap]) => {""" + SETTLED + """
  document.querySelector(selector).focus();
  const t0 = performance.now();
  for (let i = 1; i <= word.length; i++) {
    // Re-query: a render replaces the field, as real typing finds the new one focused.
    const input = document.activeElement;
    input.value = word.slice(0, i);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    await new Promise(r => setTimeout(r, gap));
  }
  await settled(attr, word);
  return Math.round(performance.now() - t0);
}"""

NAMES = ["render", "renderGrid", "renderApp", "renderObject", "renderMovingOut", "renderGhost", "icon", "objectsByApp",
         "hiddenStagedByApp", "visibleApps", "snapshot", "restore", "renderFilterResults", "buildIcon", "flushFilters",
         "renderToolbar", "renderTypeMenu", "renderLegend",
         "renderSelectionBar", "buildPanel", "announce", "el", "matches", "appList", "splunkIsDark", "renderMessages",
         "renderTabs", "plural", "aclOf", "changeParts", "appMatches", "focus", "empty", "cleanData"]


def _profile(cdp, action):
    cdp.send("Profiler.enable")
    cdp.send("Profiler.setSamplingInterval", {"interval": 100})
    cdp.send("Profiler.start")
    action()
    profile = cdp.send("Profiler.stop")["profile"]
    nodes = {n["id"]: n for n in profile["nodes"]}
    parents = {}
    for n in profile["nodes"]:
        for c in n.get("children", []):
            parents[c] = n["id"]
    incl = collections.Counter()
    selfc = collections.Counter()
    for sample, delta in zip(profile["samples"], profile["timeDeltas"]):
        f = nodes[sample]["callFrame"]
        selfc[f["functionName"] or "(anon)"] += delta
        seen = set()
        nid = sample
        while nid is not None:
            name = nodes[nid]["callFrame"]["functionName"]
            if name in NAMES and name not in seen:
                incl[name] += delta
                seen.add(name)
            nid = parents.get(nid)
    return {"inclusive_ms": [(k, round(v / 1000)) for k, v in incl.most_common()],
            "self_top_ms": [(k, round(v / 1000)) for k, v in selfc.most_common(12)]}


@pytest.mark.skipif(os.environ.get("EASYADMIN_PERF_PROBE") != "1",
                    reason="timing probe; set EASYADMIN_PERF_PROBE=1 to run it")
def test_filter_perf_probe(open_view, page, artifacts):
    _install_stub(page)
    page.set_default_timeout(120000)
    t = open_view(APP, VIEW, ready=ROOT + " .ea-grid")
    out = {"apps": N_APPS, "objects": N_OBJECTS}
    obj_seq = ["p", "pe", "perf", "perf_obj_0", "perf_obj_00", "perf_obj_001", "perf_obj_0012", ""]
    app_seq = ["p", "perf", "perfapp_0", "perfapp_00", "perfapp_001", ""]
    out["object_filter"] = t.evaluate(SEQ, [ROOT + " .ea-filter", "data-filter", obj_seq])
    out["app_filter"] = t.evaluate(SEQ, [ROOT + " .ea-app-filter", "data-app-filter", app_seq])
    out["typed_perf_obj_gap30_ms"] = t.evaluate(TYPE, [ROOT + " .ea-filter", "data-filter", "perf_obj", 30])
    t.evaluate(SEQ, [ROOT + " .ea-filter", "data-filter", [""]])
    cdp = t.context.new_cdp_session(t)
    out["profile_one_char"] = _profile(cdp, lambda: t.evaluate(SEQ, [ROOT + " .ea-filter", "data-filter", ["p"]]))
    out["profile_clear"] = _profile(cdp, lambda: t.evaluate(SEQ, [ROOT + " .ea-filter", "data-filter", [""]]))
    path = os.path.join(artifacts, "probe-filter-perf.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=1)
