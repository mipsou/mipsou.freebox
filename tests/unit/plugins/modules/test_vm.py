# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: EUPL-1.2
#
# Tests for the regression scenarios called out in the PRA handoff:
#   - VM delete must capture disk_path BEFORE issuing DELETE /vm/{id}
#     (the Freebox API will not return it afterwards, and the qcow2 +
#      .efivars would leak).
#   - Clone must run fs/cp before fs/rename (intermediate file relies on
#     the source basename produced by fs/cp).
#   - state=present + existing VM + no force_recreate must not POST /vm/.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.mipsou.freebox.plugins.module_utils import freebox_api
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    encode_path,
)
from ansible_collections.mipsou.freebox.plugins.modules import vm as vm_module


# ── Recording client ─────────────────────────────────────────────────────


class RecordingClient(object):
    """In-memory stand-in for FreeboxClient that records every call in order."""

    def __init__(self):
        self.calls = []
        # By path-or-pattern, return value or callable(receiving the call dict).
        self.responses = {}
        # Existing FS paths probed via path_exists.
        self.fs_existing = set()

    def _record(self, method, path, body=None):
        self.calls.append({"method": method, "path": path, "body": body})

    def _resolve(self, key, call):
        spec = self.responses.get(key)
        if callable(spec):
            return spec(call)
        return spec

    # ── FreeboxClient surface used by vm.py ─────────────────────────────

    def get(self, path, query=None):
        call = {"method": "GET", "path": path, "query": query}
        self.calls.append(call)
        return self._resolve(path, call)

    def post(self, path, body=None, content_type="application/json"):
        self._record("POST", path, body)
        return self._resolve(path, {"path": path, "body": body})

    def put(self, path, body=None):
        self._record("PUT", path, body)
        return self._resolve(path, {"path": path, "body": body})

    def delete(self, path):
        self._record("DELETE", path)
        return self._resolve(path, {"path": path})

    def path_exists(self, abs_path):
        self.calls.append({"method": "PATH_EXISTS", "path": abs_path})
        return {"name": abs_path} if abs_path in self.fs_existing else None

    def poll_fs_task(self, task_id, timeout=120, interval=1.0):
        self.calls.append({"method": "POLL_FS", "task_id": task_id})
        return {"id": task_id, "state": "done"}

    def poll_vm_disk_task(self, task_id, timeout=600, interval=1.0):
        self.calls.append({"method": "POLL_VM_DISK", "task_id": task_id})
        return {"id": task_id, "done": True}

    def delete_vm_disk_task(self, task_id):
        self.calls.append({"method": "DELETE_VM_DISK_TASK", "task_id": task_id})


# ── Module stub ──────────────────────────────────────────────────────────


class StubModule(object):
    def __init__(self, params, check_mode=False):
        self.params = params
        self.check_mode = check_mode
        self.warnings = []
        self.failures = []

    def warn(self, msg):
        self.warnings.append(msg)

    def fail_json(self, **kw):
        self.failures.append(kw)
        raise SystemExit(kw)


def _base_params(**overrides):
    params = dict(
        name="fbx-vm-01",
        state="present",
        started=True,
        vcpus=2,
        memory=1024,
        os="unknown",
        enable_screen=False,
        disk=dict(
            source_image="/Disque 1/VMs/base.qcow2",
            name="fbx-vm-01.qcow2",
            dir="/Disque 1/VMs",
        ),
        cloudinit_file=None,
        cloudinit_userdata=None,
        force_recreate=False,
        delete_disk=False,
        stop_timeout=60,
        start_timeout=30,
        force_kill=False,
        task_timeout=600,
    )
    params.update(overrides)
    return params


# ── Tests ────────────────────────────────────────────────────────────────


