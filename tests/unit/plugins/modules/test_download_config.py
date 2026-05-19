# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.mipsou.freebox.plugins.modules import download_config as mod
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    encode_path,
    sanitize_path,
)


# ── encode_path / sanitize_path ────────────────────────────────────────────


def test_encode_path_roundtrip():
    import base64
    raw = "/Disque dur/Telechargements"
    encoded = encode_path(sanitize_path(raw))
    decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    assert decoded == raw


def test_sanitize_rejects_traversal():
    with pytest.raises(ValueError):
        sanitize_path("/foo/../etc/passwd")


# ── RecordingClient ────────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, cfg=None):
        self._cfg = cfg or {
            "download_dir": encode_path("/Disque dur/Telechargements"),
            "max_downloading_tasks": 10,
            "throttling_mode": "normal",
            "use_watch_dir": False,
            "watch_dir": encode_path("/Disque dur/Torrents"),
        }
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/downloads/config/":
            return dict(self._cfg)
        raise AssertionError("unexpected GET %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        if path == "/downloads/config/":
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


def test_update_config_throttling_change_issues_put():
    client = RecordingClient()
    changed, before, after = mod._update_config(client, {"throttling_mode": "slow"})
    assert changed is True
    assert after["throttling_mode"] == "slow"
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"throttling_mode": "slow"}


def test_update_config_noop_when_already_matching():
    client = RecordingClient()
    changed, before, after = mod._update_config(client, {"throttling_mode": "normal"})
    assert changed is False


def test_update_config_check_mode_no_put():
    client = RecordingClient()
    changed, before, after = mod._update_config(client, {"throttling_mode": "hibernate"}, check_mode=True)
    assert changed is True
    assert after["throttling_mode"] == "hibernate"
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_update_config_empty_desired_get_only():
    client = RecordingClient()
    changed, before, after = mod._update_config(client, {})
    assert changed is False
    assert all(c["method"] == "GET" for c in client.calls)


def test_update_config_path_same_encoding_noop():
    """Providing the same path re-encoded must not trigger a PUT."""
    encoded = encode_path("/Disque dur/Telechargements")
    client = RecordingClient(cfg={
        "download_dir": encoded, "throttling_mode": "normal",
        "max_downloading_tasks": 10, "use_watch_dir": False,
        "watch_dir": encode_path("/Disque dur/Torrents"),
    })
    desired_encoded = encode_path(sanitize_path("/Disque dur/Telechargements"))
    changed, before, after = mod._update_config(client, {"download_dir": desired_encoded})
    assert changed is False


def test_update_config_path_change_issues_put():
    old_enc = encode_path("/Disque dur/Old")
    new_enc = encode_path("/Disque dur/New")
    client = RecordingClient(cfg={
        "download_dir": old_enc, "throttling_mode": "normal",
        "max_downloading_tasks": 10, "use_watch_dir": False,
        "watch_dir": encode_path("/Disque dur/Torrents"),
    })
    changed, before, after = mod._update_config(client, {"download_dir": new_enc})
    assert changed is True
    assert after["download_dir"] == new_enc


def test_update_config_multi_key_change():
    client = RecordingClient()
    changed, before, after = mod._update_config(
        client, {"throttling_mode": "slow", "max_downloading_tasks": 5}
    )
    assert changed is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    body = puts[0]["body"]
    assert body.get("throttling_mode") == "slow"
    assert body.get("max_downloading_tasks") == 5


# ── mod._compute_diff ─────────────────────────────────────────────────────


def test_compute_diff_returns_changed_keys():
    before = {"a": 1, "b": 2}
    after = {"a": 1, "b": 3}
    diff = mod._compute_diff(before, after, ["a", "b"])
    assert "a" not in diff
    assert diff["b"] == (2, 3)


def test_compute_diff_empty_when_no_change():
    before = {"a": 1}
    after = {"a": 1}
    assert mod._compute_diff(before, after, ["a"]) == {}
