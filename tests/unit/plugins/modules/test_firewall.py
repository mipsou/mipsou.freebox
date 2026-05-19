# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.mipsou.freebox.plugins.modules import firewall as mod
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import validate_rfc1918


# ── RecordingClient ───────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, dmz=None, incoming=None):
        self._dmz = dmz or {"enabled": False, "ip": "192.168.1.50"}
        self._incoming = list(incoming or [])
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/fw/dmz/":
            return dict(self._dmz)
        if path == "/fw/incoming/":
            return list(self._incoming)
        raise AssertionError("unexpected GET %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        if path == "/fw/dmz/":
            self._dmz.update(body or {})
            return dict(self._dmz)
        raise AssertionError("unexpected PUT %s" % path)

    def diff_and_put(self, path, desired, full_body=False, check_mode=False):
        before = self.get(path)
        changed_keys = [k for k, v in desired.items() if before.get(k) != v]
        if not changed_keys:
            return False, before, before
        after_sim = dict(before)
        after_sim.update(desired)
        if check_mode:
            return True, before, after_sim
        body = {k: desired[k] for k in changed_keys}
        after_actual = self.put(path, body=body) or after_sim
        return True, before, after_actual


# ── validate_rfc1918 ───────────────────────────────────────────────────────


def test_validate_rfc1918_accepts_192_168():
    assert validate_rfc1918("192.168.1.50") == "192.168.1.50"


def test_validate_rfc1918_rejects_public():
    with pytest.raises(ValueError):
        validate_rfc1918("8.8.8.8")


# ── mod._update_dmz ───────────────────────────────────────────────────────


def test_update_dmz_enable_issues_put():
    client = RecordingClient(dmz={"enabled": False, "ip": "192.168.1.50"})
    changed, before, after = mod._update_dmz(client, {"enabled": True})
    assert changed is True
    assert after["enabled"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"enabled": True}


def test_update_dmz_noop_when_already_enabled():
    client = RecordingClient(dmz={"enabled": True, "ip": "192.168.1.50"})
    changed, before, after = mod._update_dmz(client, {"enabled": True})
    assert changed is False
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_update_dmz_check_mode_no_put():
    client = RecordingClient(dmz={"enabled": False, "ip": "192.168.1.50"})
    changed, before, after = mod._update_dmz(client, {"enabled": True}, check_mode=True)
    assert changed is True
    assert after["enabled"] is True
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_update_dmz_ip_change_issues_put():
    client = RecordingClient(dmz={"enabled": True, "ip": "192.168.1.1"})
    changed, before, after = mod._update_dmz(client, {"ip": "192.168.1.100"})
    assert changed is True
    assert after["ip"] == "192.168.1.100"


def test_update_dmz_no_desired_does_get_only():
    client = RecordingClient(dmz={"enabled": True, "ip": "192.168.1.50"})
    changed, before, after = mod._update_dmz(client, {})
    assert changed is False
    assert after == {"enabled": True, "ip": "192.168.1.50"}
    assert all(c["method"] == "GET" for c in client.calls)


def test_update_dmz_empty_desired_returns_current():
    client = RecordingClient(dmz={"enabled": False, "ip": "192.168.1.2"})
    changed, _before, after = mod._update_dmz(client, {})
    assert changed is False
    assert after["ip"] == "192.168.1.2"


# ── mod._collect_incoming ─────────────────────────────────────────────────


def test_collect_incoming_returns_rules():
    rules = [{"id": 1, "enabled": True, "comment": "ssh"}]
    client = RecordingClient(incoming=rules)
    result = mod._collect_incoming(client)
    assert result == rules
    gets = [c for c in client.calls if c["path"] == "/fw/incoming/"]
    assert len(gets) == 1


def test_collect_incoming_empty():
    client = RecordingClient(incoming=[])
    result = mod._collect_incoming(client)
    assert result == []


def test_collect_incoming_multiple_rules():
    rules = [{"id": 1}, {"id": 2}, {"id": 3}]
    client = RecordingClient(incoming=rules)
    result = mod._collect_incoming(client)
    assert len(result) == 3
    assert result[1]["id"] == 2
