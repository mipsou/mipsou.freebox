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
module: info_shares
short_description: Gather Freebox file sharing facts (FTP, AFP, TFTP)
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Collect file sharing configuration from the Freebox (FTP, AFP, TFTP)
    and return it as C(ansible_facts.freebox_shares).
  - Always reports C(changed=false).
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Gather file sharing facts
  mipsou.freebox.info_shares:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
  register: shares
"""

RETURN = r"""
ansible_facts:
  description: File sharing facts.
  type: dict
  returned: always
  contains:
    freebox_shares:
      description: File sharing configuration.
      type: dict
      contains:
        ftp:
          description: FTP configuration dict.
          type: dict
        afp:
          description: AFP configuration dict.
          type: dict
        tftp:
          description: TFTP configuration dict.
          type: dict
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
)


def _collect_facts(client):
    """Return the freebox_shares facts dict."""
    return {
        "ftp": client.get("/ftp/config/") or {},
        "afp": client.get("/afp/config/") or {},
        "tftp": client.get("/tftp/config/") or {},
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
        ansible_facts={"freebox_shares": facts},
    )


if __name__ == "__main__":
    main()
