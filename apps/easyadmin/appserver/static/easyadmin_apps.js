/*
 * Easy Admin - app management page.
 *
 * Shows every app as a box holding its knowledge objects, each with an icon
 * for its type. Objects can be dragged to another app's box, or selected and
 * moved, re-permissioned or deleted in bulk; clicking an object opens a panel
 * with every setting it has. Nothing is written until Apply: every change is
 * staged, marked on the object, and applied in one request.
 *
 * What splunkd allows for each object (move, delete, change permissions)
 * comes from the server, which reads it from the object itself. Validation
 * and the writes live in bin/easyadmin_apps_core.py, where they are unit
 * tested.
 *
 * Every name and value shown here comes from the server and is inserted with
 * text(), val() or attr(), never as HTML, so an object or app name with markup
 * in it cannot inject script into an administrator's session. Icon path data
 * is constant, defined below.
 *
 * Plain ES5 on purpose: no build step, and it runs as shipped.
 */
require([
    'jquery',
    'splunk.util',
    'splunkjs/mvc/simplexml/ready!'
], function ($, splunkUtil) {
    'use strict';

    // Splunk Web's proxy to splunkd; default/web.conf exposes this endpoint.
    var ENDPOINT = splunkUtil.make_url('/splunkd/__raw/services/easyadmin/apps');
    var SVG_NS = 'http://www.w3.org/2000/svg';

    var $root = $('#easyadmin-apps');

    // ---------------------------------------------------------------- theme
    //
    // Same approach as the role management page (playbook follow-user-theme):
    // reload once with ?theme=<preference> when Splunk drew the other theme,
    // then style the panel from the background Splunk actually drew.

    function luminance(css) {
        var parts = /rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?/.exec(css || '');
        if (!parts) { return null; }
        if (parts[4] !== undefined && parseFloat(parts[4]) === 0) { return null; }
        var channel = function (value) {
            var c = parseFloat(value) / 255;
            return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * channel(parts[1]) + 0.7152 * channel(parts[2]) + 0.0722 * channel(parts[3]);
    }

    function splunkIsDark() {
        var node = $root[0] && $root[0].parentNode;
        while (node && node.nodeType === 1) {
            var lum = luminance(window.getComputedStyle(node).backgroundColor);
            if (lum !== null) { return lum < 0.2; }
            node = node.parentNode;
        }
        return false;
    }

    function urlParam(name) {
        var match = new RegExp('[?&]' + name + '=([^&#]*)').exec(window.location.search);
        return match ? decodeURIComponent(match[1].replace(/\+/g, ' ')) : null;
    }

    // Loop guard: never reload when the URL already names the preferred theme.
    function matchSplunkTheme(preference) {
        if (preference !== 'light' && preference !== 'dark') { return false; }
        if (urlParam('theme') === preference) { return false; }
        if (splunkIsDark() === (preference === 'dark')) { return false; }
        var search = window.location.search.replace(/([?&])theme=[^&#]*&?/, '$1').replace(/[?&]$/, '');
        search += (search ? '&' : '?') + 'theme=' + encodeURIComponent(preference);
        window.location.replace(window.location.pathname + search + window.location.hash);
        return true;
    }

    // ---------------------------------------------------------------- icons
    //
    // One pictogram per knowledge object type, drawn with the text colour so
    // it follows the theme. Each carries the type's name as its accessible
    // text, and the legend above the boxes names every one (A6).

    var ICONS = {
        savedsearch: [['circle', { cx: 6.5, cy: 6.5, r: 4 }], ['path', { d: 'M9.5 9.5L14 14' }]],
        view: [['rect', { x: 2, y: 2, width: 5, height: 5 }], ['rect', { x: 9, y: 2, width: 5, height: 5 }],
            ['rect', { x: 2, y: 9, width: 5, height: 5 }], ['rect', { x: 9, y: 9, width: 5, height: 5 }]],
        nav: [['path', { d: 'M2 4H14M2 8H14M2 12H14' }]],
        panel: [['rect', { x: 2, y: 2, width: 12, height: 12 }], ['path', { d: 'M2 6H14' }]],
        macro: [['path', { d: 'M6 2C4 2 4 3 4 5V6.5C4 7.5 3 8 2 8C3 8 4 8.5 4 9.5V11C4 13 4 14 6 14' +
            'M10 2C12 2 12 3 12 5V6.5C12 7.5 13 8 14 8C13 8 12 8.5 12 9.5V11C12 13 12 14 10 14' }]],
        eventtype: [['path', { d: 'M9 1L3 9H8L7 15L13 7H8Z' }]],
        tag: [['path', { d: 'M2 2H8L14 8L8 14L2 8Z' }], ['circle', { cx: 5, cy: 5, r: 1 }]],
        extraction: [['path', { d: 'M5 2H2V14H5M11 2H14V14H11' }], ['circle', { cx: 8, cy: 8, r: 1.5 }]],
        fieldalias: [['path', { d: 'M2 5H13M10 2L13 5L10 8M14 11H3M6 8L3 11L6 14' }]],
        calcfield: [['rect', { x: 3, y: 1.5, width: 10, height: 13 }],
            ['path', { d: 'M5.5 4.5H10.5M5.5 9H7.5M6.5 8V10M8.5 9H10.5M8.5 11.5H10.5' }]],
        autolookup: [['path', { d: 'M13 8A5 5 0 1 1 11.5 4.5M13 2V5H10' }]],
        sourcetyperename: [['path', { d: 'M2 14L3 10.5L11 2.5L13.5 5L5.5 13ZM9.5 4L12 6.5' }]],
        transform: [['path', { d: 'M2 3H14L9.5 8.5V13L6.5 14.5V8.5Z' }]],
        lookupdef: [['rect', { x: 2, y: 3, width: 12, height: 10 }], ['path', { d: 'M2 7H14M6 7V13' }]],
        lookupfile: [['path', { d: 'M4 1.5H9.5L12.5 4.5V14.5H4ZM9.5 1.5V4.5H12.5M6 8H10.5M6 11H10.5' }]],
        workflow: [['path', { d: 'M9 2H14V7M14 2L7 9M12 10V14H2V4H6' }]],
        timerange: [['circle', { cx: 8, cy: 8, r: 6 }], ['path', { d: 'M8 4.5V8L10.5 9.5' }]],
        datamodel: [['path', { d: 'M8 1.5L14 4.5V11.5L8 14.5L2 11.5V4.5ZM2 4.5L8 7.5L14 4.5M8 7.5V14.5' }]],
        collection: [['ellipse', { cx: 8, cy: 4, rx: 5, ry: 2 }],
            ['path', { d: 'M3 4V12C3 13.1 5.2 14 8 14C10.8 14 13 13.1 13 12V4M3 8C3 9.1 5.2 10 8 10C10.8 10 13 9.1 13 8' }]],
        alertaction: [['path', { d: 'M4 11V7A4 4 0 0 1 12 7V11L13.5 12.5H2.5ZM6.5 14H9.5' }]],
        lock: [['rect', { x: 3.5, y: 7, width: 9, height: 7 }], ['path', { d: 'M5.5 7V5A2.5 2.5 0 0 1 10.5 5V7' }]]
    };

    // An inline SVG icon. ``label`` names it for assistive technology; without
    // one it is decorative and hidden from it.
    function icon(name, label) {
        var svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('viewBox', '0 0 16 16');
        svg.setAttribute('width', '16');
        svg.setAttribute('height', '16');
        svg.setAttribute('class', 'ea-icon ea-icon-' + name);
        svg.setAttribute('focusable', 'false');
        if (label) {
            svg.setAttribute('role', 'img');
            svg.setAttribute('aria-label', label);
            var title = document.createElementNS(SVG_NS, 'title');
            title.textContent = label;
            svg.appendChild(title);
        } else {
            svg.setAttribute('aria-hidden', 'true');
        }
        $.each(ICONS[name] || [], function (i, shape) {
            var node = document.createElementNS(SVG_NS, shape[0]);
            $.each(shape[1], function (attr, value) { node.setAttribute(attr, String(value)); });
            svg.appendChild(node);
        });
        return svg;
    }

    // ---------------------------------------------------------------- state

    var SHARING_LABELS = { user: 'Private', app: 'This app', global: 'All apps' };
    var SHARING_CHOICES = [
        ['user', 'Keep private (owner only)'],
        ['app', 'This app only'],
        ['global', 'All apps (global)']
    ];

    var state = {
        data: null,
        byKey: newMap(),       // object key -> object
        typeLabels: newMap(),  // type id -> label
        apps: newMap(),        // app name -> app
        pending: newMap(),     // object key -> {moveTo, acl, del}
        selected: newMap(),    // object key -> true
        details: newMap(),     // object key -> settings from the server, or 'loading' / {error}
        filter: '',
        type: '',
        showBuiltin: false,
        panel: null,           // {mode: 'object', key} or {mode: 'bulk'}
        busy: false,
        message: null,         // {kind: 'error' | 'success' | 'info', lines: [..]}
        dragKeys: null
    };

    function newMap() {
        return Object.create(null);
    }

    function size(map) {
        var count = 0;
        var name;
        for (name in map) { count += 1; }
        return count;
    }

    function keys(map) {
        var list = [];
        var name;
        for (name in map) { list.push(name); }
        return list;
    }

    function el(tag, className, text) {
        var $node = $(document.createElement(tag));
        if (className) { $node.addClass(className); }
        if (text !== undefined && text !== null) { $node.text(text); }
        return $node;
    }

    function plural(count, one, many) {
        return count + ' ' + (count === 1 ? one : (many || one + 's'));
    }

    function errorText(xhr) {
        var body = xhr && xhr.responseJSON;
        if (body && body.messages && body.messages.length && body.messages[0].text) {
            return body.messages[0].text;
        }
        if (xhr && xhr.status === 404) {
            return 'The Easy Admin endpoint was not found. Splunk must be restarted once after ' +
                'the app is installed or upgraded before the endpoint is registered.';
        }
        if (xhr && xhr.status) {
            return 'Request failed with HTTP ' + xhr.status + '. Reload to try again; if it keeps ' +
                'failing, see easyadmin.log on the search head.';
        }
        return 'Could not reach Splunk.';
    }

    function sameList(a, b) {
        if (a.length !== b.length) { return false; }
        var seen = newMap();
        $.each(a, function (i, item) { seen[item] = true; });
        for (var i = 0; i < b.length; i += 1) {
            if (!seen[b[i]]) { return false; }
        }
        return true;
    }

    // ------------------------------------------------------------- pending

    function currentAcl(obj) {
        return { sharing: obj.sharing, owner: obj.owner, read: obj.read.slice(), write: obj.write.slice() };
    }

    function sameAcl(a, b) {
        if (a.sharing !== b.sharing || a.owner !== b.owner) { return false; }
        if (a.sharing === 'user') { return true; }   // a private object has no role permissions
        return sameList(a.read, b.read) && sameList(a.write, b.write);
    }

    // The object's ACL as it will be once pending changes apply.
    function aclOf(obj) {
        var pending = state.pending[obj.key];
        return pending && pending.acl ? pending.acl : currentAcl(obj);
    }

    function appOf(obj) {
        var pending = state.pending[obj.key];
        return pending && pending.moveTo ? pending.moveTo : obj.app;
    }

    // Store one object's staged edits, dropping any that match what it is now.
    function setPending(obj, edits) {
        var pending = state.pending[obj.key] || { moveTo: null, acl: null, del: false };
        if ('moveTo' in edits) { pending.moveTo = edits.moveTo === obj.app ? null : edits.moveTo; }
        if ('acl' in edits) { pending.acl = edits.acl && !sameAcl(edits.acl, currentAcl(obj)) ? edits.acl : null; }
        if ('del' in edits) { pending.del = !!edits.del; }
        if (pending.del) { pending.moveTo = null; pending.acl = null; }
        if (pending.moveTo || pending.acl || pending.del) {
            state.pending[obj.key] = pending;
        } else {
            delete state.pending[obj.key];
        }
    }

    // An app as people see it: its label, with the directory name when different.
    function appText(name) {
        var app = state.apps[name];
        return app && app.label !== name ? app.label + ' (' + name + ')' : name;
    }

    // "1 object ships in its app's..." / "2 objects ship in their apps'...".
    function lockedText(count, what) {
        return plural(count, 'object') + (count === 1 ? ' ships in its app\'s' : ' ship in their apps\'') +
            ' default folder and cannot be ' + what + '; ' + (count === 1 ? 'it was' : 'they were') + ' left as ' +
            (count === 1 ? 'it is' : 'they are') + '.';
    }

    // Stage a move of each object that can be moved, and say what happened.
    function stageMove(objectKeys, app) {
        var moved = 0;
        var locked = 0;
        $.each(objectKeys, function (i, objKey) {
            var obj = state.byKey[objKey];
            if (!obj) { return; }
            if (!obj.movable) { locked += 1; return; }
            setPending(obj, { moveTo: app, del: false });
            if (state.pending[objKey] && state.pending[objKey].moveTo === app) { moved += 1; }
        });
        var lines = [];
        if (moved) {
            lines.push('Staged a move of ' + plural(moved, 'object') + ' to ' + appText(app) + '. Apply to make it.');
        } else if (!locked) {
            lines.push('Nothing to move: ' + (objectKeys.length === 1 ? 'the object is' : 'the objects are') +
                ' already in ' + appText(app) + '.');
        }
        if (locked) { lines.push(lockedText(locked, 'moved')); }
        state.message = { kind: 'info', lines: lines };
    }

    function collectChanges() {
        var changes = [];
        $.each(keys(state.pending), function (i, objKey) {
            var obj = state.byKey[objKey];
            var pending = state.pending[objKey];
            if (!obj) { return; }
            var change = { type: obj.type, ns: obj.ns, app: obj.app, name: obj.name };
            if (pending.del) {
                change['delete'] = true;
            } else {
                if (pending.moveTo) { change.move_to = pending.moveTo; }
                if (pending.acl) {
                    change.acl = { sharing: pending.acl.sharing, owner: pending.acl.owner,
                        read: pending.acl.read, write: pending.acl.write };
                }
            }
            changes.push(change);
        });
        return changes;
    }

    // ---------------------------------------------------------------- data

    function index(data) {
        state.byKey = newMap();
        state.typeLabels = newMap();
        state.apps = newMap();
        $.each(data.types, function (i, type) { state.typeLabels[type.id] = type.label; });
        $.each(data.apps, function (i, app) { state.apps[app.name] = app; });
        $.each(data.objects, function (i, obj) { state.byKey[obj.key] = obj; });
    }

    function load() {
        state.busy = true;
        state.busyText = state.data ? 'Reloading apps and knowledge objects...' : null;
        render();
        $.ajax({
            url: ENDPOINT,
            type: 'GET',
            dataType: 'json',
            data: { output_mode: 'json' },
            cache: false
        }).done(function (data) {
            if (matchSplunkTheme(data.theme)) {
                return;  // reloading in the right theme; nothing to render
            }
            state.data = data;
            index(data);
            state.details = newMap();
            // Staged changes for objects that no longer exist where they were
            // (moved, renamed or deleted elsewhere) cannot be applied.
            var dropped = 0;
            $.each(keys(state.pending), function (i, objKey) {
                var obj = state.byKey[objKey];
                if (!obj) {
                    delete state.pending[objKey];
                    dropped += 1;
                } else {
                    var pending = state.pending[objKey];
                    setPending(obj, { moveTo: pending.moveTo || obj.app, acl: pending.acl, del: pending.del });
                }
            });
            $.each(keys(state.selected), function (i, objKey) {
                if (!state.byKey[objKey]) { delete state.selected[objKey]; }
            });
            if (state.panel && state.panel.mode === 'object' && !state.byKey[state.panel.key]) {
                state.panel = null;
            }
            if (dropped) {
                var lines = state.message ? state.message.lines.slice() : [];
                lines.push(plural(dropped, 'staged change was', 'staged changes were') +
                    ' dropped because the object no longer exists where it was.');
                state.message = { kind: state.message ? state.message.kind : 'info', lines: lines };
            }
        }).fail(function (xhr) {
            state.message = { kind: 'error', lines: ['Could not load the apps. ' + errorText(xhr)] };
        }).always(function () {
            state.busy = false;
            render();
        });
    }

    function loadDetails(obj) {
        if (state.details[obj.key]) { return; }
        state.details[obj.key] = 'loading';
        $.ajax({
            url: ENDPOINT,
            type: 'GET',
            dataType: 'json',
            data: { output_mode: 'json', type: obj.type, ns: obj.ns, app: obj.app, name: obj.name },
            cache: false
        }).done(function (details) {
            state.details[obj.key] = details;
        }).fail(function (xhr) {
            state.details[obj.key] = { error: errorText(xhr) };
        }).always(function () {
            if (state.panel && state.panel.key === obj.key) { renderPanel(); }
        });
    }

    function apply() {
        var changes = collectChanges();
        if (!changes.length) { return; }
        var moves = 0;
        var acls = 0;
        var deletes = 0;
        $.each(changes, function (i, change) {
            if (change['delete']) { deletes += 1; }
            if (change.move_to) { moves += 1; }
            if (change.acl) { acls += 1; }
        });
        var parts = [];
        if (moves) { parts.push('move ' + plural(moves, 'object')); }
        if (acls) { parts.push('change the permissions of ' + plural(acls, 'object')); }
        if (deletes) { parts.push('delete ' + plural(deletes, 'object')); }
        var prompt = 'Apply changes to ' + plural(changes.length, 'object') + ': ' + parts.join(', ') + '?';
        if (deletes) {
            prompt += '\n\nDeleting cannot be undone.';
        }
        if (!window.confirm(prompt)) {
            return;
        }

        state.busy = true;
        state.busyText = 'Applying ' + plural(changes.length, 'change') + '...';
        state.message = null;
        render();
        $.ajax({
            url: ENDPOINT + '?output_mode=json',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ changes: changes }),
            dataType: 'json',
            // Splunk Web rejects a state-changing request without its CSRF token.
            headers: {
                'X-Splunk-Form-Key': splunkUtil.getFormKey(),
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).done(function (body) {
            var failures = [];
            $.each(body.results || [], function (i, result) {
                var obj = state.byKey[result.key];
                var pending = state.pending[result.key];
                if (result.status !== 'error') {
                    delete state.pending[result.key];
                    delete state.selected[result.key];
                    return;
                }
                failures.push(result.message);
                // Moved but not re-permissioned: keep the permission edit,
                // now addressed at the object's new app, so it can be retried.
                if (result.moved_to && obj && pending) {
                    delete state.pending[result.key];
                    var movedKey = [obj.type, obj.ns, result.moved_to, obj.name].join('\u0000');
                    if (pending.acl) {
                        state.pending[movedKey] = { moveTo: null, acl: pending.acl, del: false };
                    }
                }
            });
            if (body.failed) {
                state.message = { kind: 'error', lines: ['Applied ' + plural(body.applied, 'change') + '; ' +
                    plural(body.failed, 'object') + ' could not be changed and still show as staged:']
                    .concat(failures) };
            } else {
                state.message = { kind: 'success', lines: ['Applied changes to ' + plural(body.applied, 'object') + '.'] };
            }
            load();
        }).fail(function (xhr) {
            state.busy = false;
            state.message = { kind: 'error', lines: ['Nothing was applied. ' + errorText(xhr)] };
            render();
        });
    }

    // ----------------------------------------------------------- filtering

    function matches(obj) {
        if (state.type && obj.type !== state.type) { return false; }
        var needle = state.filter.toLowerCase();
        return !needle || obj.name.toLowerCase().indexOf(needle) !== -1;
    }

    // App name -> objects to show in its box, placed where pending moves put them.
    function objectsByApp() {
        var map = newMap();
        $.each(state.data.objects, function (i, obj) {
            if (!matches(obj)) { return; }
            var app = appOf(obj);
            (map[app] = map[app] || []).push(obj);
        });
        return map;
    }

    // The filter narrows objects, never apps: every app stays on show as a
    // place to drop objects (finding an object, then dragging it elsewhere,
    // is the main use). Only the built-in toggle hides boxes.
    function visibleApps(byApp) {
        return $.grep(state.data.apps, function (app) {
            if (byApp[app.name] && $.grep(byApp[app.name], function (obj) {
                return state.pending[obj.key];
            }).length) {
                return true;   // always show where staged changes are
            }
            return !(app.builtin && !state.showBuiltin);
        });
    }

    function targetApps() {
        return $.grep(state.data.apps, function (app) { return app.target; });
    }

    // ------------------------------------------------------------- render

    // Re-rendering replaces the DOM; keep the focused control and each box's
    // scroll position so typing in the filter or ticking a box is not lost.
    function snapshot() {
        var active = document.activeElement;
        var scroll = newMap();
        $root.find('.ea-objects').each(function () {
            scroll[this.getAttribute('data-app')] = this.scrollTop;
        });
        return {
            fid: active && $root[0].contains(active) ? active.getAttribute('data-fid') : null,
            caret: active && typeof active.selectionStart === 'number' ? active.selectionStart : null,
            scroll: scroll
        };
    }

    function restore(snap) {
        $root.find('.ea-objects').each(function () {
            var top = snap.scroll[this.getAttribute('data-app')];
            if (top) { this.scrollTop = top; }
        });
        if (!snap.fid) { return; }
        var found = $root.find('[data-fid]').filter(function () {
            return this.getAttribute('data-fid') === snap.fid;
        })[0];
        if (found) {
            found.focus();
            if (snap.caret !== null && typeof found.setSelectionRange === 'function') {
                try { found.setSelectionRange(snap.caret, snap.caret); } catch (ignore) { /* not a text field */ }
            }
        }
    }

    // Screen readers announce a live region's changes only when the region
    // was already in the page, so these two are created once, outside the
    // part each render rebuilds, and only their text changes (A5). The
    // visible messages below them carry no role, to avoid a double reading.
    var $liveStatus = el('div', 'ea-sr-only').attr({ role: 'status', 'aria-live': 'polite' });
    var $liveAlert = el('div', 'ea-sr-only').attr({ role: 'alert', 'aria-live': 'assertive' });
    var $body = el('div', 'ea-body');

    function announce() {
        var text = state.message ? state.message.lines.join(' ') : '';
        if (state.busy) { text = state.busyText || 'Loading apps and knowledge objects...'; }
        // Progress is never an alert, even while an error from Apply is kept.
        var error = !state.busy && state.message && state.message.kind === 'error';
        if ($liveAlert.text() !== (error ? text : '')) { $liveAlert.text(error ? text : ''); }
        if ($liveStatus.text() !== (error ? '' : text)) { $liveStatus.text(error ? '' : text); }
    }

    function renderMessages() {
        var $box = el('div', 'ea-messages');
        if (state.busy) {
            $box.append(el('div', 'ea-message ea-info ea-busy', state.busyText || 'Loading apps and knowledge objects...'));
        }
        if (state.message) {
            var $message = el('div', 'ea-message ea-' + state.message.kind);
            $.each(state.message.lines, function (i, line) { $message.append(el('div', null, line)); });
            $box.append($message);
        }
        if (!state.data && !state.busy) {
            // The first load failed: without data there is no toolbar, so
            // offer the way to try again here.
            $box.append(el('button', 'btn', 'Reload').attr({ type: 'button', 'data-fid': 'reload-failed' })
                .on('click', function () {
                    state.message = null;
                    load();
                }));
        }
        if (state.data && state.data.warnings.length) {
            var $warn = el('div', 'ea-message ea-info');
            $.each(state.data.warnings, function (i, line) { $warn.append(el('div', null, line)); });
            $box.append($warn);
        }
        return $box;
    }

    function appOptions($select, current, placeholder) {
        if (placeholder) { $select.append(el('option', null, placeholder).attr('value', '')); }
        $.each(targetApps(), function (i, app) {
            var text = app.label === app.name ? app.name : app.label + ' (' + app.name + ')';
            $select.append(el('option', null, text).attr('value', app.name));
        });
        $select.val(current || '');
        return $select;
    }

    function renderToolbar() {
        var $bar = el('div', 'ea-toolbar');
        $bar.append(el('input', 'ea-filter').attr({
            type: 'text', placeholder: 'Filter objects by name', 'aria-label': 'Filter objects by name',
            'data-fid': 'filter'
        }).val(state.filter).on('input', function () {
            state.filter = $(this).val();
            render();
        }));

        var $type = el('select', 'ea-type').attr({ 'aria-label': 'Object type', 'data-fid': 'type' });
        $type.append(el('option', null, 'All types').attr('value', ''));
        $.each(state.data.types, function (i, type) {
            $type.append(el('option', null, type.label).attr('value', type.id));
        });
        $type.val(state.type).on('change', function () {
            state.type = $(this).val();
            render();
        });
        $bar.append($type);

        var $builtin = el('label', 'ea-check');
        $builtin.append(el('input').attr({ type: 'checkbox', 'data-fid': 'builtin' })
            .prop('checked', state.showBuiltin).on('change', function () {
                state.showBuiltin = this.checked;
                render();
            }));
        $builtin.append(document.createTextNode(" Show Splunk's built-in apps"));
        $bar.append($builtin);

        var count = size(state.pending);
        var $actions = el('span', 'ea-actions');
        $actions.append(el('button', 'btn', 'Reload').attr({ type: 'button', 'data-fid': 'reload' })
            .prop('disabled', state.busy).on('click', function () {
                state.message = null;
                load();
            }));
        $actions.append(el('button', 'btn ea-discard', count ? 'Discard ' + plural(count, 'change') : 'Discard changes')
            .attr({ type: 'button', 'data-fid': 'discard' })
            .prop('disabled', state.busy || !count).on('click', function () {
                // Staged work can be large and is not recoverable: ask first.
                if (!window.confirm('Discard ' + plural(count, 'staged change') + '? Nothing has been applied yet.')) {
                    return;
                }
                state.pending = newMap();
                state.message = { kind: 'info', lines: ['Discarded ' + plural(count, 'staged change') + '.'] };
                render();
            }));
        $actions.append(el('button', 'btn btn-primary ea-apply', count ? 'Apply ' + plural(count, 'change') : 'Apply changes')
            .attr({ type: 'button', 'data-fid': 'apply' })
            .prop('disabled', state.busy || !count).on('click', apply));
        $bar.append($actions);
        return $bar;
    }

    function renderSelectionBar() {
        var count = size(state.selected);
        var $bar = el('div', 'ea-selection').attr('aria-label', 'Selected objects');
        if (!count) {
            $bar.append(el('span', 'ea-muted',
                'Tick objects to move, re-permission or delete several at once, or drag an object to another app.'));
            return $bar;
        }
        $bar.append(el('strong', null, plural(count, 'object') + ' selected'));
        var $target = appOptions(el('select', 'ea-move-target').attr({ 'aria-label': 'Move selected objects to app',
            'data-fid': 'move-target' }), '', 'Move to app...');
        $bar.append($target);
        $bar.append(el('button', 'btn', 'Move').attr({ type: 'button', 'data-fid': 'move-selected' }).on('click', function () {
            var app = $target.val();
            if (!app) {
                state.message = { kind: 'info', lines: ['Choose the app to move the selected objects to.'] };
                render();
                return;
            }
            stageMove(keys(state.selected), app);
            render();
        }));
        $bar.append(el('button', 'btn', 'Edit permissions').attr({ type: 'button', 'data-fid': 'bulk-acl' })
            .on('click', function () { openPanel({ mode: 'bulk' }); }));
        $bar.append(el('button', 'btn', 'Delete').attr({ type: 'button', 'data-fid': 'delete-selected' }).on('click', function () {
            var staged = 0;
            var locked = 0;
            $.each(keys(state.selected), function (i, objKey) {
                var obj = state.byKey[objKey];
                if (obj && obj.removable) {
                    setPending(obj, { del: true });
                    staged += 1;
                } else {
                    locked += 1;
                }
            });
            var lines = staged ? ['Staged ' + plural(staged, 'object') + ' for deletion. Apply to delete them.'] : [];
            if (locked) { lines.push(lockedText(locked, 'deleted')); }
            state.message = { kind: 'info', lines: lines };
            render();
        }));
        $bar.append(el('button', 'btn btn-link', 'Clear selection').attr({ type: 'button', 'data-fid': 'clear-selection' })
            .on('click', function () {
                state.selected = newMap();
                render();
            }));
        return $bar;
    }

    function renderLegend() {
        var $legend = el('div', 'ea-legend');
        var $types = el('ul', 'ea-legend-types').attr('aria-label', 'Object types');
        $.each(state.data.types, function (i, type) {
            var $item = el('li');
            $item.append(icon(type.id), document.createTextNode(' ' + type.label));
            $types.append($item);
        });
        $legend.append($types);
        var $note = el('p', 'ea-muted');
        $note.append(icon('lock'), document.createTextNode(
            ' ships in the app\'s default folder: it can be re-permissioned, not moved or deleted. ' +
            'Staged changes are outlined and labelled until you apply them.'));
        $legend.append($note);
        return $legend;
    }

    function changeBadges(obj) {
        var pending = state.pending[obj.key];
        var badges = [];
        if (!pending) { return badges; }
        if (pending.del) { badges.push('will be deleted'); }
        if (pending.moveTo) { badges.push('moving from ' + obj.app); }
        if (pending.acl) { badges.push('permissions changed'); }
        return badges;
    }

    function renderObject(obj) {
        var pending = state.pending[obj.key];
        var acl = aclOf(obj);
        var typeLabel = state.typeLabels[obj.type] || obj.type;
        var $li = el('li', 'ea-object').attr('data-key', obj.key);
        if (pending) { $li.addClass('ea-changed'); }
        if (pending && pending.del) { $li.addClass('ea-deleted'); }
        if (obj.movable) { $li.attr('draggable', 'true'); }

        $li.append(el('input', 'ea-select').attr({
            type: 'checkbox', 'aria-label': 'Select ' + typeLabel.toLowerCase() + ' ' + obj.name,
            'data-fid': 'sel:' + obj.key
        }).prop('checked', !!state.selected[obj.key]));
        $li.append(icon(obj.type, typeLabel));
        $li.append(el('button', 'ea-object-name', obj.name).attr({
            type: 'button', title: typeLabel + ': ' + obj.name + ' (owner ' + obj.owner + ')',
            'data-fid': 'open:' + obj.key
        }));
        var $tags = el('span', 'ea-tags');
        if (!obj.movable && !obj.removable) {
            $tags.append(el('span', 'ea-badge ea-locked').attr('title',
                'Ships in the app\'s default folder: cannot be moved or deleted.').append(icon('lock'), document.createTextNode(' default')));
        }
        $tags.append(el('span', 'ea-badge', SHARING_LABELS[acl.sharing] || acl.sharing));
        if (obj.disabled) { $tags.append(el('span', 'ea-badge', 'disabled')); }
        $.each(changeBadges(obj), function (i, text) {
            $tags.append(el('span', 'ea-badge ea-badge-changed', text));
        });
        $li.append($tags);
        return $li;
    }

    function renderApp(app, objects) {
        var $box = el('section', 'ea-app').attr({ 'data-app': app.name, 'aria-label': 'App ' + app.label });
        if (!app.target) { $box.addClass('ea-app-fixed'); }
        if (!objects.length) { $box.addClass('ea-app-empty'); }
        var $head = el('header', 'ea-app-head');
        var $title = el('h3', 'ea-app-title', app.label).attr('title', app.label + ' (' + app.name + ')');
        $head.append($title);
        var $meta = el('div', 'ea-app-meta');
        $meta.append(el('code', null, app.name));
        $meta.append(el('span', null, state.filter || state.type ?
            plural(objects.length, 'match', 'matches') : plural(objects.length, 'object')));
        if (app.builtin) { $meta.append(el('span', 'ea-badge', 'built-in')); }
        if (app.disabled) { $meta.append(el('span', 'ea-badge', 'disabled')); }
        if (!app.target) {
            $meta.append(el('span', 'ea-badge').text('not a destination').attr('title',
                app.name === 'system' ? 'Objects in etc/system are not in an app; nothing can be moved here.' :
                    'This app is not listed for your account; nothing can be moved here.'));
        }
        $head.append($meta);
        $box.append($head);

        var $list = el('ul', 'ea-objects').attr({ 'data-app': app.name, 'aria-label': 'Objects in ' + app.label });
        if (!objects.length) {
            $list.append(el('li', 'ea-empty', state.filter || state.type ?
                'No matching objects.' + (app.target ? ' Drop objects here to move them.' : '') :
                'No knowledge objects visible to your account.'));
        }
        $.each(objects, function (i, obj) { $list.append(renderObject(obj)); });
        $box.append($list);
        return $box;
    }

    function renderGrid() {
        var byApp = objectsByApp();
        var apps = visibleApps(byApp);
        var $wrap = el('div', 'ea-grid-wrap');
        var hidden = state.data.apps.length - apps.length;
        var filtered = state.filter || state.type;
        var shown = 0;
        $.each(apps, function (i, app) { shown += (byApp[app.name] || []).length; });
        var summary = 'Showing ' + plural(apps.length, 'app') + (filtered ? ' and ' +
            plural(shown, 'matching object') : '') + '.';
        if (hidden) {
            summary += ' ' + plural(hidden, 'built-in app is', 'built-in apps are') +
                ' hidden; tick "Show Splunk\'s built-in apps" to see them.';
        }
        $wrap.append(el('p', 'ea-muted ea-summary', summary));
        if (filtered && !shown) {
            var what = state.type ? state.typeLabels[state.type].toLowerCase() + ' objects' : 'objects';
            $wrap.append(el('p', 'ea-message ea-info', 'No ' + what + (state.filter ? ' match the filter "' +
                state.filter + '"' : ' found') + (hidden ? ' in the apps shown.' : '.')));
        }
        if (!apps.length) {
            $wrap.append(el('p', 'ea-empty', 'No apps are visible to your account.'));
            return $wrap;
        }
        var $grid = el('div', 'ea-grid');
        $.each(apps, function (i, app) { $grid.append(renderApp(app, byApp[app.name] || [])); });
        return $wrap.append($grid);
    }

    // ---------------------------------------------------------------- panel

    function aclEditor(acl, enabled, prefix, onChange) {
        var $editor = el('div', 'ea-acl');
        var roles = ['*'].concat(state.data.roles);
        $.each(acl.read.concat(acl.write), function (i, role) {
            if ($.inArray(role, roles) === -1) { roles.push(role); }
        });
        var $table = el('table', 'ea-perms');
        var $head = el('tr');
        $head.append(el('th', null, 'Role'), el('th', null, 'Read'), el('th', null, 'Write'));
        $table.append(el('thead').append($head));
        var $body = el('tbody');
        $.each(roles, function (i, role) {
            var label = role === '*' ? 'Everyone (*)' : role;
            var $tr = el('tr').append(el('th', null, label).attr('scope', 'row'));
            $.each(['read', 'write'], function (j, kind) {
                $tr.append(el('td').append(el('input').attr({
                    type: 'checkbox', 'aria-label': kind + ' / ' + label, 'data-fid': prefix + kind + ':' + role
                }).prop({ checked: $.inArray(role, acl[kind]) !== -1, disabled: !enabled }).on('change', function () {
                    var list = $.grep(acl[kind], function (r) { return r !== role; });
                    if (this.checked) { list.push(role); }
                    var next = $.extend({}, acl);
                    next[kind] = list;
                    onChange(next);
                })));
            });
            $body.append($tr);
        });
        $editor.append($table.append($body));
        return $editor;
    }

    function ownerField(value, enabled, fid, onChange) {
        var listId = 'ea-users-list';
        var $input = el('input').attr({ type: 'text', list: listId, 'data-fid': fid, id: 'ea-owner',
            spellcheck: 'false' }).val(value).prop('disabled', !enabled);
        var $error = el('div', 'ea-field-error').attr({ id: 'ea-owner-error', role: 'alert' });
        $input.on('change', function () {
            var owner = $.trim($input.val());
            if (!owner) {
                $error.text('Owner is required. Use nobody for an object no one owns.');
                $input.attr({ 'aria-invalid': 'true', 'aria-describedby': 'ea-owner-error' });
                return;
            }
            onChange(owner);
        });
        var $list = el('datalist').attr('id', listId);
        $.each(['nobody'].concat(state.data.users), function (i, user) {
            $list.append(el('option').attr('value', user));
        });
        return el('div', 'ea-field').append(el('label', null, 'Owner').attr('for', 'ea-owner'), $input, $list, $error);
    }

    function sharingField(value, obj, enabled, fid, onChange, placeholder) {
        var $select = el('select').attr({ id: 'ea-sharing', 'data-fid': fid }).prop('disabled', !enabled);
        if (placeholder) { $select.append(el('option', null, placeholder).attr('value', '')); }
        $.each(SHARING_CHOICES, function (i, choice) {
            var $option = el('option', null, choice[1]).attr('value', choice[0]);
            if (obj && ((choice[0] === 'global' && !obj.can_share_global) || (choice[0] === 'app' && !obj.can_share_app))) {
                $option.prop('disabled', true);
            }
            $select.append($option);
        });
        $select.val(value).on('change', function () { onChange($select.val()); });
        var $field = el('div', 'ea-field').append(el('label', null, 'Sharing').attr('for', 'ea-sharing'), $select);
        // Say why a sharing level is unavailable rather than only greying it (S5).
        if (obj && enabled && (!obj.can_share_global || !obj.can_share_app)) {
            $field.append(el('div', 'ea-muted', 'Your account cannot share this object ' +
                (!obj.can_share_app ? 'with this app' + (!obj.can_share_global ? ' or ' : '') : '') +
                (!obj.can_share_global ? 'with all apps' : '') + ', so that choice is unavailable.'));
        }
        return $field;
    }

    function renderObjectPanel($panel, obj) {
        var typeLabel = state.typeLabels[obj.type] || obj.type;
        var pending = state.pending[obj.key];
        var acl = aclOf(obj);
        var $title = el('h2', 'ea-panel-title').attr({ tabindex: '-1', id: 'ea-panel-title' });
        $title.append(icon(obj.type, typeLabel), document.createTextNode(' ' + obj.name));
        $panel.append($title);
        $panel.append(el('p', 'ea-muted', typeLabel + ' in ' + appText(obj.app) + (obj.sharing === 'user' ? ', private to ' + obj.owner : '')));

        if (pending) {
            $panel.append(el('p', 'ea-badge ea-badge-changed ea-panel-state',
                'Staged: ' + changeBadges(obj).join(', ') + '. Apply to make the change.'));
        }

        var rerender = function () { render(); };

        // App (move)
        var $app = appOptions(el('select').attr({ id: 'ea-app', 'data-fid': 'panel-app' }), appOf(obj))
            .prop('disabled', !obj.movable || (pending && pending.del));
        if ($.inArray(obj.app, $.map(targetApps(), function (a) { return a.name; })) === -1) {
            $app.prepend(el('option', null, obj.app).attr('value', obj.app));
            $app.val(appOf(obj));
        }
        $app.on('change', function () {
            setPending(obj, { moveTo: $app.val() });
            rerender();
        });
        var $appField = el('div', 'ea-field').append(el('label', null, 'App').attr('for', 'ea-app'), $app);
        if (!obj.movable) {
            $appField.append(el('div', 'ea-muted', 'Ships in this app\'s default folder, so it cannot be moved or ' +
                'deleted. Its permissions can still be changed.'));
        }
        $panel.append($appField);

        var aclEnabled = obj.can_change_perms && !(pending && pending.del);
        var setAcl = function (next) {
            setPending(obj, { acl: next });
            rerender();
        };
        $panel.append(el('h3', null, 'Permissions'));
        if (!obj.can_change_perms) {
            $panel.append(el('p', 'ea-muted', 'Your account cannot change the permissions of this object.'));
        }
        $panel.append(sharingField(acl.sharing, obj, aclEnabled, 'panel-sharing', function (sharing) {
            setAcl($.extend({}, acl, { sharing: sharing }));
        }));
        $panel.append(ownerField(acl.owner, aclEnabled, 'panel-owner', function (owner) {
            setAcl($.extend({}, acl, { owner: owner }));
        }));
        if (acl.sharing === 'user') {
            $panel.append(el('p', 'ea-muted', 'A private object is visible only to its owner; it has no role permissions.'));
        } else {
            $panel.append(aclEditor(acl, aclEnabled, 'panel-', setAcl));
        }

        var $actions = el('div', 'ea-panel-actions');
        if (pending && pending.del) {
            $actions.append(el('button', 'btn', 'Keep this object').attr({ type: 'button', 'data-fid': 'panel-undelete' })
                .on('click', function () { setPending(obj, { del: false }); rerender(); }));
        } else {
            $actions.append(el('button', 'btn ea-danger', 'Delete object').attr({ type: 'button', 'data-fid': 'panel-delete' })
                .prop('disabled', !obj.removable)
                .attr('title', obj.removable ? 'Stage this object for deletion' : 'Objects in the default folder cannot be deleted')
                .on('click', function () { setPending(obj, { del: true }); rerender(); }));
        }
        if (pending) {
            $actions.append(el('button', 'btn', 'Undo staged changes').attr({ type: 'button', 'data-fid': 'panel-undo' })
                .on('click', function () { delete state.pending[obj.key]; rerender(); }));
        }
        $panel.append($actions);

        $panel.append(el('h3', null, 'Settings'));
        var details = state.details[obj.key];
        if (!details || details === 'loading') {
            $panel.append(el('p', 'ea-muted', 'Loading settings...'));
            loadDetails(obj);
        } else if (details.error) {
            $panel.append(el('p', 'ea-message ea-error', 'Could not load the settings. ' + details.error));
        } else if (!details.settings.length) {
            $panel.append(el('p', 'ea-muted', 'This object has no settings to show.'));
        } else {
            var $dl = el('dl', 'ea-settings');
            $.each(details.settings, function (i, setting) {
                $dl.append(el('dt', null, setting.name));
                $dl.append(el('dd', null, setting.value + (setting.truncated ? ' ... (shortened)' : '')));
            });
            $panel.append($dl);
        }
    }

    function renderBulkPanel($panel) {
        var selected = $.map(keys(state.selected), function (k) { return state.byKey[k] || null; });
        var editable = $.grep(selected, function (obj) { return obj.can_change_perms; });
        var draft = state.panel.draft = state.panel.draft || { sharing: '', owner: '', perms: false,
            acl: { sharing: 'app', owner: '', read: ['*'], write: [] } };
        var canStage = function () {
            return editable.length > 0 && !!(draft.sharing || draft.owner || draft.perms);
        };
        $panel.append(el('h2', 'ea-panel-title', 'Permissions for ' + plural(selected.length, 'selected object'))
            .attr({ tabindex: '-1', id: 'ea-panel-title' }));
        $panel.append(el('p', 'ea-muted', 'Fields left unchanged keep each object\'s own value. ' +
            (selected.length - editable.length ? plural(selected.length - editable.length, 'object') +
                ' cannot be re-permissioned by your account and will be skipped.' : '')));

        $panel.append(sharingField(draft.sharing, null, true, 'bulk-sharing', function (sharing) {
            draft.sharing = sharing;
            renderPanel();
        }, 'Leave unchanged'));
        var $owner = el('input').attr({ type: 'text', list: 'ea-users-list', id: 'ea-owner', 'data-fid': 'bulk-owner',
            placeholder: 'Leave unchanged', spellcheck: 'false' }).val(draft.owner)
            .on('input', function () {
                draft.owner = $.trim($owner.val());
                $root.find('[data-fid="bulk-stage"]').prop('disabled', !canStage());
            });
        var $list = el('datalist').attr('id', 'ea-users-list');
        $.each(['nobody'].concat(state.data.users), function (i, user) { $list.append(el('option').attr('value', user)); });
        $panel.append(el('div', 'ea-field').append(el('label', null, 'Owner').attr('for', 'ea-owner'), $owner, $list));

        var $perms = el('label', 'ea-check');
        $perms.append(el('input').attr({ type: 'checkbox', 'data-fid': 'bulk-perms' }).prop('checked', draft.perms)
            .on('change', function () { draft.perms = this.checked; renderPanel(); }));
        $perms.append(document.createTextNode(' Replace read and write roles'));
        $panel.append($perms);
        if (draft.perms) {
            $panel.append(aclEditor(draft.acl, true, 'bulk-', function (next) {
                draft.acl = next;
                renderPanel();
            }));
            $panel.append(el('p', 'ea-muted', 'Role permissions do not apply to objects that end up private.'));
        }

        var $actions = el('div', 'ea-panel-actions');
        $actions.append(el('button', 'btn btn-primary', 'Stage for ' + plural(editable.length, 'object'))
            .attr({ type: 'button', 'data-fid': 'bulk-stage' })
            .prop('disabled', !canStage())
            .on('click', function () {
                var staged = 0;
                var refused = 0;
                $.each(editable, function (i, obj) {
                    // A sharing level splunkd says this object cannot take
                    // would only fail at Apply; skip it now and say so.
                    if ((draft.sharing === 'global' && !obj.can_share_global) ||
                            (draft.sharing === 'app' && !obj.can_share_app)) {
                        refused += 1;
                        return;
                    }
                    var acl = aclOf(obj);
                    var next = $.extend({}, acl);
                    if (draft.sharing) { next.sharing = draft.sharing; }
                    if (draft.owner) { next.owner = draft.owner; }
                    if (draft.perms) { next.read = draft.acl.read.slice(); next.write = draft.acl.write.slice(); }
                    setPending(obj, { acl: next });
                    // setPending drops an edit that matches the object as it is.
                    if (state.pending[obj.key] && state.pending[obj.key].acl) { staged += 1; }
                });
                var lines = staged ? ['Staged permission changes for ' + plural(staged, 'object') +
                    '. Apply to make them.'] : ['Nothing was staged.'];
                if (refused) {
                    lines.push(plural(refused, 'object') + ' cannot be shared that way by your account and ' +
                        (refused === 1 ? 'was' : 'were') + ' left unchanged.');
                }
                state.message = { kind: 'info', lines: lines };
                closePanel();
            }));
        $actions.append(el('button', 'btn', 'Cancel').attr({ type: 'button', 'data-fid': 'bulk-cancel' })
            .on('click', closePanel));
        $panel.append($actions);
    }

    function renderPanel() {
        var snap = snapshot();
        buildPanel();
        restore(snap);
    }

    function buildPanel() {
        $root.find('.ea-panel').remove();
        if (!state.panel || !state.data) { return; }
        var $panel = el('aside', 'ea-panel').attr({ role: 'dialog', 'aria-labelledby': 'ea-panel-title' });
        $panel.append(el('button', 'btn btn-link ea-panel-close', 'Close').attr({ type: 'button', 'data-fid': 'panel-close' })
            .on('click', closePanel));
        if (state.panel.mode === 'object') {
            renderObjectPanel($panel, state.byKey[state.panel.key]);
        } else {
            renderBulkPanel($panel);
        }
        $root.append($panel);
    }

    function openPanel(panel) {
        state.panel = panel;
        state.returnFocus = document.activeElement;
        renderPanel();
        $root.find('#ea-panel-title').focus();
    }

    function closePanel() {
        var returnTo = state.returnFocus;
        state.panel = null;
        render();
        if (returnTo && returnTo.getAttribute) {
            var fid = returnTo.getAttribute('data-fid');
            var found = $root.find('[data-fid]').filter(function () { return this.getAttribute('data-fid') === fid; })[0];
            if (found) { found.focus(); }
        }
    }

    function render() {
        $root.toggleClass('ea-dark', splunkIsDark());
        if (!$body[0].parentNode) {
            // First render: replace the view's "Loading..." text with the
            // persistent live regions and the body that renders rebuild.
            $root.empty().append($liveStatus, $liveAlert, $body);
        }
        var snap = snapshot();
        $body.empty();
        announce();
        if (!state.data) {
            $body.append(renderMessages());
            return;
        }
        $body.append(renderToolbar());
        $body.append(renderMessages());
        $body.append(renderSelectionBar());
        $body.append(renderLegend());
        $body.append(renderGrid());
        buildPanel();
        restore(snap);
    }

    // --------------------------------------------------------------- events

    $root.on('change', '.ea-select', function () {
        var objKey = $(this).closest('.ea-object').attr('data-key');
        if (this.checked) { state.selected[objKey] = true; } else { delete state.selected[objKey]; }
        $root.find('.ea-selection').replaceWith(renderSelectionBar());
    });

    $root.on('click', '.ea-object-name', function () {
        var objKey = $(this).closest('.ea-object').attr('data-key');
        openPanel({ mode: 'object', key: objKey });
    });

    // Drag and drop. Dragging a selected object carries every selected one;
    // dragging an unselected one carries just that object.
    $root.on('dragstart', '.ea-object[draggable="true"]', function (event) {
        var objKey = this.getAttribute('data-key');
        state.dragKeys = state.selected[objKey] ? keys(state.selected) : [objKey];
        var transfer = event.originalEvent.dataTransfer;
        transfer.effectAllowed = 'move';
        // Firefox starts a drag only when some data is set.
        transfer.setData('text/plain', state.byKey[objKey] ? state.byKey[objKey].name : '');
        $(this).addClass('ea-dragging');
    });

    $root.on('dragend', '.ea-object', function () {
        state.dragKeys = null;
        $(this).removeClass('ea-dragging');
        $root.find('.ea-drop').removeClass('ea-drop');
    });

    $root.on('dragover', '.ea-app', function (event) {
        var app = state.apps[this.getAttribute('data-app')];
        if (!state.dragKeys || !app || !app.target) { return; }
        event.preventDefault();   // marks the box as a valid drop target
        event.originalEvent.dataTransfer.dropEffect = 'move';
        $(this).addClass('ea-drop');
    });

    $root.on('dragleave', '.ea-app', function (event) {
        if (!this.contains(event.originalEvent.relatedTarget)) { $(this).removeClass('ea-drop'); }
    });

    $root.on('drop', '.ea-app', function (event) {
        event.preventDefault();
        var app = this.getAttribute('data-app');
        var dragged = state.dragKeys || [];
        state.dragKeys = null;
        stageMove(dragged, app);
        render();
    });

    $(document).on('keydown', function (event) {
        if (event.which === 27 && state.panel) { closePanel(); }
    });

    // Leaving with staged changes silently discards them; let the browser ask.
    $(window).on('beforeunload', function () {
        if (size(state.pending)) {
            return 'There are staged changes that have not been applied.';
        }
        return undefined;
    });

    load();
});
