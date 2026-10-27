#!/bin/zsh
set -euo pipefail
SCE_VIDEO_DIR="${0:A:h}"
SCE_PROJECT_DIR="${SCE_VIDEO_DIR:h:h:h}"
SCE_DEMO_PYTHON='/Users/wushuyue/anaconda3/envs/socioverse/bin/python'
exec "$SCE_DEMO_PYTHON" "$SCE_PROJECT_DIR/studies/sce_inflation_expectations/reports/video_demo_v1/record_demo.py"
