#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天訊文完整自動工作流（一鍵管線）

步驟：
  1. 解析 WhatsApp 原始對話（僅一天大人）
  2. 原文去重（一字不改）
  3. 寫入／合併 master/whatsapp/YYYY-MM-DD.md
  4. 自動分類：功能粗標 + 天訊文細類（天訊文/短開示/金句/誓願文/非開示）
  5. 產出篩選報告 CSV / Markdown

用法：
  python scripts/run_tianxunwen_pipeline.py raw/whatsapp/20260401_0531_chat.txt
  python scripts/run_tianxunwen_pipeline.py raw/whatsapp/xxx.txt --master-dir master/whatsapp --classify-dir classify
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def coarse_function(content: str, category: str) -> str:
    c = content.strip()
    if category in ("天訊文", "短開示", "金句"):
        return "開示"
    if category == "誓願文":
        return "開示｜修行指示"
    if re.match(r"^(中午|早上|晚上|泡|吃|叫|拿|傳|約|通知)", c):
        if re.search(r"(叫|通知|告訴|讓|傳給)", c):
            return "任務指派"
        return "生活作息"
    if re.search(r"(專案|團隊|出版|編印|演講|音樂會|推廣|品牌|設計|園區)", c):
        return "組織推廣"
    if len(c) < 40 and re.search(r"(嗎|呢|？|\?)", c):
        return "詢問確認"
    if len(c) < 30:
        return "詢問確認｜決策拍板"
    return "非開示待標"


def main():
    ap = argparse.ArgumentParser(description="天訊文完整自動工作流")
    ap.add_argument("input", help="WhatsApp 原始 txt")
    ap.add_argument("--master-dir", default="master/whatsapp")
    ap.add_argument("--classify-dir", default="classify")
    ap.add_argument("--source-name", default=None)
    ap.add_argument("--skip-master", action="store_true", help="只做篩選，不寫 master")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    candidates = [
        root / "screen_tianxunwen.py",
        root.parent / "scripts" / "screen_tianxunwen.py",
        Path("scripts/screen_tianxunwen.py"),
    ]
    screen_path = next((p for p in candidates if p.exists()), None)
    if not screen_path:
        print("找不到 screen_tianxunwen.py", file=sys.stderr)
        sys.exit(1)

    process_candidates = [
        root / "process_whatsapp_tianxunwen.py",
        root.parent / "scripts" / "process_whatsapp_tianxunwen.py",
        Path("scripts/process_whatsapp_tianxunwen.py"),
    ]
    process_path = next((p for p in process_candidates if p.exists()), None)

    screen = load_module("screen_tianxunwen", screen_path)
    input_path = Path(args.input)
    source_name = args.source_name or input_path.name
    master_dir = Path(args.master_dir)
    classify_dir = Path(args.classify_dir)
    classify_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("天訊文自動工作流")
    print("=" * 50)
    print(f"輸入：{input_path}")

    if not args.skip_master and process_path:
        print("\n[1/3] 去重並寫入 master …")
        proc = load_module("process_whatsapp", process_path)
        proc.process_file(str(input_path), str(master_dir), source_name)
    elif args.skip_master:
        print("\n[1/3] 跳過 master 寫入（--skip-master）")
    else:
        print("\n[1/3] 未找到 process 腳本，僅篩選（不寫 master）")

    print("\n[2/3] 解析並篩選天訊文細類 …")
    messages = screen.parse_whatsapp(input_path)
    results = screen.screen_messages(messages)
    cnt = Counter(r.category for r in results)
    print("篩選統計：", dict(cnt))

    print("\n[3/3] 產出分類報告 …")
    stamp = datetime.now().strftime("%Y%m%d")
    base = input_path.stem
    csv_path = classify_dir / f"pipeline_{base}_{stamp}.csv"
    md_path = classify_dir / f"pipeline_{base}_{stamp}.md"

    by_tx = {f"TX-{m['datetime'].strftime('%Y%m%d%H%M%S')}": m for m in messages}
    rows = []
    for r in results:
        m = by_tx.get(r.tx_id)
        content = m["content"] if m else r.preview
        rows.append(
            {
                "tx_id": r.tx_id,
                "datetime": r.datetime,
                "功能粗標": coarse_function(content, r.category),
                "開示細類": r.category,
                "產出建議": r.output,
                "score": r.score,
                "reason": r.reason,
                "length": r.length,
                "preview": r.preview,
            }
        )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            w.writerows(rows)

    out_map = {
        "天訊文": "文案／典藏",
        "金句": "圖卡",
        "短開示": "圖卡+文案",
        "誓願文": "編印",
        "非開示": "—",
    }
    lines = [
        f"# 天訊文工作流報告：`{source_name}`",
        "",
        f"產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 統計",
        "",
        "| 開示細類 | 則數 | 建議產出 |",
        "|----------|------|----------|",
    ]
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} | {out_map.get(k, '—')} |")

    lines += [
        "",
        "## 天訊文清單（可優先文案／公開）",
        "",
        "| TX-ID | 時間 | 字數 | 摘要 |",
        "|-------|------|------|------|",
    ]
    for r in results:
        if r.category != "天訊文":
            continue
        lines.append(
            f"| {r.tx_id} | {r.datetime} | {r.length} | {r.preview.replace('|', '｜')[:50]} |"
        )

    lines += [
        "",
        "## 金句清單（可優先圖卡）",
        "",
        "| TX-ID | 時間 | 摘要 |",
        "|-------|------|------|",
    ]
    for r in results:
        if r.category != "金句":
            continue
        lines.append(
            f"| {r.tx_id} | {r.datetime} | {r.preview.replace('|', '｜')[:60]} |"
        )

    lines += [
        "",
        "## 工作流說明",
        "",
        "1. **原始對話** → 只取一天大人文字，媒體占位略過",
        "2. **去重** → 原文完全相同保留最早一則，寫入 `master/whatsapp/`",
        "3. **分類** → 開示細類 + 功能粗標",
        "4. **產出** → 天訊文作文案；金句做圖卡；誓願文編印",
        "5. **人工** → 需前因後果之任務類仍須對 raw",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"CSV：{csv_path}")
    print(f"MD ：{md_path}")
    print("完成。")


if __name__ == "__main__":
    main()
