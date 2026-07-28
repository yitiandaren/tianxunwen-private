#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一步：同時篩選
  A. 天訊文（僅一天大人原文）
  B. 任務指派完整脈絡（一天大人指令 + 一天行互動）

使用：
  python scripts/extract_tianxunwen_and_tasks.py raw/whatsapp/某檔.txt
  python scripts/extract_tianxunwen_and_tasks.py raw/whatsapp/某檔.txt --context 3
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

大人_KW = ["一天大人", "太素天尊"]
行_KW = ["一天行", "ㄧ天行"]

SKIP = re.compile(r"^(圖像已省略|影片已省略|貼圖已忽略|語音通話|文件已忽略)\s*$")

CORE_KW = re.compile(
    r"素行|本元|太素|太元|靜定|簡單|觀心|順隨|示曰|言曰|"
    r"覺醒|生命能量|愛自己|愛地球|愛眾生|信行醒|地靈國|天印"
)
CLASSIC_TITLE = re.compile(r"《[^》]*(心經|素語|白皮書|經)[^》]*》|素語三百|素行心經")
PRAYER = re.compile(r"^(開經偈|迴向偈)|開經偈|迴向偈")

TASK_ACTION = re.compile(
    r"(叫|請|讓|通知|告訴|傳給|拿去|去做|做成|設計|拍|剪|上傳|"
    r"製作|寫|整理|發|推|貼|回報|確認|聯絡|約|安排|處理)"
)
TASK_HEAD = re.compile(r"^(叫|請|讓|通知|告訴|傳|拿|做|先不|先做|中午|早上|晚上)")
DECISION = re.compile(r"(先不做|先做|可以$|就這樣|不要$|用這個)")
ORG_SOP = re.compile(r"(核心公式|總體規劃|公頃|五大區域|短視頻核心|70%畫面)")


@dataclass
class Msg:
    idx: int
    dt: datetime
    speaker: str
    role: str
    text: str
    tx_id: str


@dataclass
class TianHit:
    tx_id: str
    datetime: str
    細標: str
    length: int
    preview: str
    reason: str


@dataclass
class TaskHit:
    task_tx_id: str
    datetime: str
    任務類型: str
    大人原文: str
    脈絡全文: str
    含一天行: str
    前後則數: int


def role_of(speaker: str) -> str:
    if any(k in speaker for k in 大人_KW):
        return "大人"
    if any(k in speaker for k in 行_KW):
        return "行"
    return "其他"


def parse_all(path: Path) -> list:
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

    out = []
    for i, m in enumerate(messages):
        c = m["content"].strip()
        if SKIP.match(c):
            continue
        dt = m["datetime"]
        out.append(
            Msg(
                idx=i,
                dt=dt,
                speaker=m["speaker"],
                role=role_of(m["speaker"]),
                text=c,
                tx_id=f"TX-{dt.strftime('%Y%m%d%H%M%S')}",
            )
        )
    return out


def is_tianxunwen(text: str):
    c = re.sub(r"(圖像已省略|影片已省略|貼圖已忽略)", "", text).strip()
    n = len(c)
    if n < 40:
        return False, "—", "過短"
    has_示 = "示曰" in c or "言曰" in c
    has_title = bool(re.search(r"《[^》]{2,}》", c))
    classic = bool(CLASSIC_TITLE.search(c))
    kw = len(CORE_KW.findall(c))
    prayer = bool(PRAYER.search(c[:40]))
    sop = bool(ORG_SOP.search(c)) and "示曰" not in c
    if sop and n < 800:
        return False, "—", "SOP"
    if prayer and n < 400:
        return True, "偈", "偈"
    if has_示 and n >= 60:
        if classic or n >= 800:
            return True, "經典", "示曰+長"
        if n >= 200:
            return True, "天訊文", "示曰"
        return True, "短示", "示曰短"
    if (has_title or classic) and n >= 250 and (kw >= 2 or classic):
        return True, ("經典" if classic or n >= 600 else "天訊文"), "成篇"
    if n >= 350 and kw >= 3 and c.count("。") >= 4 and not sop:
        return True, "天訊文", "長論"
    return False, "—", "—"


def is_task_msg(text: str):
    c = text.strip()
    n = len(c)
    if "示曰" in c and n >= 80:
        return False, ""
    if n > 500:
        return False, ""
    if DECISION.search(c) and n < 40:
        return True, "決策拍板"
    if TASK_HEAD.match(c) or (TASK_ACTION.search(c) and n < 200):
        if re.search(r"(吃|泡|睡|保養|勞力士)", c) and n < 40:
            return True, "生活作息"
        return True, "任務指派"
    if re.search(r"(進度|好了沒|有沒有做)", c) and n < 80:
        return True, "詢問確認"
    return False, ""


