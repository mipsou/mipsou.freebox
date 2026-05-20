#!/usr/bin/env bash
set -e
CFG=/home/user/.ansible/collections/ansible_collections/mipsou/freebox/tests/integration/integration_config.yml
URL=$(grep '^freebox_url' "$CFG" | awk '{print $2}')
APP_ID=$(grep '^freebox_app_id' "$CFG" | awk '{print $2}')
APP_TOKEN=$(grep '^freebox_app_token' "$CFG" | awk '{print $2}')

echo "url=$URL app_id=$APP_ID token_len=${#APP_TOKEN}"

LANG=C.UTF-8 ansible localhost -m mipsou.freebox.system \
  -a "url=$URL app_id=$APP_ID app_token=$APP_TOKEN" \
  -v 2>&1
