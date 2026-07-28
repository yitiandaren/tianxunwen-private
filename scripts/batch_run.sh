#!/bin/bash
# 天訊文批量處理（本機）
# 用法：
#   ./scripts/batch_run.sh
#   ./scripts/batch_run.sh raw/whatsapp
#   ./scripts/batch_run.sh raw/whatsapp --skip-master
#   ./scripts/batch_run.sh raw/whatsapp --only-process   # 只去重，不跑完整管線

set -euo pipefail
cd "$(dirname "$0")/.."

DIR="${1:-raw/whatsapp}"
MODE="${2:-}"

if [ ! -d "$DIR" ]; then
  echo "目錄不存在：$DIR"
  exit 1
fi

shopt -s nullglob
files=("$DIR"/*.txt)
if [ ${#files[@]} -eq 0 ]; then
  echo "沒有找到 .txt：$DIR"
  exit 0
fi

echo "共 ${#files[@]} 個檔案"
echo "模式：${MODE:-完整管線（去重+篩選報告）}"
echo

for f in "${files[@]}"; do
  echo "======== $(basename "$f") ========"
  case "$MODE" in
    --skip-master)
      python3 scripts/run_tianxunwen_pipeline.py "$f" --skip-master
      ;;
    --only-process)
      python3 scripts/process_whatsapp_tianxunwen.py "$f" \
        --output-dir master/whatsapp \
        --source-name "$(basename "$f")"
      ;;
    *)
      python3 scripts/run_tianxunwen_pipeline.py "$f"
      ;;
  esac
  echo
done

echo "全部完成。"
