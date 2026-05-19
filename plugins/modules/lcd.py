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
module: lcd
short_description: Manage the Freebox LCD display configuration
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the Freebox LCD panel configuration at C(/lcd/config/).
  - Only parameters explicitly set are sent to the API.
options:
  brightness:
    description:
      - LCD brightness as a percentage (0–100).
    type: int
  orientation:
    description:
      - Screen rotation in degrees. Accepted values are 0, 90, 180, 270.
    type: int
    choices: [0, 90, 180, 270]
  enabled:
    description:
      - Whether the LCD display is powered on.
    type: bool
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Set LCD brightness to 50%
  mipsou.freebox.lcd:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    brightness: 50

- name: Rotate and dim display
  mipsou.freebox.lcd:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    brightness: 20
    orientation: 90
    enabled: true
"""

RETURN = r"""
config:
  description: The LCD configuration after the call.
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

_SETTABLE_KEYS = ("brightness", "orientation", "enabled")

_VALID_ORIENTATIONS = (0, 90, 180, 270)


def _compute_diff(before, after, keys):
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        brightness=dict(type="int"),
        orientation=dict(type="int", choices=list(_VALID_ORIENTATIONS)),
        enabled=dict(type="bool"),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    brightness = module.params.get("brightness")
    if brightness is not None and not (0 <= brightness <= 100):
        module.fail_json(msg="brightness must be between 0 and 100, got %d" % brightness)

    desired = {k: module.params[k] for k in _SETTABLE_KEYS if module.params.get(k) is not None}

    client = FreeboxClient(module)
    try:
        if desired:
            changed, before, after = client.diff_and_put(
                "/lcd/config/",
                desired,
                full_body=False,
                check_mode=module.check_mode,
            )
        else:
            after = client.get("/lcd/config/") or {}
            before = after
            changed = False
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    diff = _compute_diff(before, after, desired.keys())
    module.exit_json(changed=changed, config=after, diff=diff)


if __name__ == "__main__":
    main()
