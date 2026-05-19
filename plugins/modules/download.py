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
module: download
short_description: Manage individual Freebox download tasks
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Add, remove, or pause/resume individual download tasks on the Freebox.
  - To list current tasks, use M(mipsou.freebox.download_config) or gather facts
    from C(GET /downloads/).
options:
  url_to_download:
    description:
      - URL to add as a new download task. Required when I(state=present) and no
        I(id) is given.
    type: str
  id:
    description:
      - Numeric task ID. Required for I(state=absent), I(state=stopped), and
        I(state=downloading).
    type: int
  state:
    description:
      - C(present) — add a download task by I(url_to_download). Idempotency is
        not guaranteed (the API does not deduplicate by URL); run once.
      - C(absent) — delete the task identified by I(id).
      - C(stopped) — pause the task identified by I(id).
      - C(downloading) — resume the task identified by I(id).
      - C(facts) — return the list of all tasks as
        C(ansible_facts.freebox_downloads); I(changed=false) always.
    type: str
    choices: [present, absent, stopped, downloading, facts]
    default: present
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Add a download
  mipsou.freebox.download:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    url_to_download: https://example.com/file.iso
    state: present

- name: Delete task 42
  mipsou.freebox.download:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    id: 42
    state: absent

- name: Pause task 42
  mipsou.freebox.download:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    id: 42
    state: stopped

- name: List all downloads as facts
  mipsou.freebox.download:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    state: facts
  register: dl
"""

RETURN = r"""
task:
  description: The affected task dict (present/absent/stopped/downloading).
  type: dict
  returned: when state != facts
changed:
  description: Whether the Freebox state was modified.
  type: bool
  returned: always
ansible_facts:
  description: Populated when I(state=facts).
  type: dict
  returned: when state=facts
  contains:
    freebox_downloads:
      description: List of download task dicts.
      type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        url_to_download=dict(type="str"),
        id=dict(type="int"),
        state=dict(
            type="str",
            default="present",
            choices=["present", "absent", "stopped", "downloading", "facts"],
        ),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        required_if=[
            ("state", "present", ["url_to_download"]),
            ("state", "absent", ["id"]),
            ("state", "stopped", ["id"]),
            ("state", "downloading", ["id"]),
        ],
    )

    state = module.params["state"]
    task_id = module.params.get("id")
    client = FreeboxClient(module)

    try:
        if state == "facts":
            tasks = client.get("/downloads/") or []
            module.exit_json(changed=False, ansible_facts={"freebox_downloads": tasks})

        elif state == "present":
            if module.check_mode:
                module.exit_json(changed=True, task={"url": module.params["url_to_download"]})
            task = client.post("/downloads/", body={"download_url": module.params["url_to_download"]}) or {}
            module.exit_json(changed=True, task=task)

        elif state == "absent":
            if module.check_mode:
                module.exit_json(changed=True, task={"id": task_id})
            client.delete("/downloads/%d" % task_id)
            module.exit_json(changed=True, task={"id": task_id})

        else:  # stopped or downloading
            if module.check_mode:
                module.exit_json(changed=True, task={"id": task_id, "status": state})
            updated = client.put("/downloads/%d" % task_id, body={"status": state}) or {}
            module.exit_json(changed=True, task=updated)

    except FreeboxError as exc:
        module.fail_json(msg=str(exc))


if __name__ == "__main__":
    main()
