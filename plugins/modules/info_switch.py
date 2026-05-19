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
module: info_switch
short_description: Gather Freebox switch facts (ports and statistics)
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Collect Freebox built-in switch port information and statistics, returning
    them as C(ansible_facts.freebox_switch).
  - Always reports C(changed=false).
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Gather switch facts
  mipsou.freebox.info_switch:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
  register: sw
"""

RETURN = r"""
ansible_facts:
  description: Switch facts.
  type: dict
  returned: always
  contains:
    freebox_switch:
      description: Switch details.
      type: dict
      contains:
        ports:
          description: List of switch port dicts with embedded stats.
          type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def _collect_facts(client):
    """Return the freebox_switch facts dict with per-port stats embedded."""
    ports = client.get("/switch/port/") or []
    for port in ports:
        port_id = port.get("id")
        if port_id is not None:
            try:
                port["stats"] = client.get("/switch/port/%s/stats" % port_id) or {}
            except FreeboxError:
                port["stats"] = {}
    return {"ports": ports}


def main():
    module = AnsibleModule(argument_spec=dict(COMMON_ARGSPEC), supports_check_mode=True)
    client = FreeboxClient(module)
    try:
        facts = _collect_facts(client)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(
        changed=False,
        ansible_facts={"freebox_switch": facts},
    )


if __name__ == "__main__":
    main()
