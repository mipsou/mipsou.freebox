# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import download_config as mod
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    encode_path,
    sanitize_path,
)


# ── encode_path / sanitize_path behaviour for paths ──────────────────────


def test_encode_path_roundtrip():
    raw = "/Disque dur/Telechargements"
    encoded = encode_path(sanitize_path(raw))
    import base64
    decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    assert decoded == raw


def test_sanitize_rejects_traversal():
    import pytest
    with pytest.raises(ValueError):
        sanitize_path("/foo/../etc/passwd")


# ── RecordingClient ───────────────────────────────────────────────────────


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
            self._cfg.update(body)
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


# ── throttling_mode change ────────────────────────────────────────────────


def test_throttling_mode_change_issues_put():
    client = RecordingClient()
    changed, before, after = client.diff_and_put(
        "/downloads/config/", {"throttling_mode": "slow"}
    )
    assert changed is True
    assert after["throttling_mode"] == "slow"
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    assert puts[0]["body"] == {"throttling_mode": "slow"}


def test_noop_when_already_matching():
    client = RecordingClient()
    changed, before, after = client.diff_and_put(
        "/downloads/config/", {"throttling_mode": "normal"}
    )
    assert changed is False


def test_check_mode_no_put():
    client = RecordingClient()
    changed, before, after = client.diff_and_put(
        "/downloads/config/", {"throttling_mode": "hibernate"}, check_mode=True
    )
    assert changed is True
    assert after["throttling_mode"] == "hibernate"
    assert not any(c["method"] == "PUT" for c in client.calls)


def test_path_field_encoded_before_comparison():
    """download_dir is stored base64-encoded; same encoding means no-op."""
    encoded = encode_path("/Disque dur/Telechargements")
    client = RecordingClient(cfg={"download_dir": encoded, "throttling_mode": "normal",
                                  "max_downloading_tasks": 10, "use_watch_dir": False,
                                  "watch_dir": encode_path("/Disque dur/Torrents")})
    # Setting the same path (re-encoded) → no change.
    desired_encoded = encode_path(sanitize_path("/Disque dur/Telechargements"))
    changed, before, after = client.diff_and_put(
        "/downloads/config/", {"download_dir": desired_encoded}
    )
    assert changed is False


def test_path_field_change_issues_put():
    old_encoded = encode_path("/Disque dur/Old")
    new_encoded = encode_path("/Disque dur/New")
    client = RecordingClient(cfg={"download_dir": old_encoded, "throttling_mode": "normal",
                                  "max_downloading_tasks": 10, "use_watch_dir": False,
                                  "watch_dir": encode_path("/Disque dur/Torrents")})
    changed, before, after = client.diff_and_put(
        "/downloads/config/", {"download_dir": new_encoded}
    )
    assert changed is True
    assert after["download_dir"] == new_encoded


def test_multi_key_change():
    client = RecordingClient()
    changed, before, after = client.diff_and_put(
        "/downloads/config/",
        {"throttling_mode": "slow", "max_downloading_tasks": 5}
    )
    assert changed is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1
    body = puts[0]["body"]
    assert body.get("throttling_mode") == "slow"
    assert body.get("max_downloading_tasks") == 5
