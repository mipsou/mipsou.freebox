# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.mipsou.freebox.plugins.modules import route as mod


# ── Recording client ─────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, routes_v4=None, routes_v6=None, next_id=1):
        self._routes = {4: list(routes_v4 or []), 6: list(routes_v6 or [])}
        self.calls = []
        self._next_id = next_id

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/ipv4/route/":
            return list(self._routes[4])
        if path == "/ipv6/route/":
            return list(self._routes[6])
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        version = 4 if "ipv4" in path else 6
        created = dict(body)
        created["id"] = self._next_id
        self._next_id += 1
        self._routes[version].append(created)
        return created

    def delete(self, path):
        self.calls.append({"method": "DELETE", "path": path})
        for ver in (4, 6):
            prefix = "/ipv4/route/" if ver == 4 else "/ipv6/route/"
            if path.startswith(prefix):
                route_id = int(path[len(prefix):])
                self._routes[ver] = [r for r in self._routes[ver] if r.get("id") != route_id]
                return None
        raise AssertionError("unexpected DELETE %s" % path)


class StubModule(object):
    def __init__(self, check_mode=False):
        self.check_mode = check_mode
        self.failures = []

    def fail_json(self, **kw):
        self.failures.append(kw)
        raise SystemExit(kw)


# ── helpers ───────────────────────────────────────────────────────────────


def _route_v4(**overrides):
    r = dict(id=1, ip="10.20.0.0", mask="255.255.0.0", gw="192.168.1.254", enabled=True)
    r.update(overrides)
    return r


def _route_v6(**overrides):
    r = dict(id=2, ip="2001:db8::", prefix_len=32, gw="fe80::1", enabled=True)
    r.update(overrides)
    return r


# ── _detect_ip_version ───────────────────────────────────────────────────


def test_detect_ip_version_v4():
    assert mod._detect_ip_version("10.0.0.1") == 4


def test_detect_ip_version_v6():
    assert mod._detect_ip_version("2001:db8::1") == 6


# ── _validate_ipv4 ───────────────────────────────────────────────────────


def test_validate_ipv4_accepts_valid():
    assert mod._validate_ipv4("192.168.1.1", "ip") == "192.168.1.1"


@pytest.mark.parametrize("bad", ["256.0.0.1", "not-an-ip", "::1", "1.2.3"])
def test_validate_ipv4_rejects_bad(bad):
    with pytest.raises(ValueError):
        mod._validate_ipv4(bad, "ip")


# ── _validate_ipv6 ───────────────────────────────────────────────────────


def test_validate_ipv6_accepts_valid():
    assert mod._validate_ipv6("2001:db8::", "ip") == "2001:db8::"


@pytest.mark.parametrize("bad", ["", "not-ipv6", "192.168.1.1", "fe80:1"])
def test_validate_ipv6_rejects_bad(bad):
    with pytest.raises(ValueError):
        mod._validate_ipv6(bad, "ip")


# ── _find_route ───────────────────────────────────────────────────────────


def test_find_route_v4_matches():
    client = RecordingClient(routes_v4=[_route_v4()])
    identity = ("10.20.0.0", "255.255.0.0", "192.168.1.254")
    found = mod._find_route(client, 4, identity)
    assert found is not None
    assert found["ip"] == "10.20.0.0"


def test_find_route_v4_no_match():
    client = RecordingClient(routes_v4=[_route_v4()])
    identity = ("10.30.0.0", "255.255.0.0", "192.168.1.254")
    assert mod._find_route(client, 4, identity) is None


def test_find_route_v6_matches():
    client = RecordingClient(routes_v6=[_route_v6()])
    identity = ("2001:db8::", 32, "fe80::1")
    found = mod._find_route(client, 6, identity)
    assert found is not None


# ── _ensure_present ───────────────────────────────────────────────────────


