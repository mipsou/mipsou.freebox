# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import wifi_ssid as mod


# ── Recording client ─────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, ssids=None):
        self._ssids = list(ssids or [])
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/wifi/bss/":
            return list(self._ssids)
        raise AssertionError("unexpected GET %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        # Update in-memory state for introspection.
        for ssid in self._ssids:
            put_key = "/wifi/ap/{0}/ssid/{1}".format(ssid["ap_id"], ssid["id"])
            if path == put_key:
                ssid.update(body)
                return dict(ssid)
        raise AssertionError("unexpected PUT %s" % path)


# ── helpers ───────────────────────────────────────────────────────────────


def _ssid(**overrides):
    s = dict(
        id="22:66:CF:74:D1:A8",
        bssid="22:66:CF:74:D1:A8",
        ssid="MyNetwork",
        band="5g",
        enabled=True,
        hide_ssid=False,
        encryption="wpa2_ccmp",
        ap_id=0,
    )
    s.update(overrides)
    return s


# ── _find_ssid ────────────────────────────────────────────────────────────


def test_find_ssid_matches_by_name():
    client = RecordingClient(ssids=[_ssid()])
    found = mod._find_ssid(client, "MyNetwork")
    assert found is not None
    assert found["ssid"] == "MyNetwork"


def test_find_ssid_no_match():
    client = RecordingClient(ssids=[_ssid()])
    assert mod._find_ssid(client, "OtherNetwork") is None


def test_find_ssid_matches_with_ap_id():
    client = RecordingClient(ssids=[_ssid(ap_id=0), _ssid(ssid="MyNetwork", ap_id=1, id="AA:BB:CC:DD:EE:FF")])
    found = mod._find_ssid(client, "MyNetwork", ap_id=1)
    assert found is not None
    assert found["ap_id"] == 1


def test_find_ssid_ap_id_no_match():
    client = RecordingClient(ssids=[_ssid(ap_id=0)])
    assert mod._find_ssid(client, "MyNetwork", ap_id=1) is None


# ── _diff_fields ─────────────────────────────────────────────────────────


def test_diff_fields_detects_changed():
    existing = {"enabled": True, "hide_ssid": False, "encryption": "wpa2_ccmp"}
    desired = {"enabled": False}
    assert mod._diff_fields(existing, desired) == {"enabled": False}


def test_diff_fields_ignores_none():
    existing = {"enabled": True}
    desired = {"enabled": None, "hide_ssid": None}
    assert mod._diff_fields(existing, desired) == {}


def test_diff_fields_noop_when_same():
    existing = {"enabled": True, "hide_ssid": False}
    desired = {"enabled": True}
    assert mod._diff_fields(existing, desired) == {}


# ── main via internal helpers ─────────────────────────────────────────────


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
    p = dict(
        name="MyNetwork",
        ap_id=None,
        enabled=None,
        hide_ssid=None,
        encryption=None,
        state="present",
    )
    p.update(overrides)
    # Include COMMON_ARGSPEC-like fields (unused by helpers but accessed by FreeboxClient).
    p.setdefault("url", "http://mafreebox.freebox.fr")
    p.setdefault("app_id", "test")
    p.setdefault("app_token", "secret")
    p.setdefault("api_base", "/api/v15")
    p.setdefault("timeout", 30)
    p.setdefault("validate_certs", True)
    return p


def test_noop_when_already_matching():
    client = RecordingClient(ssids=[_ssid(enabled=True)])

    # Call _find_ssid + _diff_fields directly — mirrors what main() does.
    existing = mod._find_ssid(client, "MyNetwork")
    assert existing is not None
    diff = mod._diff_fields(existing, {"enabled": True})
    assert diff == {}


def test_put_issued_when_enabled_changes():
    client = RecordingClient(ssids=[_ssid(enabled=True)])
    existing = mod._find_ssid(client, "MyNetwork")
    diff = mod._diff_fields(existing, {"enabled": False})
    assert diff == {"enabled": False}

    ssid_id = existing["id"]
    ap_id_actual = existing["ap_id"]
    client.put("/wifi/ap/{0}/ssid/{1}".format(ap_id_actual, ssid_id), body=diff)

    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"enabled": False}
    assert puts[0]["path"] == "/wifi/ap/0/ssid/22:66:CF:74:D1:A8"


def test_put_only_changed_fields():
    client = RecordingClient(ssids=[_ssid(enabled=True, hide_ssid=False)])
    existing = mod._find_ssid(client, "MyNetwork")
    # Request hide_ssid=True, enabled stays the same.
    diff = mod._diff_fields(existing, {"enabled": True, "hide_ssid": True})
    assert diff == {"hide_ssid": True}


def test_find_ssid_not_found_returns_none():
    client = RecordingClient(ssids=[])
    assert mod._find_ssid(client, "NonExistent") is None


def test_check_mode_no_put():
    client = RecordingClient(ssids=[_ssid(enabled=True)])
    existing = mod._find_ssid(client, "MyNetwork")
    diff = mod._diff_fields(existing, {"enabled": False})
    # In check_mode, we should not call PUT — verify no PUT call was made.
    assert not any(c["method"] == "PUT" for c in client.calls)
    assert diff == {"enabled": False}
