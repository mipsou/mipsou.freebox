# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import (
    port_forward as mod,
)


# ── Recording client ─────────────────────────────────────────────────────


class RecordingClient(object):
    """In-memory stand-in mirroring ``/fw/redir/`` state across calls."""

    def __init__(self, rules=None, next_id=1):
        self.rules = list(rules or [])
        self.calls = []
        self._next_id = next_id

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path, "query": query})
        if path == "/fw/redir/":
            return list(self.rules)
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/fw/redir/":
            created = dict(body)
            created["id"] = self._next_id
            self._next_id += 1
            self.rules.append(created)
            return created
        raise AssertionError("unexpected POST %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        if path.startswith("/fw/redir/"):
            rule_id = int(path.rsplit("/", 1)[1])
            for rule in self.rules:
                if rule.get("id") == rule_id:
                    rule.update(body)
                    return dict(rule)
            raise AssertionError("no rule with id=%d" % rule_id)
        raise AssertionError("unexpected PUT %s" % path)

    def delete(self, path):
        self.calls.append({"method": "DELETE", "path": path})
        if path.startswith("/fw/redir/"):
            rule_id = int(path.rsplit("/", 1)[1])
            self.rules = [r for r in self.rules if r.get("id") != rule_id]
            return None
        raise AssertionError("unexpected DELETE %s" % path)


class StubModule(object):
    def __init__(self, check_mode=False):
        self.check_mode = check_mode


# Common identity tuple for the tests below.
HTTPS_IDENTITY = ("tcp", 443, 443, "")


def _existing_https_rule(**overrides):
    rule = dict(
        id=7,
        ip_proto="tcp",
        wan_port_start=443,
        wan_port_end=443,
        src_ip="",
        lan_ip="192.168.1.50",
        lan_port=443,
        enabled=True,
        comment="https",
    )
    rule.update(overrides)
    return rule


# ── _identity ────────────────────────────────────────────────────────────


def test_identity_normalises_missing_src_ip():
    rule = {"ip_proto": "tcp", "wan_port_start": 80, "wan_port_end": 80}
    # Missing src_ip is coerced to "" so it matches the default-derived identity.
    assert mod._identity(rule) == ("tcp", 80, 80, "")


# ── _diff_fields ─────────────────────────────────────────────────────────


def test_diff_fields_ignores_none_values():
    existing = {"enabled": True, "comment": "old"}
    desired = {"enabled": False, "comment": None}
    assert mod._diff_fields(existing, desired) == {"enabled": False}


# ── _ensure_present ──────────────────────────────────────────────────────


def test_ensure_present_creates_when_absent():
    client = RecordingClient(rules=[])
    module = StubModule()
    desired = dict(
        ip_proto="tcp", wan_port_start=443, wan_port_end=443, src_ip="",
        lan_ip="192.168.1.50", lan_port=443, enabled=True, comment="https",
    )
    result = mod._ensure_present(module, client, HTTPS_IDENTITY, desired)
    assert result["changed"] is True
    post = [c for c in client.calls if c["method"] == "POST"]
    assert len(post) == 1
    assert post[0]["body"]["lan_ip"] == "192.168.1.50"
    # The created rule gets an id assigned by the box stub.
    assert result["rule"]["id"] == 1


def test_ensure_present_noop_when_already_matching():
    client = RecordingClient(rules=[_existing_https_rule()])
    module = StubModule()
    desired = dict(
        ip_proto="tcp", wan_port_start=443, wan_port_end=443, src_ip="",
        lan_ip="192.168.1.50", lan_port=443, enabled=True, comment="https",
    )
    result = mod._ensure_present(module, client, HTTPS_IDENTITY, desired)
    assert result["changed"] is False
    assert all(c["method"] == "GET" for c in client.calls)


def test_ensure_present_updates_via_partial_put():
    """The Freebox accepts partial PUT on /fw/redir/{id} — only changed keys."""
    client = RecordingClient(rules=[_existing_https_rule()])
    module = StubModule()
    desired = dict(
        ip_proto="tcp", wan_port_start=443, wan_port_end=443, src_ip="",
        lan_ip="192.168.1.50", lan_port=443, enabled=False, comment="https",
    )
    result = mod._ensure_present(module, client, HTTPS_IDENTITY, desired)
    assert result["changed"] is True
    put = [c for c in client.calls if c["method"] == "PUT"]
    assert len(put) == 1
    assert put[0]["body"] == {"enabled": False}
    # No POST/DELETE — pure update.
    assert not any(c["method"] in ("POST", "DELETE") for c in client.calls)


def test_ensure_present_check_mode_does_not_mutate():
    client = RecordingClient(rules=[_existing_https_rule(enabled=True)])
    module = StubModule(check_mode=True)
    desired = dict(
        ip_proto="tcp", wan_port_start=443, wan_port_end=443, src_ip="",
        lan_ip="192.168.1.50", lan_port=443, enabled=False, comment="https",
    )
    result = mod._ensure_present(module, client, HTTPS_IDENTITY, desired)
    assert result["changed"] is True
    assert result["rule"]["enabled"] is False
    assert all(c["method"] == "GET" for c in client.calls)


def test_ensure_present_identity_distinguishes_src_ip():
    """Two rules differing only by src_ip are distinct: present must create
    the new src_ip-restricted rule rather than match the unrestricted one."""
    client = RecordingClient(rules=[_existing_https_rule(src_ip="")])
    module = StubModule()
    restricted_identity = ("tcp", 443, 443, "203.0.113.10")
    desired = dict(
        ip_proto="tcp", wan_port_start=443, wan_port_end=443, src_ip="203.0.113.10",
        lan_ip="192.168.1.50", lan_port=443, enabled=True, comment="restricted",
    )
    result = mod._ensure_present(module, client, restricted_identity, desired)
    assert result["changed"] is True
    post = [c for c in client.calls if c["method"] == "POST"]
    assert len(post) == 1
    assert post[0]["body"]["src_ip"] == "203.0.113.10"
    # Original unrestricted rule untouched
    assert any(r["src_ip"] == "" for r in client.rules)
    assert any(r["src_ip"] == "203.0.113.10" for r in client.rules)


# ── _ensure_absent ───────────────────────────────────────────────────────


def test_ensure_absent_noop_when_already_absent():
    client = RecordingClient(rules=[])
    module = StubModule()
    result = mod._ensure_absent(module, client, HTTPS_IDENTITY)
    assert result == {"changed": False, "rule": {}}
    assert all(c["method"] == "GET" for c in client.calls)


def test_ensure_absent_deletes_when_present():
    client = RecordingClient(rules=[_existing_https_rule()])
    module = StubModule()
    result = mod._ensure_absent(module, client, HTTPS_IDENTITY)
    assert result["changed"] is True
    delete_calls = [c for c in client.calls if c["method"] == "DELETE"]
    assert delete_calls == [{"method": "DELETE", "path": "/fw/redir/7"}]
    assert client.rules == []


def test_ensure_absent_check_mode_does_not_delete():
    client = RecordingClient(rules=[_existing_https_rule()])
    module = StubModule(check_mode=True)
    result = mod._ensure_absent(module, client, HTTPS_IDENTITY)
    assert result["changed"] is True
    assert not any(c["method"] == "DELETE" for c in client.calls)
