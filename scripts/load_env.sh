#!/usr/bin/env bash
set -euo pipefail
cd /home/luuuu/miniconda3/envs/OPC-development
set -a
source .env
set +a
printf 'Environment loaded from %s/.env\n' "$PWD"
