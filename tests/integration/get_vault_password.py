#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ansible vault-password-file script.

Reads the vault password from Windows Credential Manager.

Store the vault password once (run yourself, never via an AI):
    cmdkey /add:community-freebox-vault /user:vault /pass:<your-vault-password>

Usage with ansible-vault / ansible-test:
    ansible-vault encrypt --vault-password-file tests/integration/get_vault_password.py ...
    ansible-test integration --vault-password-file tests/integration/get_vault_password.py ...
"""

from __future__ import print_function

import ctypes
import sys

_CRED_TYPE_GENERIC = 1


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


_TARGET = "community-freebox-vault"

_advapi32 = ctypes.WinDLL("advapi32")
_advapi32.CredReadW.restype = ctypes.c_bool
_advapi32.CredReadW.argtypes = [
    ctypes.c_wchar_p,
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)),
]
_advapi32.CredFree.argtypes = [ctypes.c_void_p]

_ptr = ctypes.POINTER(_CREDENTIAL)()
if not _advapi32.CredReadW(_TARGET, _CRED_TYPE_GENERIC, 0, ctypes.byref(_ptr)):
    sys.stderr.write(
        "ERROR: '%s' not found in Windows Credential Manager.\n"
        "Run: cmdkey /add:%s /user:vault /pass:<vault-password>\n"
        % (_TARGET, _TARGET)
    )
    sys.exit(1)

_blob = bytes(_ptr.contents.CredentialBlob[: _ptr.contents.CredentialBlobSize])
_advapi32.CredFree(_ptr)

print(_blob.decode("utf-16-le"))
