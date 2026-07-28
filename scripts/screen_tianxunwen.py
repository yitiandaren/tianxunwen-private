#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天訊文自動篩選腳本

依 WhatsApp 匯出檔或 master 日檔，快速標出：
  天訊文 / 短開示 / 金句 / 誓願文 / 非開示

規律（由 20260724_0601_chat 等樣本歸納）：
1. 強訊號：含「示曰」且成段論述 → 天訊文
2. 標題體：《xxx》+ 長文（如素行心經）→ 天訊文
3. 金句：短、完整意旨、非任務口語 → 圖卡
4. 偈頌／十二願／誓願 → 誓願文
5. 排除：飲食行程、叫誰做、數字回覆、短視頻SOP、純媒體占位

使用：
  python scripts/screen_tianxunwen.py raw/whatsapp/xxx.txt
  python scripts/screen_tianxunwen.py master/whatsapp --only 天訊文,金句 --csv out.csv
  python scripts/screen_tianxunwen.py master/whatsapp/2026-07-28.md --md-report report.md
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

SPEAKER_KEYWORDS = ["一天大人", "太素天尊"]

TASK_HEAD = re.compile(
    r"^(中午|早上|晚上|明天|後天|五點|四點|三點|叫|拿|傳|約|買|吃|泡|洗|"
    r"通知|告訴|給|讓|做一|先不|先做|都|好了|可以|現在|"
    r"\d+|http)",
    re.I,
)

SKIP_ONLY = re.compile(r"^(圖像已省略|影片已省略|貼圖已忽略|語音通話|文件已忽略)\s*$")

THEME_KW = re.compile(
    r"素行|本元|太素|太元|靜定|簡單|觀心|順隨|示曰|覺醒|生命能量|"
    r"愛自己|愛地球|愛眾生|信行醒|地靈國|天印|三元"
)

PRAYER_KW = re.compile(r"十二願|誓願文|祈願文|共願|如是素行\s*$|迴向偈|開經偈")


@dataclass
class ScreenResult:
    tx_id: str
    datetime: str
    category: str
    output: str
    score: int
    reason: str
    length: int
    preview: str


