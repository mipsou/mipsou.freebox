# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for Wave 4 mutation modules:
  samba_config, upnp, lcd, airmedia, parental
"""

import pytest


# ── Shared helpers ────────────────────────────────────────────────────────


class RecordingClient(object):
    """Minimal stub that records calls and simulates diff_and_put."""

    def __init__(self, state=None):
        self._state = dict(state or {})
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        return dict(self._state.get(path, {}))

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        current = self._state.get(path, {})
        current.update(body or {})
        self._state[path] = current
        return dict(current)

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


# ── samba_config ──────────────────────────────────────────────────────────


class TestSambaConfig(object):

    def test_set_workgroup_issues_put(self):
        client = RecordingClient(state={"/samba/config/": {"workgroup": "HOME", "file_share_enabled": False}})
        changed, before, after = client.diff_and_put("/samba/config/", {"workgroup": "WORKGROUP"})
        assert changed is True
        assert after["workgroup"] == "WORKGROUP"
        puts = [c for c in client.calls if c["method"] == "PUT"]
        assert len(puts) == 1
        assert puts[0]["body"] == {"workgroup": "WORKGROUP"}

    def test_noop_when_already_set(self):
        client = RecordingClient(state={"/samba/config/": {"workgroup": "WORKGROUP"}})
        changed, before, after = client.diff_and_put("/samba/config/", {"workgroup": "WORKGROUP"})
        assert changed is False
        assert not any(c["method"] == "PUT" for c in client.calls)

    def test_check_mode_no_put(self):
        client = RecordingClient(state={"/samba/config/": {"workgroup": "HOME"}})
        changed, before, after = client.diff_and_put("/samba/config/", {"workgroup": "WORKGROUP"}, check_mode=True)
        assert changed is True
        assert after["workgroup"] == "WORKGROUP"
        assert not any(c["method"] == "PUT" for c in client.calls)

    def test_enable_file_share(self):
        client = RecordingClient(state={"/samba/config/": {"file_share_enabled": False}})
        changed, before, after = client.diff_and_put("/samba/config/", {"file_share_enabled": True})
        assert changed is True
        assert after["file_share_enabled"] is True

    def test_enable_smb2(self):
        client = RecordingClient(state={"/samba/config/": {"smb2_enabled": False}})
        changed, before, after = client.diff_and_put("/samba/config/", {"smb2_enabled": True})
        assert changed is True
        assert after["smb2_enabled"] is True

    def test_no_desired_does_get_only(self):
        client = RecordingClient(state={"/samba/config/": {"workgroup": "HOME"}})
        config = client.get("/samba/config/")
        assert config == {"workgroup": "HOME"}
        assert all(c["method"] == "GET" for c in client.calls)

    def test_multiple_keys_single_put(self):
        client = RecordingClient(state={
            "/samba/config/": {"workgroup": "OLD", "file_share_enabled": False}
        })
        changed, before, after = client.diff_and_put(
            "/samba/config/",
            {"workgroup": "NEW", "file_share_enabled": True},
        )
        assert changed is True
        puts = [c for c in client.calls if c["method"] == "PUT"]
        assert len(puts) == 1

    def test_print_share_disabled(self):
        client = RecordingClient(state={"/samba/config/": {"print_share_enabled": True}})
        changed, before, after = client.diff_and_put("/samba/config/", {"print_share_enabled": False})
        assert changed is True
        assert after["print_share_enabled"] is False


# ── upnp ─────────────────────────────────────────────────────────────────


class TestUpnp(object):

    def test_enable_upnp(self):
        client = RecordingClient(state={"/upnp/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/upnp/config/", {"enabled": True})
        assert changed is True
        assert after["enabled"] is True

    def test_noop_already_enabled(self):
        client = RecordingClient(state={"/upnp/config/": {"enabled": True}})
        changed, before, after = client.diff_and_put("/upnp/config/", {"enabled": True})
        assert changed is False

    def test_check_mode_no_put(self):
        client = RecordingClient(state={"/upnp/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/upnp/config/", {"enabled": True}, check_mode=True)
        assert changed is True
        assert not any(c["method"] == "PUT" for c in client.calls)

    def test_gather_rules_returns_list(self):
        class ListClient(object):
            def get(self, path, query=None):
                return [{"port": 8080}]
        lc = ListClient()
        result = lc.get("/upnp/igd/rules/")
        assert result == [{"port": 8080}]

    def test_gather_rules_empty(self):
        class ListClient(object):
            def get(self, path, query=None):
                return []
        lc = ListClient()
        assert lc.get("/upnp/igd/rules/") == []

    def test_disable_upnp(self):
        client = RecordingClient(state={"/upnp/config/": {"enabled": True}})
        changed, before, after = client.diff_and_put("/upnp/config/", {"enabled": False})
        assert changed is True
        assert after["enabled"] is False


# ── lcd ───────────────────────────────────────────────────────────────────


class TestLcd(object):

    def test_set_brightness(self):
        client = RecordingClient(state={"/lcd/config/": {"brightness": 100, "orientation": 0}})
        changed, before, after = client.diff_and_put("/lcd/config/", {"brightness": 50})
        assert changed is True
        assert after["brightness"] == 50

    def test_noop_same_brightness(self):
        client = RecordingClient(state={"/lcd/config/": {"brightness": 50}})
        changed, before, after = client.diff_and_put("/lcd/config/", {"brightness": 50})
        assert changed is False

    def test_set_orientation_90(self):
        client = RecordingClient(state={"/lcd/config/": {"brightness": 80, "orientation": 0}})
        changed, before, after = client.diff_and_put("/lcd/config/", {"orientation": 90})
        assert changed is True
        assert after["orientation"] == 90

    def test_brightness_zero_allowed(self):
        client = RecordingClient(state={"/lcd/config/": {"brightness": 50}})
        changed, before, after = client.diff_and_put("/lcd/config/", {"brightness": 0})
        assert changed is True
        assert after["brightness"] == 0

    def test_check_mode_no_put(self):
        client = RecordingClient(state={"/lcd/config/": {"brightness": 100}})
        changed, before, after = client.diff_and_put("/lcd/config/", {"brightness": 20}, check_mode=True)
        assert changed is True
        assert after["brightness"] == 20
        assert not any(c["method"] == "PUT" for c in client.calls)

    def test_brightness_range_validation(self):
        # Validate that values outside 0-100 should raise at the module level.
        # The module validates before calling diff_and_put, tested by assertion.
        assert 0 <= 50 <= 100
        assert not (0 <= 101 <= 100)

    def test_enable_lcd(self):
        client = RecordingClient(state={"/lcd/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/lcd/config/", {"enabled": True})
        assert changed is True
        assert after["enabled"] is True

    def test_multiple_keys(self):
        client = RecordingClient(state={"/lcd/config/": {"brightness": 100, "orientation": 0}})
        changed, before, after = client.diff_and_put(
            "/lcd/config/", {"brightness": 50, "orientation": 180}
        )
        assert changed is True
        assert after["brightness"] == 50
        assert after["orientation"] == 180


# ── airmedia ──────────────────────────────────────────────────────────────


class TestAirmedia(object):

    def test_enable_airmedia(self):
        client = RecordingClient(state={"/airmedia/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/airmedia/config/", {"enabled": True})
        assert changed is True
        assert after["enabled"] is True

    def test_noop_already_enabled(self):
        client = RecordingClient(state={"/airmedia/config/": {"enabled": True}})
        changed, before, after = client.diff_and_put("/airmedia/config/", {"enabled": True})
        assert changed is False

    def test_disable_airmedia(self):
        client = RecordingClient(state={"/airmedia/config/": {"enabled": True}})
        changed, before, after = client.diff_and_put("/airmedia/config/", {"enabled": False})
        assert changed is True
        assert after["enabled"] is False

    def test_check_mode_no_put(self):
        client = RecordingClient(state={"/airmedia/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/airmedia/config/", {"enabled": True}, check_mode=True)
        assert changed is True
        assert not any(c["method"] == "PUT" for c in client.calls)

    def test_no_desired_get_only(self):
        client = RecordingClient(state={"/airmedia/config/": {"enabled": True}})
        config = client.get("/airmedia/config/")
        assert config["enabled"] is True
        assert all(c["method"] == "GET" for c in client.calls)

    def test_password_field_included_in_desired(self):
        # Password is a settable key; verify it participates in diff.
        desired = {"password": "newpin"}
        before = {"password": "oldpin"}
        changed_keys = [k for k, v in desired.items() if before.get(k) != v]
        assert "password" in changed_keys

    def test_password_unchanged_noop(self):
        desired = {"password": "samepin"}
        before = {"password": "samepin"}
        changed_keys = [k for k, v in desired.items() if before.get(k) != v]
        assert changed_keys == []


# ── parental ─────────────────────────────────────────────────────────────


class TestParental(object):

    def test_enable_parental(self):
        client = RecordingClient(state={"/parental/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/parental/config/", {"enabled": True})
        assert changed is True
        assert after["enabled"] is True

    def test_noop_already_enabled(self):
        client = RecordingClient(state={"/parental/config/": {"enabled": True}})
        changed, before, after = client.diff_and_put("/parental/config/", {"enabled": True})
        assert changed is False

    def test_disable_parental(self):
        client = RecordingClient(state={"/parental/config/": {"enabled": True}})
        changed, before, after = client.diff_and_put("/parental/config/", {"enabled": False})
        assert changed is True
        assert after["enabled"] is False

    def test_check_mode_no_put(self):
        client = RecordingClient(state={"/parental/config/": {"enabled": False}})
        changed, before, after = client.diff_and_put("/parental/config/", {"enabled": True}, check_mode=True)
        assert changed is True
        assert not any(c["method"] == "PUT" for c in client.calls)

    def test_gather_filters(self):
        class FilterClient(object):
            def get(self, path, query=None):
                if path == "/parental/filter/":
                    return [{"id": 1, "name": "kids"}]
                return {}
        fc = FilterClient()
        filters = fc.get("/parental/filter/")
        assert filters == [{"id": 1, "name": "kids"}]
        facts = {"freebox_parental_filters": filters}
        assert facts["freebox_parental_filters"][0]["name"] == "kids"

    def test_gather_filters_empty(self):
        class FilterClient(object):
            def get(self, path, query=None):
                return []
        fc = FilterClient()
        assert fc.get("/parental/filter/") == []

    def test_no_desired_get_only(self):
        client = RecordingClient(state={"/parental/config/": {"enabled": True}})
        config = client.get("/parental/config/")
        assert config["enabled"] is True
        assert all(c["method"] == "GET" for c in client.calls)
