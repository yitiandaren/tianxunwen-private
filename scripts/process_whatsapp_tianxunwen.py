#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天訊文 WhatsApp 整理腳本（可重複使用）

功能：
1. 解析 WhatsApp 匯出文字檔
2. 只保留「一天大人」的文字訊息（完整保留，不做內容篩選）
3. 依原文完全相同進行去重（保留時間最早的一則）
4. 依日期產出／合併 Markdown 檔案（TX-YYYYMMDDHHMMSS 格式）
5. 產出去重報告

使用方式：
    python process_whatsapp_tianxunwen.py <原始檔案路徑> [--output-dir master/whatsapp]
"""

import re
import argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path

SPEAKER_KEYWORDS = ["一天大人", "太素天尊"]
SKIP_PATTERNS = [
    r"圖像已省略",
    r"影片已省略",
    r"貼圖已忽略",
    r"語音通話",
    r"文件已忽略",
    r"安全碼已變更",
]


def parse_whatsapp_line(line: str):
    """解析單行 WhatsApp 訊息（處理 LTR/RTL 隱形字元）"""
    clean = line.strip().lstrip("\u200e\u200f\ufeff")
    pattern = r"\[(\d{4})/(\d{1,2})/(\d{1,2})\s+(上午|下午|中午|晚上|清晨|凌晨)?(\d{1,2}):(\d{2}):(\d{2})\]\s*([^:]+):\s*(.*)"
    m = re.match(pattern, clean)
    if not m:
        return None

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    period = m.group(4) or ""
    hour, minute, second = int(m.group(5)), int(m.group(6)), int(m.group(7))
    speaker = m.group(8).strip()
    content = m.group(9).strip()

    if period in ["下午", "晚上"] and hour < 12:
        hour += 12
    elif period in ["上午", "清晨", "凌晨"] and hour == 12:
        hour = 0
    elif period == "中午" and hour < 12:
        hour = 12 if hour == 0 else hour

    try:
        dt = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

    return {
        "datetime": dt,
        "speaker": speaker,
        "content": content,
    }


def is_dayiren(speaker: str) -> bool:
    return any(kw in speaker for kw in SPEAKER_KEYWORDS)


def is_skip_content(content: str) -> bool:
    if not content or len(content.strip()) == 0:
        return True
    for pat in SKIP_PATTERNS:
        if re.search(pat, content):
            cleaned = re.sub(pat, "", content).strip()
            cleaned = cleaned.replace("\u200e", "").replace("\u200f", "").strip()
            if len(cleaned) < 2:
                return True
    return False


def load_existing_texts(output_dir: Path) -> set:
    existing = set()
    if not output_dir.exists():
        return existing
    for md_file in output_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        blocks = re.split(r"\n---\n", text)
        for block in blocks:
            m = re.search(r"原文：\n(.*?)(?=\n出處：|\Z)", block, re.DOTALL)
            if m:
                original = m.group(1).strip()
                if original:
                    existing.add(original)
    return existing


def parse_existing_file(md_path: Path):
    """讀取既有日檔，回傳 (header_prefix, list of message blocks sorted by TX time)"""
    if not md_path.exists():
        return None, []
    text = md_path.read_text(encoding="utf-8")
    parts = re.split(r"\n---\n\n?", text)
    header = parts[0].strip() if parts else ""
    blocks = []
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        m = re.search(r"## (TX-(\d{14}))", part)
        if m:
            blocks.append((m.group(2), part))
    return header, blocks


def format_message(msg: dict, source_file: str) -> str:
    dt = msg["datetime"]
    tx_id = f"TX-{dt.strftime('%Y%m%d%H%M%S')}"
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    return f"""## {tx_id}

時間：[{time_str}]  
說話者：一天大人  

原文：
{msg['content']}

