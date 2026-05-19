# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import encode_path
from ansible_collections.mipsou.freebox.plugins.modules import fs_directory as mod


# ── Stubs ────────────────────────────────────────────────────────────────


class RecordingClient(object):
    """In-memory stand-in for FreeboxClient for FS directory tests."""

    def __init__(self, fs_info=None, mkdir_task_id="42", rm_task_id=7):
        self.calls = []
        self._fs_info = fs_info or {}
        self._mkdir_task_id = mkdir_task_id
        self._rm_task_id = rm_task_id

    def path_exists(self, path):
        self.calls.append({"method": "PATH_EXISTS", "path": path})
        return self._fs_info.get(path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/fs/mkdir/":
            return self._mkdir_task_id  # bare string — Freebox quirk
        if path == "/fs/rm/":
            return {"id": self._rm_task_id, "state": "queued", "type": "rm", "error": ""}
        raise AssertionError("unexpected POST %s" % path)

    def poll_fs_task(self, task_id, timeout=120, interval=1.0):
        self.calls.append({"method": "POLL_FS", "task_id": task_id})
        return {"id": task_id, "state": "done"}


class StubModule(object):
    def __init__(self, check_mode=False, wait=True, task_timeout=120):
        self.check_mode = check_mode
        self.params = {"wait": wait, "task_timeout": task_timeout}
        self._fail_msgs = []

    def fail_json(self, msg="", **_kw):
        self._fail_msgs.append(msg)
        raise SystemExit(msg)

    def warn(self, msg):
        pass


PATH = "/Disque 1/VMs/backups"
DIR_INFO = {"type": "dir", "name": "backups"}
FILE_INFO = {"type": "file", "name": "backups"}


# ── _ensure_present ──────────────────────────────────────────────────────


def test_ensure_present_creates_when_absent():
    client = RecordingClient()
    module = StubModule()
    result = mod._ensure_present(module, client, PATH)
    assert result["changed"] is True
    assert result["state"] == "present"
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["path"] == "/fs/mkdir/"
    assert posts[0]["body"]["dirname"] == "backups"
    assert posts[0]["body"]["parent"] == encode_path("/Disque 1/VMs")
    polls = [c for c in client.calls if c["method"] == "POLL_FS"]
    assert len(polls) == 1
    assert result["task_id"] == 42  # cast from string "42"


def test_ensure_present_noop_when_dir_exists():
    client = RecordingClient(fs_info={PATH: DIR_INFO})
    module = StubModule()
    result = mod._ensure_present(module, client, PATH)
    assert result["changed"] is False
    assert result["state"] == "present"
    assert not any(c["method"] == "POST" for c in client.calls)


def test_ensure_present_fails_when_file_at_path():
    client = RecordingClient(fs_info={PATH: FILE_INFO})
    module = StubModule()
    with pytest.raises(SystemExit):
        mod._ensure_present(module, client, PATH)
    assert module._fail_msgs
    assert "file" in module._fail_msgs[0]


def test_ensure_present_check_mode_does_not_mkdir():
    client = RecordingClient()
    module = StubModule(check_mode=True)
    result = mod._ensure_present(module, client, PATH)
    assert result["changed"] is True
    assert not any(c["method"] == "POST" for c in client.calls)
    assert "task_id" not in result


def test_ensure_present_no_poll_when_wait_false():
    client = RecordingClient()
    module = StubModule(wait=False)
    result = mod._ensure_present(module, client, PATH)
    assert result["changed"] is True
    assert not any(c["method"] == "POLL_FS" for c in client.calls)


# ── _ensure_absent ───────────────────────────────────────────────────────


def test_ensure_absent_noop_when_already_absent():
    client = RecordingClient()
    module = StubModule()
    result = mod._ensure_absent(module, client, PATH)
    assert result["changed"] is False
    assert result["state"] == "absent"
    assert not any(c["method"] == "POST" for c in client.calls)


def test_ensure_absent_deletes_when_dir_present():
    client = RecordingClient(fs_info={PATH: DIR_INFO})
    module = StubModule()
    result = mod._ensure_absent(module, client, PATH)
    assert result["changed"] is True
    assert result["state"] == "absent"
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["path"] == "/fs/rm/"
    assert posts[0]["body"]["files"] == [encode_path(PATH)]
    polls = [c for c in client.calls if c["method"] == "POLL_FS"]
    assert len(polls) == 1
    assert result["task_id"] == 7


def test_ensure_absent_fails_when_file_at_path():
    client = RecordingClient(fs_info={PATH: FILE_INFO})
    module = StubModule()
    with pytest.raises(SystemExit):
        mod._ensure_absent(module, client, PATH)
    assert module._fail_msgs
    assert "fs_file" in module._fail_msgs[0]


def test_ensure_absent_check_mode_does_not_rm():
    client = RecordingClient(fs_info={PATH: DIR_INFO})
    module = StubModule(check_mode=True)
    result = mod._ensure_absent(module, client, PATH)
    assert result["changed"] is True
    assert not any(c["method"] == "POST" for c in client.calls)
