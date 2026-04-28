#!/usr/bin/env bash
# Из корня репозитория: bash scripts/railway_swap_superadmin.sh
# Нужны: railway link, Git Bash (или WSL). Команда выполняется на контейнере Railway.
set -euo pipefail
cd "$(dirname "$0")/.."
railway ssh -- python backend/manage.py swap_saas_superadmin superadmin too-bkc