def parse_whatsapp(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    messages = []
    current = None
    line_re = re.compile(
        r"\[(\d{4})/(\d{1,2})/(\d{1,2})\s+(上午|下午|中午|晚上|清晨|凌晨)?"
        r"(\d{1,2}):(\d{2}):(\d{2})\]\s*([^:]+):\s*(.*)"
    )
    for line in text.splitlines():
        clean = line.strip().lstrip("\u200e\u200f\ufeff")
        m = line_re.match(clean)
        if m:
            if current:
                messages.append(current)
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            period = m.group(4) or ""
            h, mi, s = int(m.group(5)), int(m.group(6)), int(m.group(7))
            if period in ("下午", "晚上") and h < 12:
                h += 12
            elif period in ("上午", "清晨", "凌晨") and h == 12:
                h = 0
            elif period == "中午" and h < 12:
                h = 12 if h == 0 else h
            try:
                dt = datetime(y, mo, d, h, mi, s)
            except ValueError:
                current = None
                continue
            current = {
                "datetime": dt,
                "speaker": m.group(8).strip(),
                "content": m.group(9).strip(),
            }
        elif current and line.strip():
            if not re.match(r"\[\d{4}/", line.strip().lstrip("\u200e\u200f")):
                current["content"] += "\n" + line.strip()
    if current:
        messages.append(current)
    return [
        m
        for m in messages
        if any(k in m["speaker"] for k in SPEAKER_KEYWORDS)
        and not SKIP_ONLY.match(m["content"].strip())
    ]


def parse_master_md(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    messages = []
    blocks = re.split(r"\n---\n", text)
    for block in blocks:
        tm = re.search(r"## (TX-(\d{14}))", block)
        cm = re.search(r"原文：\n(.*?)(?=\n出處：|\Z)", block, re.DOTALL)
        if not tm or not cm:
            continue
        tx = tm.group(1)
        ts = tm.group(2)
        try:
            dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
        except ValueError:
            continue
        content = cm.group(1).strip()
        if SKIP_ONLY.match(content):
            continue
        messages.append(
            {"datetime": dt, "speaker": "一天大人", "content": content, "tx_id": tx}
        )
    return messages


def classify_content(content: str) -> ScreenResult:
    c = content.strip()
    c_clean = re.sub(r"(圖像已省略|影片已省略|貼圖已忽略)", "", c).strip()
    n = len(c_clean)
    preview = c_clean.replace("\n", " / ")[:60]

    if n < 2:
        return _r("", "非開示", "—", 0, "僅媒體占位", n, preview)

    has_示曰 = "示曰" in c_clean
    has_title = bool(re.search(r"《[^》]{2,}》", c_clean))
    has_theme = bool(THEME_KW.search(c_clean))
    is_prayer = bool(PRAYER_KW.search(c_clean)) and n > 80 and "心經" not in c_clean
    is_task_head = bool(TASK_HEAD.match(c_clean))
    para_score = c_clean.count("。") + c_clean.count("；")
    multi_line = c_clean.count("\n") >= 2

    score = 0
    reasons = []

    if has_示曰:
        score += 50
        reasons.append("示曰")
    if has_title and n > 100:
        score += 25
        reasons.append("標題長文")
    if has_theme:
        score += 15
        reasons.append("主題關鍵字")
    if n >= 400:
        score += 20
        reasons.append("長文≥400")
    elif n >= 200:
        score += 10
        reasons.append("中長≥200")
    if para_score >= 3:
        score += 10
        reasons.append("多句結構")
    if multi_line and n > 80:
        score += 5
        reasons.append("多行")

    if is_task_head and n < 80 and not has_示曰:
        score -= 40
        reasons.append("任務口語開頭")
    if n < 15:
        score -= 30
        reasons.append("過短")

    reason = "+".join(reasons) if reasons else "無強訊號"

    if is_prayer and (n >= 200 or "十二願" in c_clean or "誓願" in c_clean):
        cat, out = "誓願文", "編印"
    elif has_示曰 and n >= 80:
        cat, out = "天訊文", "文案"
    elif has_title and n >= 300 and has_theme:
        cat, out = "天訊文", "文案"
    elif n >= 400 and has_theme and para_score >= 4:
        cat, out = "天訊文", "文案"
    elif 80 <= n < 400 and has_theme and not is_task_head and para_score >= 2:
        cat, out = "短開示", "圖卡+文案"
    elif 12 <= n <= 120 and has_theme and not is_task_head and para_score >= 1:
        cat, out = "金句", "圖卡"
    elif 12 <= n <= 80 and not is_task_head and para_score >= 1 and has_theme:
        cat, out = "金句", "圖卡"
    elif score >= 40 and n >= 150:
        cat, out = "短開示", "圖卡+文案"
    else:
        cat, out = "非開示", "—"

    if cat == "非開示" and 15 <= n <= 100 and not is_task_head:
        if re.search(r"[，；].*[。！]?$", c_clean) and para_score >= 1:
            if not re.search(r"(嗎|呢|吧)\s*$", c_clean):
                if has_theme or ("，" in c_clean and "。" in c_clean):
                    cat, out = "金句", "圖卡"
                    reason += "+短哲理"

    if re.match(r"^(開經偈|迴向偈)", c_clean) or "開經偈" in c_clean[:20] or "迴向偈" in c_clean[:20]:
        cat, out = "誓願文", "編印"
        reason += "+偈頌"

    sop = bool(
        re.search(
            r"(核心公式|總體規劃|公頃|園區總面積|五大區域|短視頻核心|"
            r"70%畫面|製作素行～|應該傳遞)",
            c_clean,
        )
    )
    if sop and "示曰" not in c_clean:
        if cat == "天訊文":
            if n > 1000 and has_theme:
                cat, out = "短開示", "文案"
                reason += "+藍圖降級"
            else:
                cat, out = "非開示", "—"
                reason += "+SOP排除"

    return _r("", cat, out, score, reason, n, preview)


def _r(tx, cat, out, score, reason, n, preview) -> ScreenResult:
    return ScreenResult(
        tx_id=tx,
        datetime="",
        category=cat,
        output=out,
        score=score,
        reason=reason,
        length=n,
        preview=preview,
    )


def screen_messages(messages: list[dict]) -> list[ScreenResult]:
    results = []
    for m in messages:
        r = classify_content(m["content"])
        dt = m["datetime"]
        r.datetime = dt.strftime("%Y-%m-%d %H:%M:%S")
        r.tx_id = m.get("tx_id") or f"TX-{dt.strftime('%Y%m%d%H%M%S')}"
        results.append(r)
    return results


def main():
    ap = argparse.ArgumentParser(description="天訊文自動篩選")
    ap.add_argument("input", help="WhatsApp txt 或 master 日檔 md / 目錄")
    ap.add_argument("--csv", default="", help="輸出 CSV 路徑")
    ap.add_argument("--only", default="", help="只輸出類別，逗號分隔，如 天訊文,金句")
    ap.add_argument("--md-report", default="", help="輸出 Markdown 報告路徑")
    args = ap.parse_args()

    path = Path(args.input)
    messages = []
    if path.is_dir():
        for f in sorted(path.glob("*.md")):
            messages.extend(parse_master_md(f))
    elif path.suffix.lower() == ".md":
        messages = parse_master_md(path)
    else:
        messages = parse_whatsapp(path)

    results = screen_messages(messages)
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else set()

    cnt = Counter(r.category for r in results)
    print("========== 篩選統計 ==========")
    print(f"總則數：{len(results)}")
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("==============================\n")

    shown = [r for r in results if not only or r.category in only]
    for r in shown:
        if r.category == "非開示" and not only:
            continue
        print(f"{r.tx_id} [{r.category}/{r.output}] score={r.score} ({r.reason})")
        print(f"  {r.preview}...")
        print()

    if args.csv and results:
        outp = Path(args.csv)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
            w.writeheader()
            for r in results:
                w.writerow(asdict(r))
        print(f"CSV 已寫入：{outp}")

    if args.md_report:
        lines = [
            "# 天訊文自動篩選報告",
            "",
            f"來源：`{path}`",
            "",
            "## 統計",
            "",
            "| 類別 | 則數 |",
            "|------|------|",
        ]
        for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} |")
        lines += ["", "## 明細（非開示略）", ""]
        lines.append("| TX-ID | 類別 | 產出 | 分數 | 摘要 |")
        lines.append("|-------|------|------|------|------|")
        for r in results:
            if r.category == "非開示":
                continue
            prev = r.preview.replace("|", "｜")[:40]
            lines.append(
                f"| {r.tx_id} | {r.category} | {r.output} | {r.score} | {prev} |"
            )
        Path(args.md_report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"MD 報告已寫入：{args.md_report}")


if __name__ == "__main__":
    main()
