# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import (
    dhcp_static_lease as mod,
)


# ── Recording client ─────────────────────────────────────────────────────


class RecordingClient(object):
    """Minimal stand-in for FreeboxClient that records mutating calls.

    ``leases`` is the in-memory list returned by ``GET /dhcp/static_lease/``.
    POST appends and DELETE removes; both update ``leases`` to mirror real
    server behaviour so cascading flows (DELETE+POST update) are observable.
    """

    def __init__(self, leases=None):
        self.leases = list(leases or [])
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path, "query": query})
        if path == "/dhcp/static_lease/":
            return list(self.leases)
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/dhcp/static_lease/":
            created = dict(body)
            # The Freebox API assigns the lease id == mac in practice.
            created.setdefault("id", body["mac"])
            self.leases.append(created)
            return created
        raise AssertionError("unexpected POST %s" % path)

    def delete(self, path):
        self.calls.append({"method": "DELETE", "path": path})
        if path.startswith("/dhcp/static_lease/"):
            lease_id = path.rsplit("/", 1)[1]
            self.leases = [le for le in self.leases if le.get("id") != lease_id]
            return None
        raise AssertionError("unexpected DELETE %s" % path)


# ── Module stub ──────────────────────────────────────────────────────────


class StubModule(object):
    def __init__(self, params, check_mode=False):
        self.params = params
        self.check_mode = check_mode
        self.failed = None

    def fail_json(self, **kw):
        self.failed = kw
        raise SystemExit(kw)


# ── _find_lease_by_mac ───────────────────────────────────────────────────


def test_find_lease_by_mac_case_insensitive():
    client = RecordingClient(leases=[
        {"id": "lease-1", "mac": "AA:BB:CC:11:22:33", "ip": "192.168.1.10"},
    ])
    found = mod._find_lease_by_mac(client, "aa:bb:cc:11:22:33")
    assert found is not None
    assert found["ip"] == "192.168.1.10"


def test_find_lease_by_mac_returns_none_when_absent():
    client = RecordingClient(leases=[])
    assert mod._find_lease_by_mac(client, "aa:bb:cc:11:22:33") is None


# ── _matches_desired ─────────────────────────────────────────────────────


def test_matches_desired_ignores_none_keys():
    lease = {"ip": "192.168.1.10", "hostname": "nas", "comment": ""}
    assert mod._matches_desired(lease, {"ip": "192.168.1.10", "hostname": None})


def test_matches_desired_detects_diff():
    lease = {"ip": "192.168.1.10", "hostname": "nas"}
    assert not mod._matches_desired(lease, {"ip": "192.168.1.99"})


# ── _ensure_present ──────────────────────────────────────────────────────


def test_ensure_present_creates_when_absent():
    client = RecordingClient(leases=[])
    module = StubModule(params={}, check_mode=False)
    result = mod._ensure_present(module, client, "aa:bb:cc:11:22:33", dict(
        ip="192.168.1.10", hostname="nas", comment="managed",
    ))
    assert result["changed"] is True
    post_calls = [c for c in client.calls if c["method"] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0]["body"] == {
        "mac": "aa:bb:cc:11:22:33",
        "ip": "192.168.1.10",
        "hostname": "nas",
        "comment": "managed",
    }
    # No DELETE since there was no prior lease
    assert not any(c["method"] == "DELETE" for c in client.calls)


def test_ensure_present_noop_when_already_matching():
    client = RecordingClient(leases=[{
        "id": "aa:bb:cc:11:22:33", "mac": "aa:bb:cc:11:22:33",
        "ip": "192.168.1.10", "hostname": "nas", "comment": "managed",
    }])
    module = StubModule(params={}, check_mode=False)
    result = mod._ensure_present(module, client, "aa:bb:cc:11:22:33", dict(
        ip="192.168.1.10", hostname="nas", comment="managed",
    ))
    assert result["changed"] is False
    # Only the GET happened — no POST, no DELETE
    methods = [c["method"] for c in client.calls]
    assert methods == ["GET"]


def test_ensure_present_updates_via_delete_then_post():
    """No PUT on /dhcp/static_lease/{id} — update is DELETE + POST."""
    client = RecordingClient(leases=[{
        "id": "aa:bb:cc:11:22:33", "mac": "aa:bb:cc:11:22:33",
        "ip": "192.168.1.10", "hostname": "old",
    }])
    module = StubModule(params={}, check_mode=False)
    result = mod._ensure_present(module, client, "aa:bb:cc:11:22:33", dict(
        ip="192.168.1.20", hostname="new", comment=None,
    ))
    assert result["changed"] is True
    sequence = [(c["method"], c["path"]) for c in client.calls
                if c["method"] in ("DELETE", "POST")]
    # DELETE must come before POST
    assert sequence[0] == ("DELETE", "/dhcp/static_lease/aa:bb:cc:11:22:33")
    assert sequence[1] == ("POST", "/dhcp/static_lease/")


def test_ensure_present_check_mode_does_not_mutate():
    client = RecordingClient(leases=[])
    module = StubModule(params={}, check_mode=True)
    result = mod._ensure_present(module, client, "aa:bb:cc:11:22:33", dict(
        ip="192.168.1.10", hostname=None, comment=None,
    ))
    assert result["changed"] is True
    assert all(c["method"] == "GET" for c in client.calls)
    assert result["lease"]["ip"] == "192.168.1.10"


# ── _ensure_absent ───────────────────────────────────────────────────────


def test_ensure_absent_noop_when_already_absent():
    client = RecordingClient(leases=[])
    module = StubModule(params={}, check_mode=False)
    result = mod._ensure_absent(module, client, "aa:bb:cc:11:22:33")
    assert result == {"changed": False, "lease": {}}
    assert all(c["method"] == "GET" for c in client.calls)


def test_ensure_absent_deletes_when_present():
    client = RecordingClient(leases=[{
        "id": "aa:bb:cc:11:22:33", "mac": "aa:bb:cc:11:22:33",
        "ip": "192.168.1.10",
    }])
    module = StubModule(params={}, check_mode=False)
    result = mod._ensure_absent(module, client, "aa:bb:cc:11:22:33")
    assert result["changed"] is True
    assert result["lease"]["ip"] == "192.168.1.10"
    delete_calls = [c for c in client.calls if c["method"] == "DELETE"]
    assert delete_calls == [{
        "method": "DELETE",
        "path": "/dhcp/static_lease/aa:bb:cc:11:22:33",
    }]


def test_ensure_absent_check_mode_does_not_delete():
    client = RecordingClient(leases=[{
        "id": "aa:bb:cc:11:22:33", "mac": "aa:bb:cc:11:22:33",
        "ip": "192.168.1.10",
    }])
    module = StubModule(params={}, check_mode=True)
    result = mod._ensure_absent(module, client, "aa:bb:cc:11:22:33")
    assert result["changed"] is True
    assert not any(c["method"] == "DELETE" for c in client.calls)
