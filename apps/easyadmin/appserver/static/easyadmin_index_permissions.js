/*
 * Easy Admin - index permissions page.
 *
 * Renders the role x index matrix returned by the app's REST endpoint as a
 * grid of checkboxes, tracks which cells the user has flipped, and submits
 * all of them in one request.
 *
 * Rendering only: what a cell means, validation and the writes themselves all
 * live server-side in bin/easyadmin_core.py, where they are unit tested.
 *
 * Every name shown here (roles, indexes, messages) comes from the server and
 * is inserted with text() or attr(), never as HTML, so a role or index with
 * markup in its name cannot inject script into an administrator's session.
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
    var ENDPOINT = splunkUtil.make_url('/splunkd/__raw/services/easyadmin/index_permissions');
    // Joins role, field and index into one key. NUL cannot occur in any of them.
    var SEP = '\u0000';

    var $root = $('#easyadmin-index-permissions');

    var state = {
        data: null,        // last matrix from the server
        field: null,       // which role attribute the grid is showing
        pending: newMap(), // key -> true (grant) / false (revoke), unsaved
        filter: '',
        extraRows: [],     // index names typed in by the user, not yet on any role
        explicit: newMap(),// key -> true for entries listed on the role itself
        busy: false,
        message: null      // {kind: 'error' | 'success' | 'info', lines: [..]}
    };

    // A prototype-less object, so an index called "constructor" is just a key.
    function newMap() {
        return Object.create(null);
    }

    function key(role, field, index) {
        return role + SEP + field + SEP + index;
    }

    function el(tag, className, text) {
        var $node = $(document.createElement(tag));
        if (className) { $node.addClass(className); }
        if (text !== undefined && text !== null) { $node.text(text); }
        return $node;
    }

    function pendingCount() {
        var count = 0;
        var name;
        for (name in state.pending) { count += 1; }
        return count;
    }

    function errorText(xhr) {
        var body = xhr && xhr.responseJSON;
        if (body && body.messages && body.messages.length && body.messages[0].text) {
            return body.messages[0].text;
        }
        if (xhr && xhr.status === 404) {
            return 'The Easy Admin endpoint was not found. Splunk must be restarted once after ' +
                'the app is installed before the endpoint is registered.';
        }
        if (xhr && xhr.status) {
            return 'Request failed with HTTP ' + xhr.status + '.';
        }
        return 'Could not reach Splunk.';
    }

    // ---------------------------------------------------------------- data

    function indexExplicit(data) {
        var map = newMap();
        $.each(data.roles, function (i, role) {
            $.each(data.fields, function (j, field) {
                $.each(role[field.name].explicit, function (k, index) {
                    map[key(role.name, field.name, index)] = true;
                });
            });
        });
        return map;
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
            state.data = data;
            state.explicit = indexExplicit(data);
            if (!state.field && data.fields.length) {
                state.field = data.fields[0].name;
            }
            // A pending change the server state now already satisfies is no
            // longer a change (someone else made it, or the save applied it).
            var name;
            for (name in state.pending) {
                if (state.pending[name] === (state.explicit[name] === true)) {
                    delete state.pending[name];
                }
            }
        }).fail(function (xhr) {
            state.message = { kind: 'error', lines: [errorText(xhr)] };
        }).always(function () {
            state.busy = false;
            render();
        });
    }

    function save() {
        var changes = [];
        var roles = newMap();
        var name;
        var parts;
        for (name in state.pending) {
            parts = name.split(SEP);
            changes.push({ role: parts[0], field: parts[1], index: parts[2], grant: state.pending[name] });
            roles[parts[0]] = true;
        }
        if (!changes.length) { return; }

        var roleCount = 0;
        for (name in roles) { roleCount += 1; }
        // Role edits take effect immediately for every user holding the role,
        // so make the size of the submit explicit before it happens.
        if (!window.confirm('Apply ' + changes.length + ' change(s) to ' + roleCount + ' role(s)?')) {
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
            var pendingName;
            for (pendingName in state.pending) {
                if (!failed[pendingName.split(SEP)[0]]) {
                    delete state.pending[pendingName];
                }
            }
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

    function visibleRows() {
        var rows = state.data.indexes.slice();
        var known = newMap();
        $.each(rows, function (i, row) { known[row.name] = true; });
        $.each(state.extraRows, function (i, name) {
            if (!known[name]) {
                rows.push({ name: name, kind: 'added', internal: false, disabled: false });
            }
        });
        var needle = state.filter.toLowerCase();
        if (!needle) { return rows; }
        return $.grep(rows, function (row) {
            return row.name.toLowerCase().indexOf(needle) !== -1;
        });
    }

    var KIND_LABELS = {
        wildcard: 'wildcard',
        unknown: 'not on this search head',
        added: 'added here'
    };

    function renderToolbar() {
        var $bar = el('div', 'ea-toolbar');
        var count = pendingCount();
        var canEdit = state.data.can_edit;

        var $field = el('select', 'ea-field').attr('aria-label', 'Permission');
        $.each(state.data.fields, function (i, field) {
            $field.append(el('option', null, field.label).attr('value', field.name));
        });
        $field.val(state.field).on('change', function () {
            state.field = $(this).val();
            render();
        });
        $bar.append(el('label', 'ea-label', 'Show ')).append($field);

        var $filter = el('input', 'ea-filter')
            .attr({ type: 'text', placeholder: 'Filter indexes', 'aria-label': 'Filter indexes' })
            .val(state.filter)
            .on('input', function () {
                state.filter = $(this).val();
                renderTable();
            });
        $bar.append($filter);

        if (canEdit) {
            var $add = el('input', 'ea-add')
                .attr({ type: 'text', placeholder: 'Add index or wildcard', 'aria-label': 'Add index or wildcard' });
            var addRow = function () {
                var name = $.trim($add.val());
                if (name && $.inArray(name, state.extraRows) === -1) {
                    state.extraRows.push(name);
                }
                $add.val('');
                renderTable();
            };
            $add.on('keydown', function (event) {
                if (event.which === 13) { addRow(); }
            });
            $bar.append($add).append(el('button', 'btn ea-add-button', 'Add column').on('click', addRow));
        }

        var $actions = el('span', 'ea-actions');
        $actions.append(el('button', 'btn', 'Reload').prop('disabled', state.busy).on('click', function () {
            state.message = null;
            load();
        }));
        if (canEdit) {
            $actions.append(el('button', 'btn ea-discard', 'Discard changes')
                .prop('disabled', state.busy || !count)
                .on('click', function () {
                    state.pending = newMap();
                    state.message = null;
                    render();
                }));
            $actions.append(el('button', 'btn btn-primary ea-save',
                count ? 'Save ' + count + ' change(s)' : 'Save changes')
                .prop('disabled', state.busy || !count)
                .on('click', save));
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

    function renderTable() {
        var $wrap = $root.find('.ea-table-wrap').empty();
        var rows = visibleRows();
        var roles = state.data.roles;
        var field = state.field;
        var canEdit = state.data.can_edit;

        if (!roles.length) {
            $wrap.append(el('p', 'ea-empty', 'No roles are visible to your account.'));
            return;
        }
        if (!rows.length) {
            $wrap.append(el('p', 'ea-empty', 'No indexes match the filter.'));
            return;
        }

        // Roles run down the page and indexes across it: one row per role,
        // one column per index. "rows" above are the server's index entries,
        // which become the columns here.
        var $table = el('table', 'ea-table');
        var $head = el('tr');
        $head.append(el('th', 'ea-corner', 'Role'));
        $.each(rows, function (i, row) {
            var $th = el('th', 'ea-index');
            var $label = el('span', 'ea-index-label');
            $label.append(el('span', 'ea-index-name', row.name));
            if (KIND_LABELS[row.kind]) {
                $label.append(el('span', 'ea-badge', KIND_LABELS[row.kind]));
            } else if (row.disabled) {
                $label.append(el('span', 'ea-badge', 'disabled'));
            }
            $th.attr('title', row.name);
            $head.append($th.append($label));
        });
        $table.append(el('thead').append($head));

        // Built detached and attached once: a large matrix is tens of
        // thousands of cells, and appending them live reflows on every row.
        var $body = el('tbody');
        $.each(roles, function (j, role) {
            var $tr = el('tr');
            var $name = el('th', 'ea-role', role.name);
            if (role.imported_roles.length) {
                $name.attr('title', role.name + ' inherits from: ' + role.imported_roles.join(', '));
            }
            $tr.append($name);

            $.each(rows, function (i, row) {
                var cellKey = key(role.name, field, row.name);
                var explicit = state.explicit[cellKey] === true;
                var checked = cellKey in state.pending ? state.pending[cellKey] : explicit;
                var reason = role[field].effective[row.name];
                var $td = el('td', 'ea-cell');
                var $box = el('input').attr({
                    type: 'checkbox',
                    'data-role': role.name,
                    'data-index': row.name,
                    'aria-label': role.name + ' / ' + row.name
                }).prop('checked', checked).prop('disabled', !canEdit);
                if (reason) {
                    $td.addClass('ea-effective').attr('title', reason);
                }
                if (cellKey in state.pending) {
                    $td.addClass('ea-changed');
                }
                $tr.append($td.append($box));
            });
            $body.append($tr);
        });
        $table.append($body);
        $wrap.append($table);
    }

    function render() {
        $root.empty();
        if (!state.data) {
            $root.append(renderMessage());
            if (!state.busy && !state.message) {
                $root.append(el('p', null, 'Loading roles and indexes...'));
            }
            return;
        }
        $root.append(renderToolbar());
        $root.append(renderMessage());
        $root.append(el('p', 'ea-legend',
            'A tick means the index is listed on the role itself. A shaded cell is already ' +
            'effective through an imported role or a wildcard (hover for the reason). ' +
            'An outlined cell is an unsaved change.'));
        $root.append(el('div', 'ea-table-wrap'));
        renderTable();
    }

    // One delegated handler for every checkbox, rather than one per cell.
    $root.on('change', '.ea-cell input[type="checkbox"]', function () {
        var cellKey = key(this.getAttribute('data-role'), state.field, this.getAttribute('data-index'));
        var explicit = state.explicit[cellKey] === true;
        if (this.checked === explicit) {
            delete state.pending[cellKey];   // flipped back: no longer a change
        } else {
            state.pending[cellKey] = this.checked;
        }
        $(this).closest('td').toggleClass('ea-changed', cellKey in state.pending);

        var count = pendingCount();
        $root.find('.ea-save').prop('disabled', !count)
            .text(count ? 'Save ' + count + ' change(s)' : 'Save changes');
        $root.find('.ea-discard').prop('disabled', !count);
    });

    // Leaving with unsaved ticks silently discards them; let the browser ask.
    $(window).on('beforeunload', function () {
        if (pendingCount()) {
            return 'There are unsaved index permission changes.';
        }
        return undefined;
    });

    load();
});
