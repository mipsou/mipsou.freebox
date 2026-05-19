# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import wifi_mac_filter as mod


# ── RecordingClient ───────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, entries=None):
        self._entries = list(entries or [])
        self._next_id = 1
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/wifi/mac_filter/":
            return list(self._entries)
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/wifi/mac_filter/":
            entry = dict(body or {})
            entry["id"] = self._next_id
            self._next_id += 1
            self._entries.append(entry)
            return entry
        raise AssertionError("unexpected POST %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        for entry in self._entries:
            if path == "/wifi/mac_filter/%s" % entry["id"]:
                entry.update(body)
                return dict(entry)
        raise AssertionError("no entry for %s" % path)

    def delete(self, path):
        self.calls.append({"method": "DELETE", "path": path})
        for i, entry in enumerate(self._entries):
            if path == "/wifi/mac_filter/%s" % entry["id"]:
                self._entries.pop(i)
                return None
        raise AssertionError("no entry for %s" % path)


class StubModule(object):
    def __init__(self, check_mode=False):
        self.check_mode = check_mode


# ── _find_entry ───────────────────────────────────────────────────────────


def test_find_entry_by_mac():
    client = RecordingClient(entries=[{"id": 1, "mac": "aa:bb:cc:dd:ee:ff", "comment": "x"}])
    entry = mod._find_entry(client, "aa:bb:cc:dd:ee:ff")
    assert entry is not None
    assert entry["mac"] == "aa:bb:cc:dd:ee:ff"


def test_find_entry_normalizes_mac_case():
    client = RecordingClient(entries=[{"id": 1, "mac": "AA:BB:CC:DD:EE:FF", "comment": "x"}])
    entry = mod._find_entry(client, "aa:bb:cc:dd:ee:ff")
    assert entry is not None


def test_find_entry_not_found():
    client = RecordingClient(entries=[])
    assert mod._find_entry(client, "aa:bb:cc:dd:ee:ff") is None


# ── _ensure_present ───────────────────────────────────────────────────────


def test_ensure_present_creates_when_absent():
    client = RecordingClient()
    module = StubModule()
    result = mod._ensure_present(module, client, "aa:bb:cc:dd:ee:ff", "workstation")
    assert result["changed"] is True
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["body"]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert posts[0]["body"]["comment"] == "workstation"


def test_ensure_present_noop_when_same():
    client = RecordingClient(entries=[{"id": 1, "mac": "aa:bb:cc:dd:ee:ff", "comment": "ws"}])
    module = StubModule()
    result = mod._ensure_present(module, client, "aa:bb:cc:dd:ee:ff", "ws")
    assert result["changed"] is False
    assert not any(c["method"] in ("POST", "PUT") for c in client.calls)


def test_ensure_present_updates_comment():
    client = RecordingClient(entries=[{"id": 1, "mac": "aa:bb:cc:dd:ee:ff", "comment": "old"}])
    module = StubModule()
    result = mod._ensure_present(module, client, "aa:bb:cc:dd:ee:ff", "new")
    assert result["changed"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"comment": "new"}


def test_ensure_present_check_mode_no_post():
    client = RecordingClient()
    module = StubModule(check_mode=True)
    result = mod._ensure_present(module, client, "aa:bb:cc:dd:ee:ff", "x")
    assert result["changed"] is True
    assert not any(c["method"] == "POST" for c in client.calls)


# ── _ensure_absent ────────────────────────────────────────────────────────


def test_ensure_absent_noop_when_not_found():
    client = RecordingClient()
    module = StubModule()
    result = mod._ensure_absent(module, client, "aa:bb:cc:dd:ee:ff")
    assert result == {"changed": False, "entry": {}}


def test_ensure_absent_deletes():
    client = RecordingClient(entries=[{"id": 1, "mac": "aa:bb:cc:dd:ee:ff", "comment": "x"}])
    module = StubModule()
    result = mod._ensure_absent(module, client, "aa:bb:cc:dd:ee:ff")
    assert result["changed"] is True
    deletes = [c for c in client.calls if c["method"] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0]["path"] == "/wifi/mac_filter/1"
    assert client._entries == []


def test_ensure_absent_check_mode_no_delete():
    client = RecordingClient(entries=[{"id": 1, "mac": "aa:bb:cc:dd:ee:ff", "comment": "x"}])
    module = StubModule(check_mode=True)
    result = mod._ensure_absent(module, client, "aa:bb:cc:dd:ee:ff")
    assert result["changed"] is True
    assert not any(c["method"] == "DELETE" for c in client.calls)
    assert len(client._entries) == 1
