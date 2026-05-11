#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: vm_disk
short_description: Manage Freebox VM disk images (clone or blank-create)
version_added: "0.1.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Provide a per-VM disk image on the Freebox NAS, either by cloning a source
    image (typical PRA pattern from a cloud-init base qcow2) or by creating a
    blank qcow2/raw file of a given size.
  - Handles the C(fs_copy) quirk that the Freebox API cannot rename during
    copy (handoff workaround #3) by chaining C(fs/cp/) + C(fs/rename/).
  - On C(state=absent), also removes the C(.efivars) companion file generated
    by the Freebox firmware for aarch64 VMs (handoff workaround #2).
options:
  path:
    description:
      - Absolute target path of the disk on the Freebox NAS, e.g.
        C(/Disque 1/VMs/fbx-vm-01.qcow2).
      - Must end in C(.qcow2) or C(.raw).
    type: path
    required: true
  state:
    description:
      - C(present) — the disk must exist (clone from I(source_image) or create
        blank from I(size_gb)).
      - C(absent) — the disk and its C(.efivars) companion must not exist.
    type: str
    choices: [present, absent]
    default: present
  source_image:
    description:
      - Absolute path of an existing image on the Freebox NAS to clone.
      - Mutually exclusive with I(size_gb).
    type: path
  size_gb:
    description:
      - Size in GiB of a new blank disk to create. Mutually exclusive with
        I(source_image).
    type: float
  disk_type:
    description:
      - Disk format. Only honored when creating a blank disk.
    type: str
    choices: [qcow2, raw]
    default: qcow2
  force:
    description:
      - Recreate the disk even if it already exists at I(path).
    type: bool
    default: false
  delete_efivars:
    description:
      - When I(state=absent), also delete the C(.efivars) file adjacent to the
        disk. The Freebox firmware creates this for aarch64 VMs and does not
        cascade-delete it when the VM is destroyed.
    type: bool
    default: true
  task_timeout:
    description:
      - Seconds to wait for an async disk task before failing. Large image
        clones can take several minutes — adjust accordingly.
    type: int
    default: 600
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Clone AlmaLinux cloud image into a per-VM disk
  mipsou.freebox.vm_disk:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/fbx-vm-01.qcow2
    source_image: /Disque 1/VMs/AlmaLinux-10-GenericCloud.aarch64.qcow2
    state: present

- name: Create a blank 20 GiB raw disk
  mipsou.freebox.vm_disk:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/blank.raw
    size_gb: 20
    disk_type: raw

- name: Remove a VM disk and its efivars companion
  mipsou.freebox.vm_disk:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/fbx-vm-01.qcow2
    state: absent
"""

RETURN = r"""
path:
  description: Absolute path of the managed disk.
  returned: always
  type: str
state:
  description: Resulting state of the disk.
  returned: always
  type: str
efivars_path:
  description: Path of the C(.efivars) companion file that was checked or removed.
  returned: when state=absent
  type: str
"""

import posixpath

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    encode_path,
    sanitize_path,
)


BYTES_PER_GB = 1024 ** 3
ALLOWED_EXTS = (".qcow2", ".raw")


def _basename(path):
    return posixpath.basename(path.rstrip("/"))


def _parent(path):
    return posixpath.dirname(path.rstrip("/")) or "/"


def _remove_if_exists(client, path, timeout):
    info = client.path_exists(path)
    if info is None:
        return False
    task = client.post("/fs/rm/", body={"files": [encode_path(path)]})
    task_id = (task or {}).get("id")
    if task_id is not None:
        client.poll_fs_task(task_id, timeout=timeout)
    return True


def _clone_source_image(client, source_image, path, timeout):
    src_info = client.path_exists(source_image)
    if src_info is None:
        raise FreeboxError("source_image %r does not exist on the Freebox NAS" % source_image)
    dst_dir = _parent(path)
    src_name = _basename(source_image)
    dst_name = _basename(path)
    cp_task = client.post(
        "/fs/cp/",
        body={
            "files": [encode_path(source_image)],
            "dst": encode_path(dst_dir),
            "mode": "overwrite",
        },
    )
    cp_id = (cp_task or {}).get("id")
    if cp_id is None:
        raise FreeboxError("fs/cp did not return a task id")
    client.poll_fs_task(cp_id, timeout=timeout)
    if src_name != dst_name:
        intermediate = posixpath.join(dst_dir, src_name)
        client.post(
            "/fs/rename/",
            body={"src": encode_path(intermediate), "dst": dst_name},
        )


def _create_blank_disk(client, path, size_gb, disk_type, timeout):
    size_bytes = int(size_gb * BYTES_PER_GB)
    task = client.post(
        "/vm/disk/create",
        body={
            "disk_path": encode_path(path),
            "size": size_bytes,
            "disk_type": disk_type,
        },
    )
    task_id = (task or {}).get("id")
    if task_id is None:
        raise FreeboxError("vm/disk/create did not return a task id")
    try:
        client.poll_vm_disk_task(task_id, timeout=timeout)
    finally:
        client.delete_vm_disk_task(task_id)


def _ensure_present(module, client, path):
    source_image = module.params["source_image"]
    size_gb = module.params["size_gb"]
    force = module.params["force"]
    timeout = module.params["task_timeout"]

    existing = client.path_exists(path)
    if existing is not None and not force:
        return dict(changed=False, path=path, state="present")

    if module.check_mode:
        return dict(changed=True, path=path, state="present")

    if existing is not None and force:
        _remove_if_exists(client, path, timeout)

    if source_image:
        try:
            source_image = sanitize_path(source_image)
        except ValueError as exc:
            module.fail_json(msg="invalid source_image: %s" % exc)
        _clone_source_image(client, source_image, path, timeout)
    else:
        _create_blank_disk(client, path, size_gb, module.params["disk_type"], timeout)

    return dict(changed=True, path=path, state="present")


def _ensure_absent(module, client, path):
    timeout = module.params["task_timeout"]
    efivars = path + ".efivars"
    delete_efivars = module.params["delete_efivars"]

    disk_existed = client.path_exists(path) is not None
    efivars_existed = delete_efivars and client.path_exists(efivars) is not None
    changed = disk_existed or efivars_existed

    if not changed:
        return dict(changed=False, path=path, state="absent", efivars_path=efivars)

    if module.check_mode:
        return dict(changed=True, path=path, state="absent", efivars_path=efivars)

    if disk_existed:
        _remove_if_exists(client, path, timeout)
    if efivars_existed:
        _remove_if_exists(client, efivars, timeout)

    return dict(changed=True, path=path, state="absent", efivars_path=efivars)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        path=dict(type="path", required=True),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        source_image=dict(type="path"),
        size_gb=dict(type="float"),
        disk_type=dict(type="str", default="qcow2", choices=["qcow2", "raw"]),
        force=dict(type="bool", default=False),
        delete_efivars=dict(type="bool", default=True),
        task_timeout=dict(type="int", default=600),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        mutually_exclusive=[("source_image", "size_gb")],
    )

    try:
        path = sanitize_path(module.params["path"])
    except ValueError as exc:
        module.fail_json(msg="invalid path: %s" % exc)

    if not path.lower().endswith(ALLOWED_EXTS):
        module.fail_json(msg="path must end in .qcow2 or .raw (got %r)" % path)

    state = module.params["state"]
    if state == "present" and not module.params["source_image"] and module.params["size_gb"] is None:
        module.fail_json(msg="state=present requires either source_image or size_gb")

    client = FreeboxClient(module)

    try:
        if state == "absent":
            result = _ensure_absent(module, client, path)
        else:
            result = _ensure_present(module, client, path)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
