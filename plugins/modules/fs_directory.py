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
module: fs_directory
short_description: Manage directories on the Freebox NAS
version_added: "0.2.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Ensure a directory exists or is absent on the Freebox NAS.
  - C(state=present) creates the directory via C(POST /fs/mkdir/) if it does not
    exist and fails if a non-directory entry (file or symlink) occupies the path.
  - C(state=absent) removes the directory and all its contents via C(POST /fs/rm/).
    Fails if the path is a file or symlink — use M(mipsou.freebox.fs_file) for
    those.
  - Both mkdir and rm operations are asynchronous; this module polls until
    completion by default.
options:
  path:
    description:
      - Absolute target path on the Freebox NAS, e.g. C(/Disque 1/VMs/backups).
      - The user-visible storage prefix varies per model (C(/Disque 1/) on
        Delta, C(/Freebox/) on Revolution). No magic default — provide the path
        as it appears in Freebox OS.
    type: path
    required: true
  state:
    description:
      - C(present) — the directory must exist. Created if absent.
      - C(absent) — the directory must not exist. Removed (recursively) if present.
    type: str
    choices: [present, absent]
    default: present
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
- name: Ensure backup directory exists
  mipsou.freebox.fs_directory:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/backups
    state: present

- name: Remove a VM working directory
  mipsou.freebox.fs_directory:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    path: /Disque 1/VMs/obsolete
    state: absent
"""

RETURN = r"""
path:
  description: Absolute path that was acted on.
  returned: always
  type: str
state:
  description: Resulting state of the directory.
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


def _ensure_present(module, client, path):
    info = client.path_exists(path)
    if info is not None:
        entry_type = info.get("type", "")
        if entry_type != "dir":
            module.fail_json(
                msg="path %r exists but is a %s, not a directory" % (path, entry_type or "unknown")
            )
        return dict(changed=False, path=path, state="present")

    if module.check_mode:
        return dict(changed=True, path=path, state="present")

    parent = posixpath.dirname(path.rstrip("/")) or "/"
    dirname = posixpath.basename(path.rstrip("/"))

    # POST /fs/mkdir/ returns a bare string task ID (not an FSTask object like rm/cp).
    raw_id = client.post("/fs/mkdir/", body={"parent": encode_path(parent), "dirname": dirname})
    try:
        task_id = int(raw_id)
    except (TypeError, ValueError):
        task_id = raw_id

    if module.params["wait"] and task_id is not None:
        client.poll_fs_task(task_id, timeout=module.params["task_timeout"])

    return dict(changed=True, path=path, state="present", task_id=task_id)


def _ensure_absent(module, client, path):
    info = client.path_exists(path)
    if info is None:
        return dict(changed=False, path=path, state="absent")

    entry_type = info.get("type", "")
    if entry_type != "dir":
        module.fail_json(
            msg="path %r is a %s, not a directory — use mipsou.freebox.fs_file to remove files"
            % (path, entry_type or "unknown")
        )

    if module.check_mode:
        return dict(changed=True, path=path, state="absent")

    task = client.post("/fs/rm/", body={"files": [encode_path(path)]})
    task_id = (task or {}).get("id")

    if module.params["wait"] and task_id is not None:
        client.poll_fs_task(task_id, timeout=module.params["task_timeout"])

    return dict(changed=True, path=path, state="absent", task_id=task_id)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        path=dict(type="path", required=True),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        wait=dict(type="bool", default=True),
        task_timeout=dict(type="int", default=120),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    try:
        path = sanitize_path(module.params["path"])
    except ValueError as exc:
        module.fail_json(msg="invalid path: %s" % exc)

    client = FreeboxClient(module)

    try:
        if module.params["state"] == "absent":
            result = _ensure_absent(module, client, path)
        else:
            result = _ensure_present(module, client, path)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
