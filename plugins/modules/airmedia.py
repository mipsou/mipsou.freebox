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
module: airmedia
short_description: Manage the Freebox AirMedia receiver configuration
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the Freebox AirMedia receiver configuration at
    C(/airmedia/config/).
  - Only parameters explicitly set are sent to the API.
options:
  enabled:
    description:
      - Whether AirMedia reception is enabled.
    type: bool
  password:
    description:
      - PIN code required to connect to the AirMedia receiver. Set to empty
        string to disable PIN authentication.
    type: str
    no_log: true
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable AirMedia with PIN
  mipsou.freebox.airmedia:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: true
    password: "{{ airmedia_pin }}"

- name: Disable AirMedia
  mipsou.freebox.airmedia:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: false
"""

RETURN = r"""
config:
  description: The AirMedia configuration after the call.
  type: dict
  returned: always
diff:
  description: Mapping of changed keys to their (before, after) values.
  type: dict
  returned: always
changed:
  description: Whether the Freebox state was modified.
  type: bool
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)

_SETTABLE_KEYS = ("enabled", "password")


def _compute_diff(before, after, keys):
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        enabled=dict(type="bool"),
        password=dict(type="str", no_log=True),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    desired = {}
    if module.params.get("enabled") is not None:
        desired["enabled"] = module.params["enabled"]
    if module.params.get("password") is not None:
        desired["password"] = module.params["password"]

    client = FreeboxClient(module)
    try:
        if desired:
            changed, before, after = client.diff_and_put(
                "/airmedia/config/",
                desired,
                full_body=False,
                check_mode=module.check_mode,
            )
        else:
            after = client.get("/airmedia/config/") or {}
            before = after
            changed = False
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    diff = _compute_diff(before, after, desired.keys())
    module.exit_json(changed=changed, config=after, diff=diff)


if __name__ == "__main__":
    main()
