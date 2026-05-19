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
module: info_storage
short_description: Gather Freebox storage facts (disks, partitions, RAID)
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Collect storage information from the Freebox and return it as
    C(ansible_facts.freebox_storage).
  - Always reports C(changed=false).
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Gather storage facts
  mipsou.freebox.info_storage:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
  register: storage_info
# storage_info.ansible_facts.freebox_storage.disks
# storage_info.ansible_facts.freebox_storage.partitions
# storage_info.ansible_facts.freebox_storage.raid
"""

RETURN = r"""
ansible_facts:
  description: Storage facts.
  type: dict
  returned: always
  contains:
    freebox_storage:
      description: Storage details.
      type: dict
      contains:
        disks:
          description: List of disk dicts.
          type: list
        partitions:
          description: List of partition dicts.
          type: list
        raid:
          description: List of RAID array dicts.
          type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def main():
    module = AnsibleModule(argument_spec=dict(COMMON_ARGSPEC), supports_check_mode=True)
    client = FreeboxClient(module)
    try:
        disks = client.get("/storage/disk/") or []
        partitions = client.get("/storage/partition/") or []
        raid = client.get("/storage/raid/") or []
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(
        changed=False,
        ansible_facts={
            "freebox_storage": {
                "disks": disks,
                "partitions": partitions,
                "raid": raid,
            }
        },
    )


if __name__ == "__main__":
    main()
