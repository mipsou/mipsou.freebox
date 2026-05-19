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
module: parental
short_description: Manage Freebox parental control and read filter profiles
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the parental control configuration at C(/parental/config/).
  - Optionally fetch the list of parental filter profiles as
    C(ansible_facts.freebox_parental_filters) (read-only).
options:
  enabled:
    description:
      - Whether parental control is globally active.
    type: bool
  gather_facts:
    description:
      - When C(true), return the parental filter profiles as
        C(ansible_facts.freebox_parental_filters).
    type: bool
    default: false
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable parental control
  mipsou.freebox.parental:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: true

- name: Gather parental filter profiles
  mipsou.freebox.parental:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    gather_facts: true
  register: parental
# parental.ansible_facts.freebox_parental_filters is a list of filter dicts
"""

RETURN = r"""
config:
  description: The parental control configuration after the call.
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
    freebox_parental_filters:
      description: List of parental filter profile dicts.
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
                "/parental/config/",
                desired,
                full_body=False,
                check_mode=module.check_mode,
            )
        else:
            config = client.get("/parental/config/") or {}
            changed = False

        result = dict(changed=changed, config=config)

        if module.params.get("gather_facts"):
            filters = client.get("/parental/filter/") or []
            result["ansible_facts"] = {"freebox_parental_filters": filters}

    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
