#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: vm
short_description: Manage Freebox virtual machines declaratively
version_added: "0.1.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Create, delete, start, stop and recreate VMs on a Freebox server.
  - On C(state=present) for a new VM, clones the I(disk.source_image) into
    I(disk.dir)/I(disk.name) before issuing C(POST /vm/) (handoff workaround
    #3 — the Freebox C(fs_copy) cannot rename atomically).
  - On C(state=absent) with I(delete_disk=true), captures the C(disk_path)
    before deleting the VM and removes both the disk and its C(.efivars)
    companion file (handoff workaround #2).
  - Config drift (vcpus, memory, cloud-init) is reported as a warning; use
    I(force_recreate=true) to apply changes.
options:
  name:
    description:
      - VM name. Used as the lookup key. Must be unique on the Freebox; the
        module fails if multiple VMs share the same name.
    type: str
    required: true
  state:
    description:
      - C(present) — VM must exist; combine with I(started) to control
        runtime state.
      - C(absent) — VM must not exist; pair with I(delete_disk=true) to also
        remove the qcow2 + efivars files.
    type: str
    choices: [present, absent]
    default: present
  started:
    description:
      - When I(state=present), whether the VM should be running. The module
        polls C(GET /vm/{id}) after start/stop until the status flips.
    type: bool
    default: true
  vcpus:
    description: Number of vCPUs (1–8). Required when creating a new VM.
    type: int
  memory:
    description: Memory in MiB. Required when creating a new VM.
    type: int
  os:
    description: Guest OS hint shown in Freebox OS.
    type: str
    choices: [fedora, debian, ubuntu, unknown]
    default: unknown
  enable_screen:
    description: Expose the QEMU VNC console.
    type: bool
    default: false
  disk:
    description:
      - Disk specification. Required when creating a new VM.
      - On steady-state runs the existing VM's C(disk_path) is reused; this
        block is then ignored.
    type: dict
    suboptions:
      source_image:
        description: Absolute path of the source image to clone (qcow2/raw).
        type: path
        required: true
      name:
        description: Filename of the per-VM disk (e.g. C(fbx-vm-01.qcow2)).
        type: str
        required: true
      dir:
        description: Directory holding the per-VM disk on the Freebox NAS.
        type: path
        required: true
  cloudinit_file:
    description:
      - Path on the Ansible controller to a cloud-init userdata file.
      - The Freebox firmware caps cloud-init userdata at 4096 characters
        (handoff workaround #4); the module fails fast above this limit.
      - Mutually exclusive with I(cloudinit_userdata).
    type: path
  cloudinit_userdata:
    description:
      - Inline cloud-init userdata. Capped at 4096 characters.
      - Mutually exclusive with I(cloudinit_file).
    type: str
  force_recreate:
    description:
      - Delete and recreate the VM even if it already exists. Combine with
        I(delete_disk=true) for a full rebuild including the qcow2.
      - With I(delete_disk=false) (the default) the existing disk file is
        kept and the new VM boots off it — I(disk.source_image) is NOT
        re-applied. Set I(delete_disk=true) when you want a clean clone.
    type: bool
    default: false
  delete_disk:
    description:
      - When deleting (C(state=absent) or I(force_recreate=true)), also
        remove the VM's qcow2 and C(.efivars) files. Default C(false) by
        safety; the Freebox VM-delete API does not cascade.
    type: bool
    default: false
  stop_timeout:
    description: Seconds to wait for ACPI stop before failing (or killing).
    type: int
    default: 60
  start_timeout:
    description: Seconds to wait for the VM to reach C(running) after start.
    type: int
    default: 30
  force_kill:
    description:
      - If ACPI stop times out, send C(POST /vm/{id}/kill) instead of failing.
      - Risk of data corruption — only set when you know the VM is wedged.
    type: bool
    default: false
  task_timeout:
    description: Seconds to wait for async FS tasks (disk copy/delete).
    type: int
    default: 600
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Ensure VM fbx-vm-01 exists and is running
  mipsou.freebox.vm:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    name: fbx-vm-01
    state: present
    vcpus: 2
    memory: 1024
    disk:
      source_image: /Disque 1/VMs/AlmaLinux-10-GenericCloud.aarch64.qcow2
      name: fbx-vm-01.qcow2
      dir: /Disque 1/VMs
    cloudinit_file: ./cloud-init/fbx-vm-01.yaml
    started: true

- name: Rebuild fbx-vm-01 from scratch (force_recreate + delete_disk)
  mipsou.freebox.vm:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    name: fbx-vm-01
    state: present
    force_recreate: true
    delete_disk: true
    vcpus: 4
    memory: 4096
    disk:
      source_image: /Disque 1/VMs/AlmaLinux-10-GenericCloud.aarch64.qcow2
      name: fbx-vm-01.qcow2
      dir: /Disque 1/VMs
    cloudinit_file: ./cloud-init/fbx-vm-01.yaml

- name: Destroy fbx-vm-01 and its disk
  mipsou.freebox.vm:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    name: fbx-vm-01
    state: absent
    delete_disk: true
"""

RETURN = r"""
name:
  description: Name of the managed VM.
  returned: always
  type: str
vm:
  description: Current Freebox VM dict (after reconciliation), or null if absent.
  returned: always
  type: dict
disk_path:
  description: Cleartext absolute path of the VM disk acted on.
  returned: when known
  type: str
"""

import posixpath
import time

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    decode_path,
    encode_path,
    sanitize_path,
)


CLOUDINIT_MAX = 4096
DRIFT_FIELDS = ("vcpus", "memory", "os", "enable_screen")


def _read_cloudinit(module):
    """Resolve the cloud-init userdata as a UTF-8 string, or None."""
    inline = module.params["cloudinit_userdata"]
    if inline is not None:
        return inline
    file_path = module.params["cloudinit_file"]
    if not file_path:
        return None
    try:
        with open(file_path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        module.fail_json(msg="cannot read cloudinit_file %r: %s" % (file_path, exc))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        module.fail_json(msg="cloudinit_file %r is not valid UTF-8: %s" % (file_path, exc))


def _find_vm_by_name(client, name):
    vms = client.get("/vm/") or []
    matches = [vm for vm in vms if vm.get("name") == name]
    if len(matches) > 1:
        ids = [vm.get("id") for vm in matches]
        raise FreeboxError("VM name %r is ambiguous: ids %r" % (name, ids))
    return matches[0] if matches else None


def _wait_for_status(client, vm_id, target_status, timeout, interval=1.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        vm = client.get("/vm/{0}".format(vm_id)) or {}
        last = vm.get("status")
        if last == target_status:
            return vm
        time.sleep(interval)
    raise FreeboxError(
        "VM %d did not reach status %r within %ds (last: %r)"
        % (vm_id, target_status, timeout, last)
    )


def _stop_vm(client, vm, stop_timeout, force_kill):
    if vm.get("status") == "stopped":
        return
    vm_id = vm["id"]
    client.post("/vm/{0}/stop".format(vm_id))
    try:
        _wait_for_status(client, vm_id, "stopped", stop_timeout)
    except FreeboxError:
        if not force_kill:
            raise
        client.post("/vm/{0}/kill".format(vm_id))
        _wait_for_status(client, vm_id, "stopped", 15)


def _start_vm(client, vm_id, start_timeout):
    client.post("/vm/{0}/start".format(vm_id))
    return _wait_for_status(client, vm_id, "running", start_timeout)


def _remove_path(client, abs_path, task_timeout):
    info = client.path_exists(abs_path)
    if info is None:
        return False
    task = client.post("/fs/rm/", body={"files": [encode_path(abs_path)]})
    task_id = (task or {}).get("id")
    if task_id is not None:
        client.poll_fs_task(task_id, timeout=task_timeout)
    return True


def _clone_disk(client, source_image, dst_dir, dst_name, task_timeout):
    src_info = client.path_exists(source_image)
    if src_info is None:
        raise FreeboxError("disk.source_image %r does not exist on the Freebox NAS" % source_image)
    cp = client.post(
        "/fs/cp/",
        body={
            "files": [encode_path(source_image)],
            "dst": encode_path(dst_dir),
            "mode": "overwrite",
        },
    )
    cp_id = (cp or {}).get("id")
    if cp_id is None:
        raise FreeboxError("fs/cp did not return a task id")
    client.poll_fs_task(cp_id, timeout=task_timeout)
    src_name = posixpath.basename(source_image.rstrip("/"))
    if src_name != dst_name:
        intermediate = posixpath.join(dst_dir, src_name)
        client.post(
            "/fs/rename/",
            body={"src": encode_path(intermediate), "dst": dst_name},
        )


def _build_create_body(module, disk_path_abs, userdata):
    body = {
        "name": module.params["name"],
        "memory": module.params["memory"],
        "vcpus": module.params["vcpus"],
        "disk_path": encode_path(disk_path_abs),
        "disk_type": "qcow2" if disk_path_abs.lower().endswith(".qcow2") else "raw",
        "os": module.params["os"],
        "enable_screen": module.params["enable_screen"],
    }
    if userdata is not None:
        body["enable_cloudinit"] = True
        body["cloudinit_userdata"] = userdata
    return body


def _validate_disk_spec(module):
    disk = module.params["disk"]
    if disk is None:
        module.fail_json(msg="disk is required to create a new VM")
    try:
        dst_dir = sanitize_path(disk["dir"])
        source_image = sanitize_path(disk["source_image"])
    except ValueError as exc:
        module.fail_json(msg="invalid disk path: %s" % exc)
    name = disk["name"]
    if "/" in name or "\\" in name:
        module.fail_json(msg="disk.name must be a bare filename, not a path")
    return source_image, dst_dir, name


def _detect_drift(module, vm, userdata):
    diverged = []
    for field in DRIFT_FIELDS:
        wanted = module.params.get(field)
        if wanted is None:
            continue
        if vm.get(field) != wanted:
            diverged.append(field)
    if userdata is not None:
        observed = vm.get("cloudinit_userdata") or ""
        if observed != userdata:
            diverged.append("cloudinit_userdata")
    elif vm.get("enable_cloudinit") and module.params["cloudinit_userdata"] is None and not module.params["cloudinit_file"]:
        # Userdata is set on the box but we have nothing to compare to.
        # Don't flag — caller may intentionally leave it untouched.
        pass
    return diverged


def _cascade_delete(client, vm, delete_disk, stop_timeout, force_kill, task_timeout):
    vm_id = vm["id"]
    disk_path_b64 = vm.get("disk_path") or ""
    _stop_vm(client, vm, stop_timeout, force_kill)
    client.delete("/vm/{0}".format(vm_id))
    cleartext = None
    if delete_disk and disk_path_b64:
        try:
            cleartext = decode_path(disk_path_b64)
        except Exception as exc:
            raise FreeboxError("cannot decode disk_path %r: %s" % (disk_path_b64, exc))
        _remove_path(client, cleartext, task_timeout)
        _remove_path(client, cleartext + ".efivars", task_timeout)
    return cleartext


def _create_vm(module, client, userdata):
    source_image, dst_dir, disk_name = _validate_disk_spec(module)
    disk_path_abs = posixpath.join(dst_dir, disk_name)

    if not client.path_exists(disk_path_abs):
        _clone_disk(client, source_image, dst_dir, disk_name, module.params["task_timeout"])

    body = _build_create_body(module, disk_path_abs, userdata)
    created = client.post("/vm/", body=body)
    return created, disk_path_abs


def _ensure_started_state(client, vm, want_started, start_timeout, stop_timeout, force_kill):
    status = vm.get("status")
    if want_started and status != "running":
        return True, _start_vm(client, vm["id"], start_timeout)
    if not want_started and status != "stopped":
        _stop_vm(client, vm, stop_timeout, force_kill)
        return True, client.get("/vm/{0}".format(vm["id"]))
    return False, vm


def _ensure_absent(module, client):
    vm = _find_vm_by_name(client, module.params["name"])
    if vm is None:
        return dict(changed=False, name=module.params["name"], vm=None)
    if module.check_mode:
        return dict(changed=True, name=module.params["name"], vm=vm)
    cleartext = _cascade_delete(
        client, vm,
        delete_disk=module.params["delete_disk"],
        stop_timeout=module.params["stop_timeout"],
        force_kill=module.params["force_kill"],
        task_timeout=module.params["task_timeout"],
    )
    result = dict(changed=True, name=module.params["name"], vm=None)
    if cleartext:
        result["disk_path"] = cleartext
    return result


def _ensure_present(module, client):
    name = module.params["name"]
    userdata = _read_cloudinit(module)
    if userdata is not None and len(userdata.encode("utf-8")) > CLOUDINIT_MAX:
        module.fail_json(
            msg="cloud-init userdata exceeds %d bytes (Freebox firmware limit); "
                "use '#include https://...' to source a longer config" % CLOUDINIT_MAX
        )

    existing = _find_vm_by_name(client, name)
    want_started = module.params["started"]

    if existing is None:
        for field in ("vcpus", "memory"):
            if module.params[field] is None:
                module.fail_json(msg="%s is required to create a new VM" % field)
        if module.check_mode:
            return dict(changed=True, name=name, vm=None)
        created, disk_path_abs = _create_vm(module, client, userdata)
        if want_started:
            created = _start_vm(client, created["id"], module.params["start_timeout"])
        return dict(changed=True, name=name, vm=created, disk_path=disk_path_abs)

    if module.params["force_recreate"]:
        if module.check_mode:
            return dict(changed=True, name=name, vm=existing)
        _cascade_delete(
            client, existing,
            delete_disk=module.params["delete_disk"],
            stop_timeout=module.params["stop_timeout"],
            force_kill=module.params["force_kill"],
            task_timeout=module.params["task_timeout"],
        )
        created, disk_path_abs = _create_vm(module, client, userdata)
        if want_started:
            created = _start_vm(client, created["id"], module.params["start_timeout"])
        return dict(changed=True, name=name, vm=created, disk_path=disk_path_abs)

    diverged = _detect_drift(module, existing, userdata)
    if diverged:
        module.warn(
            "VM %r has drifted on %s; set force_recreate=true to apply changes"
            % (name, ", ".join(diverged))
        )

    if module.check_mode:
        # Predict whether started-state will change without acting.
        will_change = (
            (want_started and existing.get("status") != "running")
            or (not want_started and existing.get("status") != "stopped")
        )
        return dict(changed=will_change, name=name, vm=existing)

    changed, vm_now = _ensure_started_state(
        client, existing, want_started,
        start_timeout=module.params["start_timeout"],
        stop_timeout=module.params["stop_timeout"],
        force_kill=module.params["force_kill"],
    )
    result = dict(changed=changed, name=name, vm=vm_now)
    disk_b64 = (vm_now or {}).get("disk_path") or ""
    if disk_b64:
        try:
            result["disk_path"] = decode_path(disk_b64)
        except Exception:
            pass
    return result


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        name=dict(type="str", required=True),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        started=dict(type="bool", default=True),
        vcpus=dict(type="int"),
        memory=dict(type="int"),
        os=dict(type="str", default="unknown", choices=["fedora", "debian", "ubuntu", "unknown"]),
        enable_screen=dict(type="bool", default=False),
        disk=dict(type="dict", options=dict(
            source_image=dict(type="path", required=True),
            name=dict(type="str", required=True),
            dir=dict(type="path", required=True),
        )),
        cloudinit_file=dict(type="path"),
        cloudinit_userdata=dict(type="str"),
        force_recreate=dict(type="bool", default=False),
        delete_disk=dict(type="bool", default=False),
        stop_timeout=dict(type="int", default=60),
        start_timeout=dict(type="int", default=30),
        force_kill=dict(type="bool", default=False),
        task_timeout=dict(type="int", default=600),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        mutually_exclusive=[("cloudinit_file", "cloudinit_userdata")],
    )

    client = FreeboxClient(module)
    try:
        if module.params["state"] == "absent":
            result = _ensure_absent(module, client)
        else:
            result = _ensure_present(module, client)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
