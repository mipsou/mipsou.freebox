#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ansible vault-password-file script — cross-platform.

Reads the vault password from the OS secret store:
  Windows  : Windows Credential Manager  (via python-keyring)
  Linux    : libsecret / GNOME Keyring   (via python-keyring + SecretService)
  macOS    : Keychain                    (via python-keyring)

Store the vault password once (run yourself, never via an AI):

  Windows:
    cmdkey /add:community-freebox-vault /user:vault /pass:<vault-password>

  Linux (libsecret):
    secret-tool store --label="community-freebox-vault" \
      service community-freebox-vault account vault

  macOS:
    security add-generic-password -s community-freebox-vault \
      -a vault -w <vault-password>

  Or via Python (any OS):
    python3 -c "import keyring; keyring.set_password(
        'community-freebox-vault', 'vault', '<vault-password>')"

Dependencies:
    pip install keyring
    # Linux also needs: pip install secretstorage  (or jeepney for DBus)

Usage:
    ansible-vault encrypt --vault-password-file tests/integration/get_vault_password.py ...
    ansible-test integration --vault-password-file tests/integration/get_vault_password.py ...
"""

from __future__ import print_function

import sys

_SERVICE = "community-freebox-vault"
_ACCOUNT = "vault"

try:
    import keyring
except ImportError:
    sys.stderr.write(
        "ERROR: 'keyring' not installed.\n"
        "  pip install keyring\n"
        "  # Linux: also pip install secretstorage\n"
    )
    sys.exit(1)

password = keyring.get_password(_SERVICE, _ACCOUNT)

if password is None:
    sys.stderr.write(
        "ERROR: no entry found for service=%r account=%r.\n"
        "Store it first (empty string allowed for init):\n"
        "  python3 -c \"import keyring; keyring.set_password(%r, %r, '')\"\n"
        % (_SERVICE, _ACCOUNT, _SERVICE, _ACCOUNT)
    )
    sys.exit(1)

# Empty password is allowed (vault init before rekey).
print(password)
