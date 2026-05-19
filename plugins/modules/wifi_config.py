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
module: wifi_config
short_description: Manage the Freebox global Wi-Fi configuration
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the singleton Wi-Fi configuration at C(/wifi/config/).
  - Only parameters explicitly set are sent to the API; unspecified parameters
    keep their current Freebox-side value.
options:
  enabled:
    description:
      - Whether Wi-Fi is enabled globally on the Freebox.
    type: bool
  mac_filter_state:
    description:
      - MAC address filter mode.
    type: str
    choices: [disabled, whitelist, blacklist]
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Enable Wi-Fi
  mipsou.freebox.wifi_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    enabled: true

- name: Set MAC filter to whitelist mode
  mipsou.freebox.wifi_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac_filter_state: whitelist
"""

RETURN = r"""
config:
  description: The full Wi-Fi configuration after the call.
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


_SETTABLE_KEYS = ("enabled", "mac_filter_state")


def _compute_diff(before, after, keys):
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        enabled=dict(type="bool"),
        mac_filter_state=dict(type="str", choices=["disabled", "whitelist", "blacklist"]),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    desired = {k: module.params[k] for k in _SETTABLE_KEYS if module.params.get(k) is not None}

    client = FreeboxClient(module)
    try:
        if desired:
            changed, before, after = client.diff_and_put(
                "/wifi/config/",
                desired,
                full_body=False,
                check_mode=module.check_mode,
            )
        else:
            after = client.get("/wifi/config/") or {}
            before = after
            changed = False
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    diff = _compute_diff(before, after, desired.keys())
    module.exit_json(changed=changed, config=after, diff=diff)


if __name__ == "__main__":
    main()
