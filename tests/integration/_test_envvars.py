#!/usr/bin/env python3
"""Test whether env vars from WSL Python subprocess reach powershell.exe."""
import os
import subprocess
import tempfile

PS = r"""
Write-Output "TARGET=$env:FBCRED_TARGET"
Write-Output "USER=$env:FBCRED_USER"
Write-Output "PASS_ISSET=$([bool]$env:FBCRED_PASS)"
"""

env = os.environ.copy()
env["FBCRED_TARGET"] = "test-target-abc"
env["FBCRED_USER"] = "test-user"
env["FBCRED_PASS"] = "test-pass-xyz"

with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w", delete=False, encoding="utf-8") as tf:
    tf.write(PS)
    ps1 = tf.name

ps1_win = subprocess.check_output(["wslpath", "-w", ps1], text=True).strip()

result = subprocess.run(
    ["powershell.exe", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1_win],
    env=env, capture_output=True
)
os.unlink(ps1)
print("rc:", result.returncode)
print(result.stdout.decode("utf-8", errors="replace").strip())
print("stderr:", result.stderr.decode("utf-8", errors="replace").strip()[:200] if result.stderr else "")