def screen_tianxunwen(msgs):
    hits = []
    for m in msgs:
        if m.role != "大人":
            continue
        ok, fine, reason = is_tianxunwen(m.text)
        if not ok:
            continue
        hits.append(
            TianHit(
                tx_id=m.tx_id,
                datetime=m.dt.strftime("%Y-%m-%d %H:%M:%S"),
                細標=fine,
                length=len(m.text),
                preview=m.text.replace("\n", " / ")[:80],
                reason=reason,
            )
        )
    return hits


def screen_tasks(msgs, context=3):
    hits = []
    n = len(msgs)
    for i, m in enumerate(msgs):
        if m.role != "大人":
            continue
        ok, ttype = is_task_msg(m.text)
        if not ok:
            continue
        lo = max(0, i - context)
        hi = min(n, i + context + 1)
        window = msgs[lo:hi]
        lines = []
        has_xing = False
        for w in window:
            tag = {"大人": "一天大人", "行": "一天行"}.get(w.role, w.speaker)
            if w.role == "行":
                has_xing = True
            ts = w.dt.strftime("%Y-%m-%d %H:%M:%S")
            body = w.text.replace("\n", " ")[:200]
            mark = " ★" if w.idx == m.idx else ""
            lines.append(f"[{ts}] {tag}{mark}: {body}")
        hits.append(
            TaskHit(
                task_tx_id=m.tx_id,
                datetime=m.dt.strftime("%Y-%m-%d %H:%M:%S"),
                任務類型=ttype,
                大人原文=m.text.replace("\n", " ")[:300],
                脈絡全文="\n".join(lines),
                含一天行="是" if has_xing else "否",
                前後則數=len(window),
            )
        )
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--context", type=int, default=3)
    ap.add_argument("--outdir", default="classify")
    args = ap.parse_args()

    path = Path(args.input)
    msgs = parse_all(path)
    tian = screen_tianxunwen(msgs)
    tasks = screen_tasks(msgs, context=args.context)

    roles = Counter(m.role for m in msgs)
    print("========== 對話解析 ==========")
    print(f"檔案：{path.name}")
    print(f"總則數：{len(msgs)}  {dict(roles)}")
    print(f"天訊文：{len(tian)}")
    print(
        f"任務錨點：{len(tasks)}（含一天行脈絡：{sum(1 for t in tasks if t.含一天行=='是')}）"
    )
    print("==============================\n")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    tcsv = outdir / f"tianxunwen_{stem}.csv"
    if tian:
        with tcsv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(tian[0]).keys()))
            w.writeheader()
            for h in tian:
                w.writerow(asdict(h))
        print(f"天訊文 CSV：{tcsv}")

    tmd = outdir / f"tianxunwen_{stem}.md"
    lines = [
        f"# 天訊文篩選 — {path.name}",
        "",
        f"則數：{len(tian)}",
        "",
        "| TX-ID | 細標 | 字數 | 摘要 |",
        "|-------|------|------|------|",
    ]
    for h in tian:
        lines.append(
            f"| {h.tx_id} | {h.細標} | {h.length} | {h.preview.replace('|','｜')[:50]} |"
        )
    tmd.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"天訊文 MD：{tmd}")

    kcsv = outdir / f"tasks_{stem}.csv"
    if tasks:
        with kcsv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(tasks[0]).keys()))
            w.writeheader()
            for h in tasks:
                w.writerow(asdict(h))
        print(f"任務 CSV：{kcsv}")

    kmd = outdir / f"tasks_{stem}.md"
    lines = [
        f"# 任務指派完整脈絡 — {path.name}",
        "",
        f"錨點則數：{len(tasks)}",
        f"前後各 {args.context} 則；★ 為一天大人任務句",
        "",
    ]
    for h in tasks:
        lines += [
            f"## {h.task_tx_id} · {h.任務類型} · 含一天行={h.含一天行}",
            "",
            "```",
            h.脈絡全文,
            "```",
            "",
        ]
    kmd.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"任務 MD：{kmd}")

    print("\n預覽任務（最多 5 則）：")
    for h in tasks[:5]:
        print(f"  {h.task_tx_id} [{h.任務類型}] 行={h.含一天行} | {h.大人原文[:50]}")


if __name__ == "__main__":
    main()
