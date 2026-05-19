# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.mipsou.freebox.plugins.modules import download as mod


# ── RecordingClient ───────────────────────────────────────────────────────


class RecordingClient(object):
    def __init__(self, tasks=None):
        self._tasks = list(tasks or [])
        self._next_id = 100
        self.calls = []

    def get(self, path, query=None):
        self.calls.append({"method": "GET", "path": path})
        if path == "/downloads/":
            return list(self._tasks)
        raise AssertionError("unexpected GET %s" % path)

    def post(self, path, body=None, content_type="application/json"):
        self.calls.append({"method": "POST", "path": path, "body": body})
        if path == "/downloads/":
            task = dict(body or {})
            task["id"] = self._next_id
            self._next_id += 1
            self._tasks.append(task)
            return task
        raise AssertionError("unexpected POST %s" % path)

    def put(self, path, body=None):
        self.calls.append({"method": "PUT", "path": path, "body": body})
        for task in self._tasks:
            if path == "/downloads/%d" % task["id"]:
                task.update(body or {})
                return dict(task)
        raise AssertionError("no task for %s" % path)

    def delete(self, path):
        self.calls.append({"method": "DELETE", "path": path})
        for i, task in enumerate(self._tasks):
            if path == "/downloads/%d" % task["id"]:
                self._tasks.pop(i)
                return None
        raise AssertionError("no task for %s" % path)


# ── mod._collect_tasks ────────────────────────────────────────────────────


def test_collect_tasks_returns_all():
    tasks = [{"id": 1, "status": "downloading"}, {"id": 2, "status": "stopped"}]
    client = RecordingClient(tasks=tasks)
    result = mod._collect_tasks(client)
    assert result == tasks
    assert len([c for c in client.calls if c["path"] == "/downloads/"]) == 1


def test_collect_tasks_empty():
    client = RecordingClient(tasks=[])
    result = mod._collect_tasks(client)
    assert result == []


def test_collect_tasks_does_get():
    client = RecordingClient(tasks=[{"id": 5}])
    mod._collect_tasks(client)
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) == 1


# ── mod._add_task ─────────────────────────────────────────────────────────


def test_add_task_posts_download_url():
    client = RecordingClient()
    task = mod._add_task(client, "https://example.com/file.iso")
    assert task["download_url"] == "https://example.com/file.iso"
    assert task["id"] == 100
    posts = [c for c in client.calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["body"] == {"download_url": "https://example.com/file.iso"}


def test_add_task_returns_task_dict():
    client = RecordingClient()
    task = mod._add_task(client, "https://example.com/a.torrent")
    assert "id" in task


# ── mod._delete_task ──────────────────────────────────────────────────────


def test_delete_task_removes_it():
    client = RecordingClient(tasks=[{"id": 42, "status": "stopped"}])
    mod._delete_task(client, 42)
    assert client._tasks == []
    deletes = [c for c in client.calls if c["method"] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0]["path"] == "/downloads/42"


def test_delete_task_uses_numeric_id():
    client = RecordingClient(tasks=[{"id": 7, "status": "downloading"}])
    mod._delete_task(client, 7)
    assert client._tasks == []


# ── mod._set_task_status ──────────────────────────────────────────────────


def test_set_task_status_stopped():
    client = RecordingClient(tasks=[{"id": 7, "status": "downloading"}])
    updated = mod._set_task_status(client, 7, "stopped")
    assert updated["status"] == "stopped"
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert puts[0]["body"] == {"status": "stopped"}


def test_set_task_status_downloading():
    client = RecordingClient(tasks=[{"id": 7, "status": "stopped"}])
    updated = mod._set_task_status(client, 7, "downloading")
    assert updated["status"] == "downloading"


def test_set_task_status_path_format():
    client = RecordingClient(tasks=[{"id": 99, "status": "stopped"}])
    mod._set_task_status(client, 99, "downloading")
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert puts[0]["path"] == "/downloads/99"
