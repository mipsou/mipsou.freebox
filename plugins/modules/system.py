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
module: system
short_description: Gather Freebox system facts and optionally reboot
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Reads C(GET /system/) and exposes the result as
    C(ansible_facts.freebox_system).
  - When I(reboot=true), issues C(POST /system/reboot/) and returns
    C(changed=true). In check_mode the POST is skipped but C(changed=true)
    is still reported.
  - When I(reboot=false) (the default) the module is always C(changed=false).
options:
  reboot:
    description:
      - When C(true), reboot the Freebox after gathering facts.
      - The Freebox does not return a structured confirmation; the POST
        returns an empty success envelope.
    type: bool
    default: false
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Gather Freebox system facts
  mipsou.freebox.system:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
  register: fbx_system

- name: Show firmware version
  ansible.builtin.debug:
    var: ansible_facts.freebox_system.firmware_version

- name: Reboot the Freebox
  mipsou.freebox.system:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    reboot: true
"""

RETURN = r"""
ansible_facts:
  description: System information from the Freebox.
  returned: always
  type: dict
  contains:
    freebox_system:
      description: Raw dict from C(GET /system/).
      type: dict
      sample:
        firmware_version: "4.10.2"
        board_name: "fbxgw7r"
        uptime_val: 37075
        mac: "20:66:CF:75:8B:2E"
changed:
  description: True only when a reboot was issued (or would be in check_mode).
  type: bool
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def _collect_facts(client):
    """Return system facts dict from GET /system/. Returns {} on None."""
    return client.get("/system/") or {}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        reboot=dict(type="bool", default=False),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
    )

    client = FreeboxClient(module)
    try:
        info = _collect_facts(client)

        if not module.params["reboot"]:
            module.exit_json(
                changed=False,
                ansible_facts={"freebox_system": info},
            )

        # reboot=true
        if module.check_mode:
            module.exit_json(
                changed=True,
                ansible_facts={"freebox_system": info},
            )

        client.post("/system/reboot/")
        module.exit_json(
            changed=True,
            ansible_facts={"freebox_system": info},
        )
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))


if __name__ == "__main__":
    main()
