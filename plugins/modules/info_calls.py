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
module: info_calls
short_description: Gather Freebox call log facts
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Collect the Freebox call log and return it as
    C(ansible_facts.freebox_calls).
  - Always reports C(changed=false).
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Gather call log facts
  mipsou.freebox.info_calls:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
  register: calls
"""

RETURN = r"""
ansible_facts:
  description: Call log facts.
  type: dict
  returned: always
  contains:
    freebox_calls:
      description: List of call log entry dicts.
      type: list
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def _collect_facts(client):
    """Return the call log list."""
    return client.get("/call/log/") or []


def main():
    module = AnsibleModule(argument_spec=dict(COMMON_ARGSPEC), supports_check_mode=True)
    client = FreeboxClient(module)
    try:
        facts = _collect_facts(client)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(changed=False, ansible_facts={"freebox_calls": facts})


if __name__ == "__main__":
    main()
