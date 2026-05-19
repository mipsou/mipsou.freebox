# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import wifi_config as mod


# ── RecordingClient ───────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, cfg=None):
        self._cfg = cfg or {"enabled": True, "mac_filter_state": "disabled"}
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/wifi/config/":
            return dict(self._cfg)
        raise AssertionError("unexpected GET %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        if path == "/wifi/config/":
            self._cfg.update(body or {})
            return dict(self._cfg)
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


# ── mod._update_config ────────────────────────────────────────────────────


def test_update_config_disable_wifi():
    client = RecordingClient(cfg={"enabled": True, "mac_filter_state": "disabled"})
    changed, before, after = mod._update_config(client, {"enabled": False})
    assert changed is True
    assert after["enabled"] is False
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"enabled": False}


def test_update_config_noop_when_already_disabled():
    client = RecordingClient(cfg={"enabled": False, "mac_filter_state": "disabled"})
    changed, before, after = mod._update_config(client, {"enabled": False})
    assert changed is False
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_update_config_mac_filter_state_change():
    client = RecordingClient(cfg={"enabled": True, "mac_filter_state": "disabled"})
    changed, before, after = mod._update_config(client, {"mac_filter_state": "whitelist"})
    assert changed is True
    assert after["mac_filter_state"] == "whitelist"


def test_update_config_check_mode_no_put():
    client = RecordingClient(cfg={"enabled": True, "mac_filter_state": "disabled"})
    changed, before, after = mod._update_config(client, {"enabled": False}, check_mode=True)
    assert changed is True
    assert after["enabled"] is False
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_update_config_empty_desired_get_only():
    client = RecordingClient(cfg={"enabled": True, "mac_filter_state": "disabled"})
    changed, before, after = mod._update_config(client, {})
    assert changed is False
    assert after["enabled"] is True
    assert all(c["method"] == "GET" for c in client.calls)


def test_update_config_multi_key_change():
    client = RecordingClient(cfg={"enabled": True, "mac_filter_state": "disabled"})
    changed, before, after = mod._update_config(
        client, {"enabled": False, "mac_filter_state": "blacklist"}
    )
    assert changed is True
    assert after["enabled"] is False
    assert after["mac_filter_state"] == "blacklist"


# ── mod._compute_diff ─────────────────────────────────────────────────────


def test_compute_diff_single_changed_key():
    before = {"enabled": True, "mac_filter_state": "disabled"}
    after = {"enabled": False, "mac_filter_state": "disabled"}
    diff = mod._compute_diff(before, after, ["enabled", "mac_filter_state"])
    assert diff == {"enabled": (True, False)}


def test_compute_diff_empty_when_unchanged():
    before = {"enabled": True}
    after = {"enabled": True}
    assert mod._compute_diff(before, after, ["enabled"]) == {}
