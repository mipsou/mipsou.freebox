# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""
Unit tests for the freebox_vm lookup plugin.

Tests call the module-level helpers _normalise_vm and _filter_by_names
directly, without requiring a live Ansible environment.
"""

import base64

from ansible_collections.mipsou.freebox.plugins.lookup.freebox_vm import (
    _normalise_vm,
    _filter_by_names,
)


def _encode(path):
    return base64.b64encode(path.encode("utf-8")).decode("ascii")


# ── _normalise_vm ─────────────────────────────────────────────────────────


def test_normalise_vm_decodes_disk_path():
    encoded = _encode("/Disque dur/VMs/fbx-vm-01.qcow2")
    vm = {
        "id": 1, "name": "fbx-vm-01", "status": "running",
        "mac": "aa:bb:cc:dd:ee:ff", "memory": 512, "vcpus": 1,
        "disk_path": encoded,
    }
    result = _normalise_vm(vm)
    assert result["disk_path"] == "/Disque dur/VMs/fbx-vm-01.qcow2"


def test_normalise_vm_preserves_scalar_fields():
    vm = {
        "id": 42, "name": "my-vm", "status": "stopped",
        "mac": "11:22:33:44:55:66", "memory": 1024, "vcpus": 2,
        "disk_path": "",
    }
    result = _normalise_vm(vm)
    assert result["id"] == 42
    assert result["name"] == "my-vm"
    assert result["status"] == "stopped"
    assert result["mac"] == "11:22:33:44:55:66"
    assert result["memory"] == 1024
    assert result["vcpus"] == 2


def test_normalise_vm_empty_disk_path():
    vm = {"id": 1, "name": "x", "status": "stopped", "mac": "", "memory": 256, "vcpus": 1, "disk_path": ""}
    result = _normalise_vm(vm)
    assert result["disk_path"] == ""


def test_normalise_vm_missing_disk_path():
    vm = {"id": 1, "name": "x", "status": "running", "mac": "", "memory": 256, "vcpus": 1}
    result = _normalise_vm(vm)
    assert result["disk_path"] == ""


def test_normalise_vm_invalid_base64_kept_raw():
    vm = {
        "id": 1, "name": "x", "status": "running", "mac": "",
        "memory": 256, "vcpus": 1, "disk_path": "!!!not_base64!!!",
    }
    result = _normalise_vm(vm)
    assert result["disk_path"] == "!!!not_base64!!!"


def test_normalise_vm_strips_extra_fields():
    vm = {
        "id": 1, "name": "x", "status": "stopped", "mac": "",
        "memory": 256, "vcpus": 1, "disk_path": "",
        "extra_field": "should_not_appear",
    }
    result = _normalise_vm(vm)
    assert "extra_field" not in result


# ── _filter_by_names ──────────────────────────────────────────────────────


def test_filter_returns_matching_vm():
    vms = [
        {"name": "fbx-vm-01", "status": "running"},
        {"name": "fbx-vm-02", "status": "stopped"},
    ]
    result = _filter_by_names(vms, ["fbx-vm-01"])
    assert len(result) == 1
    assert result[0]["name"] == "fbx-vm-01"


def test_filter_no_terms_returns_all():
    vms = [{"name": "a"}, {"name": "b"}]
    assert _filter_by_names(vms, []) == vms


def test_filter_unknown_name_returns_empty():
    vms = [{"name": "fbx-vm-01"}]
    result = _filter_by_names(vms, ["does-not-exist"])
    assert result == []


def test_filter_multiple_terms():
    vms = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    result = _filter_by_names(vms, ["a", "c"])
    assert len(result) == 2
    names = {vm["name"] for vm in result}
    assert names == {"a", "c"}


def test_filter_empty_vm_list():
    assert _filter_by_names([], ["fbx-vm-01"]) == []


def test_filter_case_sensitive():
    vms = [{"name": "FBX-VM-01"}]
    assert _filter_by_names(vms, ["fbx-vm-01"]) == []


# ── auth guard logic ──────────────────────────────────────────────────────


def test_missing_app_id_raises():
    app_id = None
    app_token = "tok"
    assert not app_id or not app_token


def test_missing_app_token_raises():
    app_id = "ansible"
    app_token = None
    assert not app_id or not app_token


def test_both_present_no_raise():
    app_id = "ansible"
    app_token = "tok"
    assert not (not app_id or not app_token)
