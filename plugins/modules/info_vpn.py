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
module: info_vpn
short_description: Gather Freebox VPN facts (status, connections, client configs)
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Collect VPN information from the Freebox and return it as
    C(ansible_facts.freebox_vpn).
  - Always reports C(changed=false).
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Gather VPN facts
  mipsou.freebox.info_vpn:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
  register: vpn_info
"""

RETURN = r"""
ansible_facts:
  description: VPN facts.
  type: dict
  returned: always
  contains:
    freebox_vpn:
      description: VPN details.
      type: dict
      contains:
        status:
          description: VPN server status dict.
          type: dict
        connections:
          description: List of active VPN connections.
          type: list
        client_configs:
          description: List of VPN client configuration dicts.
          type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def _collect_facts(client):
    """Return the freebox_vpn facts dict."""
    return {
        "status": client.get("/vpn/status/") or {},
        "connections": client.get("/vpn/connection/") or [],
        "client_configs": client.get("/vpn/client/config/") or [],
    }


def main():
    module = AnsibleModule(argument_spec=dict(COMMON_ARGSPEC), supports_check_mode=True)
    client = FreeboxClient(module)
    try:
        facts = _collect_facts(client)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(
        changed=False,
        ansible_facts={"freebox_vpn": facts},
    )


if __name__ == "__main__":
    main()
