#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: EUPL-1.2

from __future__ import absolute_import, division, print_function, unicode_literals

__metaclass__ = type

DOCUMENTATION = r"""
---
module: fs_file
short_description: Manage files on the Freebox NAS
version_added: "0.1.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Ensure files exist (optionally cloned from a source) or are absent on the
    Freebox NAS (Pop, Delta, Revolution, V7+).
  - Operations are asynchronous on the Freebox; this module polls the task
    queue until completion by default.
options:
  path:
    description:
      - Absolute target path on the Freebox NAS, e.g. C(/Disque 1/VMs/vm.qcow2).
      - The user-visible storage prefix varies per model (C(/Disque 1/) on
        Delta, C(/Freebox/) on Revolution). No magic default — provide the path
        as it appears in Freebox OS.
    type: path
    required: true
  state:
    description:
      - C(present) — the file must exist. Combine with I(src) to clone.
      - C(absent) — the file must not exist.
    type: str
    choices: [present, absent]
    default: present
  src:
    description:
      - Absolute source path on the Freebox NAS to clone from. Only used when
        I(state=present).
      - Honors the Freebox API quirk that C(fs_copy) copies into a directory
        keeping the source filename; this module renames atomically when
        I(src) and I(path) basenames differ.
    type: path
  force:
    description:
      - When I(state=present) and I(src) is set, overwrite I(path) if it
        already exists. Default is to leave existing destinations untouched
        (idempotent).
    type: bool
    default: false
  wait:
    description:
      - Wait for asynchronous filesystem tasks to complete before returning.
    type: bool
    default: true
  task_timeout:
    description:
      - Seconds to wait for an async task before failing.
    type: int
    default: 120
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Remove a stale VM disk
  mipsou.freebox.fs_file:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/fbx-vm-01.qcow2
    state: absent

- name: Clone a base image to a per-VM disk (idempotent)
  mipsou.freebox.fs_file:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/fbx-vm-01.qcow2
    src: /Disque 1/VMs/AlmaLinux-10-GenericCloud.qcow2
    state: present

- name: Force-refresh the disk from a newer base image
  mipsou.freebox.fs_file:
    url: https://mafreebox.freebox.fr
    app_id: community-freebox-ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/fbx-vm-01.qcow2
    src: /Disque 1/VMs/AlmaLinux-10-GenericCloud.qcow2
    force: true
"""

RETURN = r"""
path:
  description: Absolute path that was acted on.
  returned: always
  type: str
state:
  description: Resulting state of the file.
  returned: always
  type: str
  sample: present
task_id:
  description: ID of the asynchronous task triggered, if any.
  returned: when an FS task was created
  type: int
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


def _basename(path):
    return posixpath.basename(path.rstrip("/"))


def _parent(path):
    parent = posixpath.dirname(path.rstrip("/"))
    return parent or "/"


def _ensure_absent(module, client, path):
    info = client.path_exists(path)
    if info is None:
        return dict(changed=False, path=path, state="absent")
    if module.check_mode:
        return dict(changed=True, path=path, state="absent")
    task = client.post("/fs/rm/", body={"files": [encode_path(path)]})
    task_id = (task or {}).get("id")
    if module.params["wait"] and task_id is not None:
        client.poll_fs_task(task_id, timeout=module.params["task_timeout"])
    return dict(changed=True, path=path, state="absent", task_id=task_id)


def _ensure_present(module, client, path, src, force):
    dst_info = client.path_exists(path)

    if src is None:
        if dst_info is None:
            module.fail_json(msg="path %r does not exist and no src was provided to materialize it" % path)
        return dict(changed=False, path=path, state="present")

    src_info = client.path_exists(src)
    if src_info is None:
        module.fail_json(msg="src %r does not exist on the Freebox NAS" % src)

    if dst_info is not None and not force:
        return dict(changed=False, path=path, state="present")

    if module.check_mode:
        return dict(changed=True, path=path, state="present")

    # If destination exists and force=true, remove it first so /fs/cp doesn't
    # leave a duplicate when src and dst share the same basename in different
    # directories.
    if dst_info is not None and force:
        rm_task = client.post("/fs/rm/", body={"files": [encode_path(path)]})
        rm_id = (rm_task or {}).get("id")
        if rm_id is not None:
            client.poll_fs_task(rm_id, timeout=module.params["task_timeout"])

    dst_dir = _parent(path)
    dst_name = _basename(path)
    src_name = _basename(src)

    cp_task = client.post(
        "/fs/cp/",
        body={
            "files": [encode_path(src)],
            "dst": encode_path(dst_dir),
            "mode": "overwrite" if force else "skip",
        },
    )
    cp_id = (cp_task or {}).get("id")
    if cp_id is None:
        raise FreeboxError("fs/cp did not return a task id")
    client.poll_fs_task(cp_id, timeout=module.params["task_timeout"])

    # /fs/cp/ keeps the source basename. Rename if the user wants a different
    # destination name (handoff workaround #3).
    if src_name != dst_name:
        intermediate = posixpath.join(dst_dir, src_name)
        client.post(
            "/fs/rename/",
            body={"src": encode_path(intermediate), "dst": dst_name},
        )

    return dict(changed=True, path=path, state="present", task_id=cp_id)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        path=dict(type="path", required=True),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        src=dict(type="path"),
        force=dict(type="bool", default=False),
        wait=dict(type="bool", default=True),
        task_timeout=dict(type="int", default=120),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    try:
        path = sanitize_path(module.params["path"])
    except ValueError as exc:
        module.fail_json(msg="invalid path: %s" % exc)

    src = module.params["src"]
    if src is not None:
        try:
            src = sanitize_path(src)
        except ValueError as exc:
            module.fail_json(msg="invalid src: %s" % exc)

    client = FreeboxClient(module)

    try:
        if module.params["state"] == "absent":
            result = _ensure_absent(module, client, path)
        else:
            result = _ensure_present(module, client, path, src, module.params["force"])
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
