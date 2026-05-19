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
module: upnp
short_description: Manage Freebox UPnP/IGD configuration and read port mappings
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the UPnP IGD configuration at C(/upnp/config/).
  - Optionally fetch the current IGD port mappings as
    C(ansible_facts.freebox_upnp_rules) (read-only — rules are managed by
    UPnP clients, not by this module).
options:
  enabled:
    description:
      - Whether UPnP IGD is enabled on the Freebox.
    type: bool
  gather_facts:
    description:
      - When C(true), return the current UPnP IGD rules as
        C(ansible_facts.freebox_upnp_rules).
    type: bool
    default: false
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable UPnP IGD
  mipsou.freebox.upnp:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: true

- name: Gather current UPnP port mappings
  mipsou.freebox.upnp:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    gather_facts: true
  register: upnp
# upnp.ansible_facts.freebox_upnp_rules is a list of rule dicts
"""

RETURN = r"""
config:
  description: The UPnP configuration after the call.
  type: dict
  returned: always
changed:
  description: Whether the Freebox state was modified.
  type: bool
  returned: always
ansible_facts:
  description: Populated when I(gather_facts=true).
  type: dict
  returned: when gather_facts=true
  contains:
    freebox_upnp_rules:
      description: List of active UPnP IGD port mapping rules.
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
        enabled=dict(type="bool"),
        gather_facts=dict(type="bool", default=False),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    desired = {}
    if module.params.get("enabled") is not None:
        desired["enabled"] = module.params["enabled"]

    client = FreeboxClient(module)
    try:
        if desired:
            changed, _before, config = client.diff_and_put(
                "/upnp/config/",
                desired,
                full_body=False,
                check_mode=module.check_mode,
            )
        else:
            config = client.get("/upnp/config/") or {}
            changed = False

        result = dict(changed=changed, config=config)

        if module.params.get("gather_facts"):
            rules = client.get("/upnp/igd/rules/") or []
            result["ansible_facts"] = {"freebox_upnp_rules": rules}

    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