出處：WhatsApp 一天大人 ↔ 一天行  
原始檔案：{source_file}"""


def process_file(input_path: str, output_dir: str, source_name: str = None):
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if source_name is None:
        source_name = input_path.name

    print(f"讀取原始檔案：{input_path}")
    raw_text = input_path.read_text(encoding="utf-8", errors="replace")

    messages = []
    current = None
    for line in raw_text.splitlines():
        parsed = parse_whatsapp_line(line)
        if parsed:
            if current:
                messages.append(current)
            current = parsed
        else:
            if current and line.strip():
                clean = line.strip().lstrip("\u200e\u200f")
                if not re.match(r"\[\d{4}/", clean):
                    current["content"] += "\n" + line.strip()
    if current:
        messages.append(current)

    print(f"共解析到 {len(messages)} 則訊息")

    dayiren_msgs = []
    for msg in messages:
        if is_dayiren(msg["speaker"]) and not is_skip_content(msg["content"]):
            dayiren_msgs.append(msg)

    print(f"一天大人有效文字訊息：{len(dayiren_msgs)} 則")

    existing_texts = load_existing_texts(output_dir)
    print(f"已存在原文數：{len(existing_texts)}")

    by_date = defaultdict(list)
    new_count = 0
    dup_count = 0
    dup_samples = []

    dayiren_msgs.sort(key=lambda x: x["datetime"])

    seen_in_batch = set()
    for msg in dayiren_msgs:
        content = msg["content"].strip()
        if content in existing_texts or content in seen_in_batch:
            dup_count += 1
            if len(dup_samples) < 10:
                dup_samples.append(content[:80] + ("..." if len(content) > 80 else ""))
            continue
        seen_in_batch.add(content)
        existing_texts.add(content)
        date_key = msg["datetime"].strftime("%Y-%m-%d")
        by_date[date_key].append(msg)
        new_count += 1

    for date_key in sorted(by_date.keys()):
        new_msgs = by_date[date_key]
        out_file = output_dir / f"{date_key}.md"

        header, existing_blocks = parse_existing_file(out_file)
        if header is None:
            header = f"""# {date_key} 一天大人文字訊息

來源：WhatsApp 一天大人 ↔ 一天行  
原始檔案：{source_name}  
整理原則：完整保留原文、一字不改、時間精確到秒（僅去重，不篩選內容）"""

        # 合併：既有 + 新增，依 TX 時間排序
        all_blocks = list(existing_blocks)
        for m in new_msgs:
            block = format_message(m, source_name)
            tx_key = m["datetime"].strftime("%Y%m%d%H%M%S")
            all_blocks.append((tx_key, block))

        # 去重同一 TX-ID（理論上不應發生）
        seen_tx = set()
        unique_blocks = []
        for tx_key, block in sorted(all_blocks, key=lambda x: x[0]):
            if tx_key in seen_tx:
                continue
            seen_tx.add(tx_key)
            unique_blocks.append(block)

        body = "\n\n---\n\n".join(unique_blocks)
        out_file.write_text(header + "\n\n---\n\n" + body + "\n", encoding="utf-8")
        print(f"  寫入 {out_file.name}（既有 {len(existing_blocks)} + 新增 {len(new_msgs)} → 合計 {len(unique_blocks)} 則）")

    print("\n========== 去重報告 ==========")
    print(f"一天大人有效訊息總數：{len(dayiren_msgs)}")
    print(f"判定為重複：{dup_count}")
    print(f"實際新增：{new_count}")
    if dup_samples:
        print("\n重複訊息範例（前 10 則）：")
        for s in dup_samples:
            print(f"  - {s}")
    print("==============================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="天訊文 WhatsApp 整理腳本")
    parser.add_argument("input_file", help="原始 WhatsApp 文字檔路徑")
    parser.add_argument("--output-dir", default="master/whatsapp", help="輸出目錄")
    parser.add_argument("--source-name", default=None, help="原始檔案顯示名稱")
    args = parser.parse_args()
    process_file(args.input_file, args.output_dir, args.source_name)
