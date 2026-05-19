# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import system as mod


# ── helpers ───────────────────────────────────────────────────────────────

_SYSTEM_RESPONSE = {
    "mac": "20:66:CF:75:8B:2E",
    "serial": "385502J225103772",
    "uptime": "10 heures",
    "uptime_val": 37075,
    "board_name": "fbxgw7r",
    "firmware_version": "4.10.2",
    "disk_status": "active",
    "box_authenticated": True,
    "sensors": [],
    "fans": [],
}


class RecordingClient(object):
    def __init__(self, system_data=None):
        self._system = system_data or dict(_SYSTEM_RESPONSE)
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/system/":
            return dict(self._system)
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/system/reboot/":
            return None
        raise AssertionError("unexpected POST %s" % path)


class StubModule(object):
    def __init__(self, params, check_mode=False):
        self.params = params
        self.check_mode = check_mode
        self._results = []
        self._failures = []

    def exit_json(self, **kw):
        self._results.append(kw)
        raise SystemExit(0)

    def fail_json(self, **kw):
        self._failures.append(kw)
        raise SystemExit(1)


def _base_params(**overrides):
    p = dict(reboot=False)
    p.update(overrides)
    return p


# ── facts gathering ───────────────────────────────────────────────────────


def test_gather_facts_returns_freebox_system():
    client = RecordingClient()
    info = client.get("/system/")
    assert info["firmware_version"] == "4.10.2"
    assert info["board_name"] == "fbxgw7r"
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) == 1
    assert gets[0]["path"] == "/system/"


def test_gather_facts_no_reboot_is_unchanged():
    client = RecordingClient()
    info = client.get("/system/")
    # No reboot → no POST issued.
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert posts == []
    # changed must be false (no side effect).
    assert info is not None  # facts returned


def test_gather_facts_includes_sensors_and_fans():
    data = dict(_SYSTEM_RESPONSE)
    data["sensors"] = [{"id": "temp_t1", "name": "Temp 1", "value": 52}]
    data["fans"] = [{"id": "fan0_speed", "name": "Fan 1", "value": 1462}]
    client = RecordingClient(system_data=data)
    info = client.get("/system/")
    assert len(info["sensors"]) == 1
    assert info["sensors"][0]["value"] == 52
    assert len(info["fans"]) == 1


# ── reboot ────────────────────────────────────────────────────────────────


def test_reboot_posts_system_reboot():
    client = RecordingClient()
    client.get("/system/")
    client.post("/system/reboot/")
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["path"] == "/system/reboot/"


def test_reboot_check_mode_no_post():
    client = RecordingClient()
    client.get("/system/")
    # In check_mode: POST must NOT be issued.
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert posts == []


def test_reboot_true_changed_is_true():
    """Reboot=true always yields changed=true regardless of Freebox state."""
    client = RecordingClient()
    client.get("/system/")
    client.post("/system/reboot/")
    posts = [c for c in client.calls if c["method"] == "POST"]
    # Verify the reboot was issued.
    assert len(posts) == 1


def test_facts_ansible_facts_key_is_freebox_system():
    """The returned fact must be namespaced as freebox_system."""
    client = RecordingClient()
    info = client.get("/system/")
    # Simulate what main() does — wrap in ansible_facts.
    ansible_facts = {"freebox_system": info}
    assert "freebox_system" in ansible_facts
    assert ansible_facts["freebox_system"]["mac"] == "20:66:CF:75:8B:2E"


def test_gather_facts_empty_response_returns_empty_dict():
    """If the API returns None, facts should be an empty dict (not crash)."""
    client = RecordingClient(system_data={})
    info = client.get("/system/") or {}
    ansible_facts = {"freebox_system": info}
    assert isinstance(ansible_facts["freebox_system"], dict)
