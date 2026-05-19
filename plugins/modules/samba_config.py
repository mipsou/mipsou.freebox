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
module: samba_config
short_description: Manage the Freebox Samba (SMB) server configuration
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Read-modify-write the Freebox Samba configuration singleton at C(/samba/config/).
  - Only parameters explicitly set are sent to the API; unspecified parameters
    keep their current Freebox-side value.
options:
  workgroup:
    description:
      - NetBIOS workgroup name.
    type: str
  logon_enabled:
    description:
      - Whether domain logon (NTLM authentication) is enabled.
    type: bool
  guest_account:
    description:
      - Name of the local account used for guest access.
    type: str
  file_share_enabled:
    description:
      - Whether file sharing over SMB is enabled.
    type: bool
  print_share_enabled:
    description:
      - Whether printer sharing over SMB is enabled.
    type: bool
  smb2_enabled:
    description:
      - Whether to advertise SMB2 support (in addition to SMB1).
    type: bool
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Set workgroup and enable file sharing
  mipsou.freebox.samba_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    workgroup: WORKGROUP
    file_share_enabled: true
    smb2_enabled: true

- name: Disable printer sharing
  mipsou.freebox.samba_config:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    print_share_enabled: false
"""

RETURN = r"""
config:
  description: The full Samba configuration after the call.
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


_SETTABLE_KEYS = (
    "workgroup",
    "logon_enabled",
    "guest_account",
    "file_share_enabled",
    "print_share_enabled",
    "smb2_enabled",
)


def _compute_diff(before, after, keys):
    return {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        workgroup=dict(type="str"),
        logon_enabled=dict(type="bool"),
        guest_account=dict(type="str"),
        file_share_enabled=dict(type="bool"),
        print_share_enabled=dict(type="bool"),
        smb2_enabled=dict(type="bool"),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    desired = {k: module.params[k] for k in _SETTABLE_KEYS if module.params.get(k) is not None}

    client = FreeboxClient(module)
    try:
        if desired:
            changed, before, after = client.diff_and_put(
                "/samba/config/",
                desired,
                full_body=False,
                check_mode=module.check_mode,
            )
        else:
            after = client.get("/samba/config/") or {}
            before = after
            changed = False
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    diff = _compute_diff(before, after, desired.keys())
    module.exit_json(changed=changed, config=after, diff=diff)


if __name__ == "__main__":
    main()
