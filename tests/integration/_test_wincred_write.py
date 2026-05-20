#!/usr/bin/env python3
"""Test: write a credential via inline cmdkey.exe PS script (no env vars)."""
import os
import subprocess
import tempfile

TMPL = (
    '& cmdkey.exe /add:%(target)s /user:%(user)s /pass:%(pass)s | Out-Null\r\n'
    'if ($LASTEXITCODE -eq 0) { Write-Output "STORED_OK" }'
    ' else { Write-Output "STORED_ERR:$LASTEXITCODE" }\r\n'
)

script = TMPL % {
    "target": "community-freebox-test-write",
    "user": "testuser",
    "pass": "testpassword999",
}

old_umask = os.umask(0o177)
try:
    with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w", delete=False, encoding="utf-8") as tf:
        tf.write(script)
        ps1 = tf.name
finally:
    os.umask(old_umask)

ps1_win = subprocess.check_output(["wslpath", "-w", ps1], text=True).strip()
print("ps1_win:", ps1_win)

result = subprocess.run(
    ["powershell.exe", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1_win],
    capture_output=True,
)
os.unlink(ps1)

stdout = result.stdout.decode("utf-8", errors="replace")
stderr = result.stderr.decode("utf-8", errors="replace")
print("rc:", result.returncode)
print("stdout:", stdout.strip())
print("stderr:", stderr.strip()[:300] if stderr else "")
