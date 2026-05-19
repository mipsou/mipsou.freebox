# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import lan_host as mod


# ── Stubs ────────────────────────────────────────────────────────────────


class RecordingClient(object):
    """In-memory stand-in for FreeboxClient for LAN host tests."""

    def __init__(self, hosts=None):
        self.calls = []
        self._hosts = list(hosts or [])

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/lan/browser/pub/":
            return list(self._hosts)
        raise AssertionError("unexpected GET %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        if "/lan/browser/pub/" in path:
            host_id = path.rsplit("/", 1)[1]
            for host in self._hosts:
                if host.get("id") == host_id:
                    updated = dict(host)
                    updated.update(body)
                    return updated
        raise AssertionError("no host found at %s" % path)


class StubModule(object):
    def __init__(self, check_mode=False):
        self.check_mode = check_mode
        self._fail_msgs = []

    def fail_json(self, msg="", **_kw):
        self._fail_msgs.append(msg)
        raise SystemExit(msg)


def _make_host(mac, name="my-host", host_type="workstation",
               freebox_id=None, l2ident_as_list=True):
    """Build a minimal LanHost dict for use in tests."""
    fbx_id = freebox_id or ("ether-%s" % mac)
    l2 = {"id": mac, "type": "ethernet"}
    return {
        "id": fbx_id,
        "primary_name": name,
        "host_type": host_type,
        "reachable": True,
        "l2ident": [l2] if l2ident_as_list else l2,
    }


MAC = "de:ad:be:ef:00:01"
HOST = _make_host(MAC, name="nas-prod", host_type="nas")


# ── _find_host_by_mac ────────────────────────────────────────────────────


def test_find_host_found_by_mac_list():
    client = RecordingClient(hosts=[HOST])
    host, host_id = mod._find_host_by_mac(client, MAC)
    assert host is not None
    assert host_id == HOST["id"]


def test_find_host_found_single_object_l2ident():
    """Freebox firmware quirk: l2ident may be a single object instead of a list."""
    single_obj_host = _make_host(MAC, l2ident_as_list=False)
    client = RecordingClient(hosts=[single_obj_host])
    host, host_id = mod._find_host_by_mac(client, MAC)
    assert host is not None
    assert host["id"] == single_obj_host["id"]


def test_find_host_not_found():
    client = RecordingClient(hosts=[HOST])
    host, host_id = mod._find_host_by_mac(client, "aa:bb:cc:dd:ee:ff")
    assert host is None
    assert host_id is None


def test_find_host_case_insensitive():
    """MAC lookup normalises case — "DE:AD:BE:EF:00:01" must match "de:ad:be:ef:00:01"."""
    upper_mac_host = _make_host("DE:AD:BE:EF:00:01")
    client = RecordingClient(hosts=[upper_mac_host])
    host, _ = mod._find_host_by_mac(client, "de:ad:be:ef:00:01")
    assert host is not None


# ── _update_host ─────────────────────────────────────────────────────────


def test_update_noop_when_already_matching():
    client = RecordingClient(hosts=[HOST])
    module = StubModule()
    desired = {"primary_name": "nas-prod", "host_type": "nas"}
    result = mod._update_host(module, client, HOST, HOST["id"], desired)
    assert result["changed"] is False
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_update_changes_primary_name():
    client = RecordingClient(hosts=[HOST])
    module = StubModule()
    desired = {"primary_name": "nas-new"}
    result = mod._update_host(module, client, HOST, HOST["id"], desired)
    assert result["changed"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"primary_name": "nas-new"}
    assert result["host"]["primary_name"] == "nas-new"


def test_update_changes_host_type():
    client = RecordingClient(hosts=[HOST])
    module = StubModule()
    desired = {"host_type": "workstation"}
    result = mod._update_host(module, client, HOST, HOST["id"], desired)
    assert result["changed"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"host_type": "workstation"}


def test_update_only_changed_keys_sent():
    """Partial PUT — only the keys that differ are sent."""
    client = RecordingClient(hosts=[HOST])
    module = StubModule()
    # primary_name matches, host_type differs
    desired = {"primary_name": "nas-prod", "host_type": "nas_new"}
    result = mod._update_host(module, client, HOST, HOST["id"], desired)
    assert result["changed"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert puts[0]["body"] == {"host_type": "nas_new"}


def test_update_check_mode_does_not_put():
    client = RecordingClient(hosts=[HOST])
    module = StubModule(check_mode=True)
    desired = {"primary_name": "renamed"}
    result = mod._update_host(module, client, HOST, HOST["id"], desired)
    assert result["changed"] is True
    assert result["host"]["primary_name"] == "renamed"
    assert not any(c["method"] == "PUT" for c in client.calls)