def test_cascade_delete_captures_disk_path_before_delete():
    """Regression: capture disk_path from the live VM dict, then DELETE; if
    delete_disk is true, fs/rm both the disk and the .efivars file."""
    client = RecordingClient()
    vm = {
        "id": 7,
        "name": "fbx-vm-01",
        "status": "running",
        "disk_path": encode_path("/Disque 1/VMs/fbx-vm-01.qcow2"),
    }
    client.responses["/vm/7/stop"] = None
    # First GET on /vm/7 after stop → stopped status; subsequent fs paths exist.
    client.responses["/vm/7"] = {**vm, "status": "stopped"}
    client.responses["/vm/7"] = {**vm, "status": "stopped"}
    client.fs_existing.add("/Disque 1/VMs/fbx-vm-01.qcow2")
    client.fs_existing.add("/Disque 1/VMs/fbx-vm-01.qcow2.efivars")
    client.responses["/fs/rm/"] = {"id": 42, "state": "running"}
    client.responses["/vm/7"] = {**vm, "status": "stopped"}  # poll inside _stop_vm

    cleartext = vm_module._cascade_delete(
        client, vm,
        delete_disk=True,
        stop_timeout=5,
        force_kill=False,
        task_timeout=10,
    )

    assert cleartext == "/Disque 1/VMs/fbx-vm-01.qcow2"

    # Extract the ordered method/path pairs that mutate state.
    sequence = [
        (c["method"], c["path"])
        for c in client.calls
        if c["method"] in ("POST", "DELETE")
    ]
    # 1. stop the VM, 2. delete VM record, 3. fs/rm the disk, 4. fs/rm efivars.
    assert sequence[0] == ("POST", "/vm/7/stop")
    delete_idx = next(i for i, s in enumerate(sequence) if s == ("DELETE", "/vm/7"))
    rm_indices = [i for i, s in enumerate(sequence) if s == ("POST", "/fs/rm/")]
    # disk_path captured & DELETE happens BEFORE any fs/rm
    assert all(i > delete_idx for i in rm_indices), \
        "fs/rm must run after DELETE /vm/{id} but disk_path must be captured before it"
    # Both the qcow2 and the efivars are removed
    rm_targets = [
        c["body"]["files"][0] for c in client.calls
        if c["method"] == "POST" and c["path"] == "/fs/rm/"
    ]
    assert encode_path("/Disque 1/VMs/fbx-vm-01.qcow2") in rm_targets
    assert encode_path("/Disque 1/VMs/fbx-vm-01.qcow2.efivars") in rm_targets


def test_clone_disk_copies_then_renames():
    """fs/cp runs first (placing the source basename in dst_dir), fs/rename
    renames the intermediate to the requested basename."""
    client = RecordingClient()
    client.fs_existing.add("/Disque 1/VMs/base.qcow2")
    client.responses["/fs/cp/"] = {"id": 11, "state": "running"}
    client.responses["/fs/rename/"] = encode_path("/Disque 1/VMs/fbx-vm-01.qcow2")

    vm_module._clone_disk(
        client,
        source_image="/Disque 1/VMs/base.qcow2",
        dst_dir="/Disque 1/VMs",
        dst_name="fbx-vm-01.qcow2",
        task_timeout=10,
    )

    mutating = [(c["method"], c["path"]) for c in client.calls
                if c["method"] in ("POST", "PUT", "DELETE")]
    cp_idx = mutating.index(("POST", "/fs/cp/"))
    rename_idx = mutating.index(("POST", "/fs/rename/"))
    assert cp_idx < rename_idx
    # rename uses the intermediate path (source basename inside dst_dir)
    rename_call = next(c for c in client.calls
                       if c["method"] == "POST" and c["path"] == "/fs/rename/")
    assert rename_call["body"]["src"] == encode_path("/Disque 1/VMs/base.qcow2")
    assert rename_call["body"]["dst"] == "fbx-vm-01.qcow2"


def test_present_existing_vm_running_is_noop():
    """state=present + VM exists, already running, no force_recreate, no drift
    → no POST anywhere (idempotent)."""
    client = RecordingClient()
    client.responses["/vm/"] = [{
        "id": 7,
        "name": "fbx-vm-01",
        "status": "running",
        "vcpus": 2,
        "memory": 1024,
        "os": "unknown",
        "enable_screen": False,
        "disk_path": encode_path("/Disque 1/VMs/fbx-vm-01.qcow2"),
    }]

    module = StubModule(_base_params())
    result = vm_module._ensure_present(module, client)

    assert result["changed"] is False
    mutating = [c for c in client.calls if c["method"] in ("POST", "PUT", "DELETE")]
    assert mutating == [], "Idempotent path must not issue write calls; got %r" % mutating
    assert module.warnings == []


def test_present_existing_vm_with_drift_warns_but_only_reconciles_started():
    """Drift on vcpus → warn, but reconcile only the started state."""
    client = RecordingClient()
    client.responses["/vm/"] = [{
        "id": 7,
        "name": "fbx-vm-01",
        "status": "stopped",  # drift: caller wants started=True
        "vcpus": 1,            # drift: caller wants 2
        "memory": 1024,
        "os": "unknown",
        "enable_screen": False,
        "disk_path": encode_path("/Disque 1/VMs/fbx-vm-01.qcow2"),
    }]
    # _start_vm posts /vm/7/start then polls /vm/7 until status=='running'
    client.responses["/vm/7/start"] = None
    client.responses["/vm/7"] = {
        "id": 7, "name": "fbx-vm-01", "status": "running",
        "disk_path": encode_path("/Disque 1/VMs/fbx-vm-01.qcow2"),
    }

    module = StubModule(_base_params(started=True))
    result = vm_module._ensure_present(module, client)

    assert result["changed"] is True
    assert any("drift" in w.lower() for w in module.warnings), module.warnings
    # We should have STARTed but not POST /vm/ (no create) and not PUT /vm/7
    starts = [c for c in client.calls if c["method"] == "POST" and c["path"] == "/vm/7/start"]
    creates = [c for c in client.calls if c["method"] == "POST" and c["path"] == "/vm/"]
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(starts) == 1
    assert creates == []
    assert puts == []