def test_ensure_present_creates_v4_when_absent():
    client = RecordingClient()
    module = StubModule()
    body = {"ip": "10.20.0.0", "mask": "255.255.0.0", "gw": "192.168.1.254", "enabled": True}
    identity = ("10.20.0.0", "255.255.0.0", "192.168.1.254")
    result = mod._ensure_present(module, client, 4, identity, body)
    assert result["changed"] is True
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["path"] == "/ipv4/route/"


def test_ensure_present_noop_when_already_present():
    client = RecordingClient(routes_v4=[_route_v4()])
    module = StubModule()
    body = {"ip": "10.20.0.0", "mask": "255.255.0.0", "gw": "192.168.1.254", "enabled": True}
    identity = ("10.20.0.0", "255.255.0.0", "192.168.1.254")
    result = mod._ensure_present(module, client, 4, identity, body)
    assert result["changed"] is False
    assert all(c["method"] == "GET" for c in client.calls)


def test_ensure_present_recreates_when_enabled_differs():
    """enabled flag changed → DELETE old route + POST new one (no PUT)."""
    client = RecordingClient(routes_v4=[_route_v4(enabled=True)])
    module = StubModule()
    body = {"ip": "10.20.0.0", "mask": "255.255.0.0", "gw": "192.168.1.254", "enabled": False}
    identity = ("10.20.0.0", "255.255.0.0", "192.168.1.254")
    result = mod._ensure_present(module, client, 4, identity, body)
    assert result["changed"] is True
    methods = [c["method"] for c in client.calls]
    assert "DELETE" in methods
    assert "POST" in methods
    delete_idx = methods.index("DELETE")
    post_idx = methods.index("POST")
    assert delete_idx < post_idx


def test_ensure_present_creates_v6():
    client = RecordingClient()
    module = StubModule()
    body = {"ip": "2001:db8::", "prefix_len": 32, "gw": "fe80::1", "enabled": True}
    identity = ("2001:db8::", 32, "fe80::1")
    result = mod._ensure_present(module, client, 6, identity, body)
    assert result["changed"] is True
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert posts[0]["path"] == "/ipv6/route/"


def test_ensure_present_check_mode_does_not_post():
    client = RecordingClient()
    module = StubModule(check_mode=True)
    body = {"ip": "10.20.0.0", "mask": "255.255.0.0", "gw": "192.168.1.254", "enabled": True}
    identity = ("10.20.0.0", "255.255.0.0", "192.168.1.254")
    result = mod._ensure_present(module, client, 4, identity, body)
    assert result["changed"] is True
    assert not any(c["method"] == "POST" for c in client.calls)


# ── _ensure_absent ────────────────────────────────────────────────────────


def test_ensure_absent_noop_when_already_absent():
    client = RecordingClient()
    module = StubModule()
    result = mod._ensure_absent(module, client, 4, ("10.20.0.0", "255.255.0.0", "192.168.1.254"))
    assert result == {"changed": False, "route": {}}


def test_ensure_absent_deletes_existing_v4():
    client = RecordingClient(routes_v4=[_route_v4()])
    module = StubModule()
    result = mod._ensure_absent(module, client, 4, ("10.20.0.0", "255.255.0.0", "192.168.1.254"))
    assert result["changed"] is True
    deletes = [c for c in client.calls if c["method"] == "DELETE"]
    assert len(deletes) == 1
    assert "/ipv4/route/1" in deletes[0]["path"]


def test_ensure_absent_check_mode_does_not_delete():
    client = RecordingClient(routes_v4=[_route_v4()])
    module = StubModule(check_mode=True)
    result = mod._ensure_absent(module, client, 4, ("10.20.0.0", "255.255.0.0", "192.168.1.254"))
    assert result["changed"] is True
    assert not any(c["method"] == "DELETE" for c in client.calls)


def test_ensure_absent_deletes_v6():
    client = RecordingClient(routes_v6=[_route_v6()])
    module = StubModule()
    result = mod._ensure_absent(module, client, 6, ("2001:db8::", 32, "fe80::1"))
    assert result["changed"] is True
    deletes = [c for c in client.calls if c["method"] == "DELETE"]
    assert "/ipv6/route/2" in deletes[0]["path"]
