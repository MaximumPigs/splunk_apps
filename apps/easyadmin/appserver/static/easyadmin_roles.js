/*
 * Easy Admin - role management page.
 *
 * Renders the role model returned by the app's REST endpoint as tabs:
 *
 *   matrix tabs    a grid of checkboxes, roles down the side and items
 *                  (indexes, capabilities, roles) across the top
 *   settings tabs  a grid of fields, roles down the side and settings across
 *
 * It tracks every cell the user has changed, on every tab, and submits all of
 * them in one request.
 *
 * Rendering only: what a cell means, validation and the writes themselves all
 * live server-side in bin/easyadmin_core.py, where they are unit tested.
 *
 * Every name and value shown here comes from the server and is inserted with
 * text(), val() or attr(), never as HTML, so a role, index or setting with
 * markup in it cannot inject script into an administrator's session.
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
    var ENDPOINT = splunkUtil.make_url('/splunkd/__raw/services/easyadmin/roles');
    // Joins role, field and item into one key. NUL cannot occur in any of them.
    var SEP = '\u0000';

    var $root = $('#easyadmin-roles');

    // ---------------------------------------------------------------- theme
    //
    // The page follows the user's theme preference. Classic dashboards do
    // not pick it up on their own, so the page reloads with ?theme= when
    // Splunk drew the other theme (matchSplunkTheme). The panel's palette
    // then matches whatever Splunk drew, by measuring the background behind
    // it rather than depending on how a given Splunk version marks its dark
    // theme in the DOM.

    // Relative luminance of an "rgb(...)"/"rgba(...)" colour, or null when it
    // is transparent or unreadable.
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

    // True when the first opaque background behind the panel is dark.
    function splunkIsDark() {
        var node = $root[0] && $root[0].parentNode;
        while (node && node.nodeType === 1) {
            var lum = luminance(window.getComputedStyle(node).backgroundColor);
            if (lum !== null) { return lum < 0.2; }
            node = node.parentNode;
        }
        return false;
    }

    // Value of a query-string parameter in the page URL, or null.
    function urlParam(name) {
        var match = new RegExp('[?&]' + name + '=([^&#]*)').exec(window.location.search);
        return match ? decodeURIComponent(match[1].replace(/\+/g, ' ')) : null;
    }

    // Classic dashboards take their theme from the dashboard itself or the
    // ?theme= URL parameter, not from the user's theme preference. When the
    // preference (from the app's endpoint) is light or dark and Splunk drew
    // the other one, reload once with ?theme=<preference>. Returns true when
    // a reload is under way.
    //
    // Loop guard: if the URL already asks for the preferred theme, never
    // reload again, even if the page still looks wrong.
    function matchSplunkTheme(preference) {
        if (preference !== 'light' && preference !== 'dark') { return false; }
        if (urlParam('theme') === preference) { return false; }
        if (splunkIsDark() === (preference === 'dark')) { return false; }
        var search = window.location.search.replace(/([?&])theme=[^&#]*&?/, '$1').replace(/[?&]$/, '');
        search += (search ? '&' : '?') + 'theme=' + encodeURIComponent(preference);
        window.location.replace(window.location.pathname + search + window.location.hash);
        return true;
    }

    function applyTheme() {
        $root.toggleClass('ea-dark', splunkIsDark());
    }

    var state = {
        data: null,          // last model from the server
        tabId: null,         // the tab on show
        fieldByTab: {},      // matrix tab id -> the attribute it is showing
        filterByTab: {},     // tab id -> filter text
        extraColumns: {},    // matrix tab id -> names typed in by the user
        matrixPending: newMap(),   // role+field+item -> true (grant) / false (revoke)
        settingsPending: newMap(), // role+field -> {value, previous}
        explicit: newMap(),  // role+field+item -> true for entries listed on the role
        busy: false,
        message: null        // {kind: 'error' | 'success' | 'info', lines: [..]}
    };

    // A prototype-less object, so an item called "constructor" is just a key.
    function newMap() {
        return Object.create(null);
    }

    function key() {
        return Array.prototype.join.call(arguments, SEP);
    }

    function size(map) {
        var count = 0;
        var name;
        for (name in map) { count += 1; }
        return count;
    }

    function pendingCount() {
        return size(state.matrixPending) + size(state.settingsPending);
    }

    function el(tag, className, text) {
        var $node = $(document.createElement(tag));
        if (className) { $node.addClass(className); }
        if (text !== undefined && text !== null) { $node.text(text); }
        return $node;
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
            return 'Request failed with HTTP ' + xhr.status + '.';
        }
        return 'Could not reach Splunk.';
    }

    function currentTab() {
        var found = null;
        $.each(state.data.tabs, function (i, tab) {
            if (tab.id === state.tabId) { found = tab; }
        });
        return found;
    }

    // Lists are compared as sets: splunkd stores them sorted, not as written.
    function sameList(a, b) {
        if (a.length !== b.length) { return false; }
        var seen = newMap();
        $.each(a, function (i, item) { seen[item] = true; });
        for (var i = 0; i < b.length; i += 1) {
            if (!seen[b[i]]) { return false; }
        }
        return true;
    }

    function parseList(text) {
        var items = [];
        $.each(String(text).split(','), function (i, part) {
            part = $.trim(part);
            if (part && $.inArray(part, items) === -1) { items.push(part); }
        });
        return items;
    }

    // ---------------------------------------------------------------- data

    function indexExplicit(data) {
        var map = newMap();
        $.each(data.tabs, function (i, tab) {
            if (tab.type !== 'matrix') { return; }
            $.each(tab.cells, function (role, fields) {
                $.each(fields, function (field, cell) {
                    $.each(cell.explicit, function (k, item) {
                        map[key(role, field, item)] = true;
                    });
                });
            });
        });
        return map;
    }

    function settingValue(role, field) {
        var found = null;
        $.each(state.data.tabs, function (i, tab) {
            if (tab.type === 'settings' && tab.values[role] && tab.values[role][field]) {
                found = tab.values[role][field].value;
            }
        });
        return found;
    }

    function load() {
        state.busy = true;
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
            state.explicit = indexExplicit(data);
            if (!state.tabId && data.tabs.length) {
                state.tabId = data.tabs[0].id;
            }
            $.each(data.tabs, function (i, tab) {
                if (tab.type === 'matrix' && !state.fieldByTab[tab.id]) {
                    state.fieldByTab[tab.id] = tab.fields[0].name;
                }
            });
            // A pending change the server state now already satisfies is no
            // longer a change (someone else made it, or the save applied it).
            var name;
            for (name in state.matrixPending) {
                if (state.matrixPending[name] === (state.explicit[name] === true)) {
                    delete state.matrixPending[name];
                }
            }
            for (name in state.settingsPending) {
                var parts = name.split(SEP);
                var now = settingValue(parts[0], parts[1]);
                var wanted = state.settingsPending[name].value;
                if (now !== null && ($.isArray(now) ? sameList(now, wanted) : now === wanted)) {
                    delete state.settingsPending[name];
                }
            }
        }).fail(function (xhr) {
            state.message = { kind: 'error', lines: [errorText(xhr)] };
        }).always(function () {
            state.busy = false;
            render();
        });
    }

    function collectChanges() {
        var changes = [];
        var name;
        var parts;
        for (name in state.matrixPending) {
            parts = name.split(SEP);
            changes.push({ role: parts[0], field: parts[1], item: parts[2],
                grant: state.matrixPending[name] });
        }
        for (name in state.settingsPending) {
            parts = name.split(SEP);
            changes.push({ role: parts[0], field: parts[1],
                value: state.settingsPending[name].value,
                previous: state.settingsPending[name].previous });
        }
        return changes;
    }

    function save() {
        var changes = collectChanges();
        if (!changes.length) { return; }

        var roles = newMap();
        $.each(changes, function (i, change) { roles[change.role] = true; });
        var own = $.grep(state.data.user_roles || [], function (role) { return roles[role]; });

        // Role edits take effect immediately for every user holding the role,
        // so make the size of the submit explicit before it happens. Editing a
        // role you hold yourself can remove your own access, so say so.
        var prompt = 'Apply ' + changes.length + ' change(s) to ' + size(roles) + ' role(s)?';
        if (own.length) {
            prompt += '\n\nThis changes role(s) you hold yourself (' + own.join(', ') +
                '). Removing capabilities from them can lock you out of this page.';
        }
        if (!window.confirm(prompt)) {
            return;
        }

        state.busy = true;
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
            var failed = newMap();
            var lines = [];
            $.each(body.results || [], function (i, result) {
                if (result.status === 'error') {
                    failed[result.role] = true;
                    lines.push(result.role + ': ' + result.message);
                }
            });
            // Keep the edits for roles that failed, so they can be retried or
            // corrected; everything else has been applied.
            $.each([state.matrixPending, state.settingsPending], function (i, map) {
                var pendingName;
                for (pendingName in map) {
                    if (!failed[pendingName.split(SEP)[0]]) {
                        delete map[pendingName];
                    }
                }
            });
            if (body.failed) {
                lines.unshift('Updated ' + body.updated + ' role(s); ' + body.failed +
                    ' could not be updated and still show as unsaved:');
                state.message = { kind: 'error', lines: lines };
            } else {
                state.message = { kind: 'success', lines: ['Updated ' + body.updated + ' role(s).'] };
            }
            load();
        }).fail(function (xhr) {
            state.busy = false;
            state.message = { kind: 'error', lines: ['Nothing was saved. ' + errorText(xhr)] };
            render();
        });
    }

    // -------------------------------------------------------------- render

    var KIND_LABELS = {
        wildcard: 'wildcard',
        unknown: 'not known here',
        added: 'added here'
    };

    function updateSaveButtons() {
        var count = pendingCount();
        $root.find('.ea-save').prop('disabled', state.busy || !count)
            .text(count ? 'Save ' + count + ' change(s)' : 'Save changes');
        $root.find('.ea-discard').prop('disabled', state.busy || !count);
    }

    function renderTabs() {
        var $tabs = el('div', 'ea-tabs').attr('role', 'tablist');
        $.each(state.data.tabs, function (i, tab) {
            var count = 0;
            var name;
            var fields = newMap();
            $.each(tab.fields, function (j, field) { fields[field.name] = true; });
            $.each([state.matrixPending, state.settingsPending], function (j, map) {
                for (name in map) {
                    if (fields[name.split(SEP)[1]]) { count += 1; }
                }
            });
            var $tab = el('button', 'ea-tab', tab.label).attr({
                type: 'button', role: 'tab', 'aria-selected': tab.id === state.tabId ? 'true' : 'false'
            }).toggleClass('ea-tab-active', tab.id === state.tabId).on('click', function () {
                state.tabId = tab.id;
                render();
            });
            if (count) { $tab.append(el('span', 'ea-tab-count', String(count))); }
            $tabs.append($tab);
        });
        return $tabs;
    }

    function renderToolbar(tab) {
        var $bar = el('div', 'ea-toolbar');
        var canEdit = state.data.can_edit;

        if (tab.type === 'matrix') {
            if (tab.fields.length > 1) {
                var $field = el('select', 'ea-field').attr('aria-label', 'Attribute');
                $.each(tab.fields, function (i, field) {
                    $field.append(el('option', null, field.label + ' (' + field.name + ')')
                        .attr('value', field.name));
                });
                $field.val(state.fieldByTab[tab.id]).on('change', function () {
                    state.fieldByTab[tab.id] = $(this).val();
                    render();
                });
                $bar.append(el('label', 'ea-label', 'Show ')).append($field);
            } else {
                $bar.append(el('span', 'ea-label', tab.fields[0].label + ' (' + tab.fields[0].name + ')'));
            }
        }

        var $filter = el('input', 'ea-filter')
            .attr({ type: 'text', placeholder: tab.type === 'matrix' ? 'Filter columns' : 'Filter roles',
                'aria-label': 'Filter' })
            .val(state.filterByTab[tab.id] || '')
            .on('input', function () {
                state.filterByTab[tab.id] = $(this).val();
                renderBody(tab);
            });
        $bar.append($filter);

        if (canEdit && tab.type === 'matrix') {
            var $add = el('input', 'ea-add')
                .attr({ type: 'text', placeholder: 'Add a column by name', 'aria-label': 'Add a column by name' });
            var addColumn = function () {
                var name = $.trim($add.val());
                var extra = state.extraColumns[tab.id] = state.extraColumns[tab.id] || [];
                if (name && $.inArray(name, extra) === -1) { extra.push(name); }
                $add.val('');
                renderBody(tab);
            };
            $add.on('keydown', function (event) {
                if (event.which === 13) { addColumn(); }
            });
            $bar.append($add).append(el('button', 'btn', 'Add column').on('click', addColumn));
        }

        var $actions = el('span', 'ea-actions');
        $actions.append(el('button', 'btn', 'Reload').prop('disabled', state.busy).on('click', function () {
            state.message = null;
            load();
        }));
        if (canEdit) {
            $actions.append(el('button', 'btn ea-discard', 'Discard changes').on('click', function () {
                state.matrixPending = newMap();
                state.settingsPending = newMap();
                state.message = null;
                render();
            }));
            $actions.append(el('button', 'btn btn-primary ea-save', 'Save changes').on('click', save));
        }
        $bar.append($actions);
        return $bar;
    }

    function renderMessage() {
        var $box = el('div', 'ea-messages');
        if (state.busy) {
            $box.append(el('div', 'ea-message ea-info', 'Working...'));
        }
        if (state.message) {
            var $message = el('div', 'ea-message ea-' + state.message.kind);
            $.each(state.message.lines, function (i, line) {
                $message.append(el('div', null, line));
            });
            $box.append($message);
        }
        if (state.data && !state.data.can_edit) {
            $box.append(el('div', 'ea-message ea-info',
                'Read-only: your account does not hold the edit_roles or edit_roles_grantable capability.'));
        }
        return $box;
    }

    function roleHeader(role) {
        var $name = el('th', 'ea-role', role.name);
        if (role.imported_roles.length) {
            $name.attr('title', role.name + ' inherits from: ' + role.imported_roles.join(', '));
        }
        return $name;
    }

    function visibleColumns(tab) {
        var columns = tab.columns.slice();
        var known = newMap();
        $.each(columns, function (i, column) { known[column.name] = true; });
        $.each(state.extraColumns[tab.id] || [], function (i, name) {
            if (!known[name]) {
                columns.push({ name: name, kind: 'added', internal: false, disabled: false });
            }
        });
        var needle = (state.filterByTab[tab.id] || '').toLowerCase();
        if (!needle) { return columns; }
        return $.grep(columns, function (column) {
            return column.name.toLowerCase().indexOf(needle) !== -1;
        });
    }

    function renderMatrix(tab, $wrap) {
        var columns = visibleColumns(tab);
        var roles = state.data.roles;
        var field = state.fieldByTab[tab.id];
        var canEdit = state.data.can_edit;

        if (!columns.length) {
            $wrap.append(el('p', 'ea-empty', 'No columns match the filter.'));
            return;
        }

        var $table = el('table', 'ea-table');
        var $head = el('tr');
        $head.append(el('th', 'ea-corner', 'Role'));
        $.each(columns, function (i, column) {
            var $th = el('th', 'ea-column');
            var $label = el('span', 'ea-column-label');
            $label.append(el('span', 'ea-column-name', column.name));
            if (KIND_LABELS[column.kind]) {
                $label.append(el('span', 'ea-badge', KIND_LABELS[column.kind]));
            } else if (column.disabled) {
                $label.append(el('span', 'ea-badge', 'disabled'));
            }
            $th.attr('title', column.name);
            $head.append($th.append($label));
        });
        $table.append(el('thead').append($head));

        // Built detached and attached once: a large grid is tens of thousands
        // of cells, and appending them live reflows on every row.
        var $body = el('tbody');
        $.each(roles, function (j, role) {
            var $tr = el('tr').append(roleHeader(role));
            var cell = (tab.cells[role.name] || {})[field] || { explicit: [], effective: {} };
            $.each(columns, function (i, column) {
                var cellKey = key(role.name, field, column.name);
                var explicit = state.explicit[cellKey] === true;
                var checked = cellKey in state.matrixPending ? state.matrixPending[cellKey] : explicit;
                var reason = cell.effective[column.name];
                var $td = el('td', 'ea-cell');
                var $box = el('input').attr({
                    type: 'checkbox',
                    'data-role': role.name,
                    'data-field': field,
                    'data-item': column.name,
                    'aria-label': role.name + ' / ' + column.name
                }).prop('checked', checked).prop('disabled', !canEdit);
                if (reason) {
                    $td.addClass('ea-effective').attr('title', reason);
                }
                if (cellKey in state.matrixPending) {
                    $td.addClass('ea-changed');
                }
                $tr.append($td.append($box));
            });
            $body.append($tr);
        });
        $wrap.append($table.append($body));
    }

    function displayValue(field, value) {
        return field.kind === 'list' ? value.join(', ') : value;
    }

    function renderSettings(tab, $wrap) {
        var canEdit = state.data.can_edit;
        var needle = (state.filterByTab[tab.id] || '').toLowerCase();
        var roles = $.grep(state.data.roles, function (role) {
            return !needle || role.name.toLowerCase().indexOf(needle) !== -1;
        });
        if (!roles.length) {
            $wrap.append(el('p', 'ea-empty', 'No roles match the filter.'));
            return;
        }

        var $table = el('table', 'ea-table ea-settings');
        var $head = el('tr');
        $head.append(el('th', 'ea-corner', 'Role'));
        $.each(tab.fields, function (i, field) {
            var $th = el('th', 'ea-setting');
            $th.append(el('div', null, field.label));
            $th.append(el('div', 'ea-attr', field.name));
            $head.append($th);
        });
        $table.append(el('thead').append($head));

        var $body = el('tbody');
        $.each(roles, function (j, role) {
            var $tr = el('tr').append(roleHeader(role));
            $.each(tab.fields, function (i, field) {
                var loaded = tab.values[role.name][field.name];
                var cellKey = key(role.name, field.name);
                var pending = state.settingsPending[cellKey];
                var value = pending ? pending.value : loaded.value;
                var $td = el('td', 'ea-cell ea-setting-cell');
                var $input;
                if (field.kind === 'flag') {
                    $input = el('input').attr('type', 'checkbox').prop('checked', value === '1');
                } else {
                    $input = el('input').attr({ type: 'text', spellcheck: 'false' })
                        .val(displayValue(field, value));
                    if (field.kind === 'list') {
                        $input.attr('placeholder', 'comma-separated');
                    }
                }
                $input.attr({
                    'data-role': role.name,
                    'data-field': field.name,
                    'data-kind': field.kind,
                    'aria-label': role.name + ' / ' + field.label
                }).addClass('ea-setting-input').prop('disabled', !canEdit);
                // The value inherited from imported roles, so the person can
                // see what the role gets even where its own value is empty.
                if (loaded.imported !== null && loaded.imported !== undefined &&
                        String(displayValue(field, loaded.imported)) !== '') {
                    $td.attr('title', 'From imported roles: ' + displayValue(field, loaded.imported));
                    $td.append(el('div', 'ea-imported', 'imported: ' + displayValue(field, loaded.imported)));
                }
                if (pending) { $td.addClass('ea-changed'); }
                $tr.append($td.prepend($input));
            });
            $body.append($tr);
        });
        $wrap.append($table.append($body));
    }

    function renderBody(tab) {
        var $wrap = $root.find('.ea-table-wrap').empty();
        if (!state.data.roles.length) {
            $wrap.append(el('p', 'ea-empty', 'No roles are visible to your account.'));
            return;
        }
        if (tab.type === 'matrix') {
            renderMatrix(tab, $wrap);
        } else {
            renderSettings(tab, $wrap);
        }
    }

    function legend(tab) {
        if (tab.type === 'matrix') {
            return 'A tick means the item is listed on the role itself. A shaded cell is already ' +
                'effective through an imported role or a wildcard (hover for the reason). ' +
                'An outlined cell is an unsaved change.';
        }
        return 'Each field is the value set on the role itself; "imported" shows what its ' +
            'imported roles provide. Lists are comma-separated. An outlined cell is an unsaved change.';
    }

    function render() {
        applyTheme();
        $root.empty();
        if (!state.data) {
            $root.append(renderMessage());
            if (!state.busy && !state.message) {
                $root.append(el('p', null, 'Loading roles...'));
            }
            return;
        }
        var tab = currentTab();
        $root.append(renderTabs());
        $root.append(renderToolbar(tab));
        $root.append(renderMessage());
        $root.append(el('p', 'ea-legend', legend(tab)));
        $root.append(el('div', 'ea-table-wrap'));
        renderBody(tab);
        updateSaveButtons();
    }

    function refreshTabCounts() {
        $root.find('.ea-tabs').replaceWith(renderTabs());
        updateSaveButtons();
    }

    // One delegated handler for every checkbox in a matrix, rather than one per cell.
    $root.on('change', '.ea-cell input[data-item]', function () {
        var cellKey = key(this.getAttribute('data-role'), this.getAttribute('data-field'),
            this.getAttribute('data-item'));
        var explicit = state.explicit[cellKey] === true;
        if (this.checked === explicit) {
            delete state.matrixPending[cellKey];   // flipped back: no longer a change
        } else {
            state.matrixPending[cellKey] = this.checked;
        }
        $(this).closest('td').toggleClass('ea-changed', cellKey in state.matrixPending);
        refreshTabCounts();
    });

    // And one for every settings field. "change" fires once editing is done,
    // not on each keystroke.
    $root.on('change', '.ea-setting-input', function () {
        var role = this.getAttribute('data-role');
        var fieldName = this.getAttribute('data-field');
        var kind = this.getAttribute('data-kind');
        var cellKey = key(role, fieldName);
        var loaded = settingValue(role, fieldName);
        var value;
        var same;
        if (kind === 'flag') {
            value = this.checked ? '1' : '0';
            same = value === loaded;
        } else if (kind === 'list') {
            value = parseList(this.value);
            same = sameList(value, loaded);
        } else {
            value = $.trim(this.value);
            same = value === loaded;
        }
        if (same) {
            delete state.settingsPending[cellKey];
        } else {
            state.settingsPending[cellKey] = { value: value, previous: loaded };
        }
        $(this).closest('td').toggleClass('ea-changed', !same);
        refreshTabCounts();
    });

    // Leaving with unsaved changes silently discards them; let the browser ask.
    $(window).on('beforeunload', function () {
        if (pendingCount()) {
            return 'There are unsaved role changes.';
        }
        return undefined;
    });

    load();
});
