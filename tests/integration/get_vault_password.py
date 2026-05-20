#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ansible --vault-password-file script — cross-platform.

Reads the vault password from the OS secret store.

Store the vault password once (you, not an AI):

  Windows / WSL:
    cmdkey /add:community-freebox-vault /user:vault /pass:<vault-password>

  Linux (libsecret):
    secret-tool store --label="community-freebox-vault" \
      service community-freebox-vault account vault

  macOS:
    security add-generic-password \
      -s community-freebox-vault -a vault -w <vault-password>

Usage (non-interactive, safe in playbooks and CI):
    ansible-vault encrypt \
      --vault-password-file tests/integration/get_vault_password.py ...
    ansible-test integration \
      --vault-password-file tests/integration/get_vault_password.py ...
"""

from __future__ import print_function

import os
import subprocess
import sys
import tempfile

_SERVICE = "community-freebox-vault"
_ACCOUNT = "vault"

# ── platform detection ────────────────────────────────────────────────────


def _is_wsl():
    try:
        with open("/proc/version") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _platform():
    if sys.platform == "win32":
        return "windows"
    if _is_wsl():
        return "wsl"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


# ── per-platform readers ──────────────────────────────────────────────────

_PS_SCRIPT = r"""
$code = @'
using System; using System.Runtime.InteropServices; using System.Text;
public class WC {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct CRED {
        public int Flags,Type; public string TargetName,Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public int BlobSize; public IntPtr Blob;
        public int Persist,AttrCount; public IntPtr Attrs;
        public string Alias,UserName;
    }
    [DllImport("advapi32",EntryPoint="CredReadW",CharSet=CharSet.Unicode,SetLastError=true)]
    public static extern bool Read(string t,int typ,int f,out IntPtr c);
    [DllImport("advapi32",SetLastError=true)] public static extern void Free(IntPtr c);
    public static string[] Get(string t){
        IntPtr p; if(!Read(t,1,0,out p)) return null;
        var c=(CRED)Marshal.PtrToStructure(p,typeof(CRED));
        byte[] b=new byte[c.BlobSize]; Marshal.Copy(c.Blob,b,0,b.Length); Free(p);
        return new string[]{c.UserName, Encoding.Unicode.GetString(b)};
    }
}
'@
Add-Type -TypeDefinition $code
$r = [WC]::Get("%(service)s")
if ($r) { "|||" + $r[1] + "|||" }
""" % {"service": _SERVICE}


def _read_windows(ps_exe="powershell"):
    with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w",
                                     delete=False, encoding="utf-8") as tf:
        tf.write(_PS_SCRIPT)
        ps1 = tf.name
    try:
        result = subprocess.run(
            [ps_exe, "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1],
            capture_output=True, text=True,
        )
    finally:
        os.unlink(ps1)
    if result.returncode != 0 or "|||" not in result.stdout:
            return ""  # not found → default empty
        return result.stdout.strip().split("|||")[1]


def _read_linux():
    result = subprocess.run(
        ["secret-tool", "lookup", "service", _SERVICE, "account", _ACCOUNT],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.rstrip("\n")
    return ""  # not found → default empty


def _read_macos():
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", _SERVICE, "-a", _ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.rstrip("\n")
    return ""  # not found → default empty


# ── store-hint per platform ───────────────────────────────────────────────

_STORE_HINTS = {
    "windows": "  cmdkey /add:%s /user:%s /pass:<vault-password>" % (_SERVICE, _ACCOUNT),
    "wsl":     "  cmdkey /add:%s /user:%s /pass:<vault-password>" % (_SERVICE, _ACCOUNT),
    "linux":   "  secret-tool store --label=%s service %s account %s" % (_SERVICE, _SERVICE, _ACCOUNT),
    "macos":   "  security add-generic-password -s %s -a %s -w <vault-password>" % (_SERVICE, _ACCOUNT),
}


# ── main ──────────────────────────────────────────────────────────────────

def _get_password():
    plat = _platform()
    if plat == "windows":
        return _read_windows("powershell")
    if plat == "wsl":
        return _read_windows("powershell.exe")
    if plat == "macos":
        return _read_macos()
    return _read_linux()


password = _get_password()
plat = _platform()

if password is None:
    sys.stderr.write(
        "ERROR: '%s' not found in the %s secret store.\n"
        "Store it first:\n%s\n" % (_SERVICE, plat, _STORE_HINTS[plat])
    )
    sys.exit(1)

if password == "":
    sys.stderr.write(
        "\n"
        "  ╔══════════════════════════════════════════════════════════╗\n"
        "  ║  SECURITY WARNING — vault password is EMPTY             ║\n"
        "  ║  Set a real password NOW, then rekey the vault:         ║\n"
        "  ║    %s\n"
        "  ║    ansible-vault rekey                                  ║\n"
        "  ║      --vault-password-file get_vault_password.py        ║\n"
        "  ║      tests/integration/integration_config.yml.vault     ║\n"
        "  ╚══════════════════════════════════════════════════════════╝\n\n"
        % _STORE_HINTS[plat].strip()
    )
    if os.environ.get("FREEBOX_VAULT_ALLOW_EMPTY") != "1":
        sys.stderr.write(
            "  Blocked. Init only:\n"
            "    FREEBOX_VAULT_ALLOW_EMPTY=1 ansible-vault encrypt ...\n\n"
        )
        sys.exit(1)

print(password)
