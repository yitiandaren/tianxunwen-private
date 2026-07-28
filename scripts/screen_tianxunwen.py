#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天訊文自動篩選腳本（定稿規律）

主標／細標（依附件樣本 + 人工定稿）：
  功能主標：天訊文｜修行指示｜任務指派｜詢問確認｜決策拍板｜組織推廣｜
            生活作息｜個人私事｜回應回報｜待標
  天訊文細標（僅主標=天訊文）：經典｜天訊文｜偈｜短示
  金句：不從短訊獨立分類，只從天訊文正文抽句（--extract-jinju）

使用：
  python scripts/screen_tianxunwen.py raw/whatsapp/xxx.txt
  python scripts/screen_tianxunwen.py raw/whatsapp/xxx.txt --only 天訊文 --extract-jinju
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

SKIP_ONLY = re.compile(r"^(圖像已省略|影片已省略|貼圖已忽略|語音通話|文件已忽略)\s*$")

CORE_KW = re.compile(
    r"素行|本元|太素|太元|外元|靜定|簡單|觀心|順隨|示曰|言曰|"
    r"覺醒|生命能量|愛自己|愛地球|愛眾生|信行醒|地靈國|天印|三元|"
    r"平安喜樂|返本歸元|醒者"
)

PRAYER_HEAD = re.compile(r"^(開經偈|迴向偈)")
PRAYER_ANY = re.compile(r"開經偈|迴向偈|十二願|誓願文|祈願文")

TASK_HEAD = re.compile(
    r"^(中午|早上|晚上|明天|後天|五點|四點|三點|叫|拿|傳|約|買|吃|泡|洗|"
    r"通知|告訴|給|讓|做一|先不|先做|都好|好了|可以了|現在|"
    r"\d{1,4}$|http)",
    re.I,
)

LIFE_KW = re.compile(
    r"^(中午|早上|晚上).{0,8}(吃|泡|睡|喝)|"
    r"(拿去保養|勞力士|吃飯|睡覺|起床)"
)

DECISION_KW = re.compile(r"^(先不做|先做|可以$|就這樣|不要$|用這個|就這個)")

ASK_KW = re.compile(r"(嗎|呢|好了沒|進度|有沒有).{0,4}$|？\s*$|\?\s*$")

ORG_SOP = re.compile(
    r"(核心公式|總體規劃|公頃|園區總面積|五大區域|短視頻核心|"
    r"70%畫面|製作素行～|應該傳遞|示意圖方向.*設計)"
)

CLASSIC_TITLE = re.compile(
    r"《[^》]*(心經|素語|白皮書|經)[^》]*》|素語三百|素行心經"
)


@dataclass
class ScreenResult:
    tx_id: str
    datetime: str
    功能主標: str
    天訊文細標: str
    公開: str
    產出: str
    score: int
    reason: str
    length: int
    preview: str
    jinju_candidates: str = ""


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


def core_kw_count(text: str) -> int:
    return len(CORE_KW.findall(text))


def extract_jinju_from_text(text: str, max_n: int = 8) -> list[str]:
    cands = []
    parts = re.split(r"[。！？\n；]", text)
    for p in parts:
        s = p.strip().strip("　 *•\t")
        if not s or s.startswith("一天大人"):
            continue
        s = re.sub(r"^[\d０-９]+[\.、．]\s*", "", s)
        n = len(s)
        if n < 8 or n > 80:
            continue
        if TASK_HEAD.match(s) or LIFE_KW.search(s):
            continue
        score = 0
        if core_kw_count(s) >= 1:
            score += 2
        if re.search(r"[，、].*[，、]", s):
            score += 1
        if re.search(
            r"(不是|而是|故|故曰|唯有|當|若|願|放大|降低|靜定|順隨|接受|繼續)",
            s,
        ):
            score += 2
        if 12 <= n <= 60 and score >= 2:
            cands.append((score, s))
    cands.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for _, s in cands:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_n:
            break
    return out


def classify_content(content: str) -> ScreenResult:
    c = content.strip()
    c_clean = re.sub(r"(圖像已省略|影片已省略|貼圖已忽略)", "", c).strip()
    n = len(c_clean)
    preview = c_clean.replace("\n", " / ")[:70]

    if n < 2:
        return ScreenResult("", "", "待標", "—", "否", "—", 0, "僅媒體", n, preview)

    has_示曰 = "示曰" in c_clean or "言曰" in c_clean
    has_title = bool(re.search(r"《[^》]{2,}》", c_clean))
    is_classic = bool(CLASSIC_TITLE.search(c_clean))
    kw = core_kw_count(c_clean)
    is_prayer = bool(PRAYER_HEAD.match(c_clean) or PRAYER_ANY.search(c_clean[:40]))
    is_task = bool(TASK_HEAD.match(c_clean))
    is_life = bool(LIFE_KW.search(c_clean)) and n < 120
    is_decision = bool(DECISION_KW.search(c_clean)) and n < 40
    is_ask = bool(ASK_KW.search(c_clean)) and n < 50
    is_sop = bool(ORG_SOP.search(c_clean))
    para = c_clean.count("。") + c_clean.count("；")

    score = 0
    reasons = []

    if has_示曰:
        score += 50
        reasons.append("示曰")
    if has_title and n > 100:
        score += 25
        reasons.append("標題長文")
    if is_classic:
        score += 20
        reasons.append("經典體")
    if kw >= 3:
        score += 15
        reasons.append(f"核心詞{kw}")
    elif kw >= 1:
        score += 8
        reasons.append(f"核心詞{kw}")
    if n >= 400:
        score += 20
        reasons.append("長文≥400")
    elif n >= 200:
        score += 10
        reasons.append("中長≥200")
    if para >= 3:
        score += 10
        reasons.append("多句")

    if is_task and n < 80 and not has_示曰:
        score -= 40
        reasons.append("任務開頭")
    if n < 12:
        score -= 25
        reasons.append("過短")

    reason = "+".join(reasons) if reasons else "無強訊號"

    主標 = "待標"
    細標 = "—"
    公開 = "是"
    產出 = "—"

    if is_life and not has_示曰:
        主標, 公開, 產出 = "生活作息", "否", "內部"
        reason += "+生活"
    elif is_decision and not has_示曰:
        主標, 公開, 產出 = "決策拍板", "否", "內部任務"
        reason += "+決策"
    elif is_prayer and (n < 300 or PRAYER_HEAD.match(c_clean)):
        主標, 細標, 產出 = "天訊文", "偈", "編印｜圖卡"
        reason += "+偈"
    elif has_示曰 and n >= 60:
        主標 = "天訊文"
        if is_classic or n >= 800:
            細標, 產出 = "經典", "文案｜典藏"
        elif n >= 200:
            細標, 產出 = "天訊文", "文案｜典藏"
        else:
            細標, 產出 = "短示", "文案｜圖卡"
    elif (has_title or is_classic) and n >= 250 and (kw >= 2 or is_classic):
        主標 = "天訊文"
        細標 = "經典" if (is_classic or n >= 600) else "天訊文"
        產出 = "文案｜典藏"
        reason += "+成篇"
    elif n >= 350 and kw >= 3 and para >= 4 and not is_sop:
        主標, 細標, 產出 = "天訊文", "天訊文", "文案"
        reason += "+長論"
    elif is_sop and not has_示曰:
        主標, 公開, 產出 = "組織推廣", "否", "內部｜規劃"
        reason += "+SOP"
    elif is_task and n < 100 and not has_示曰:
        主標, 公開, 產出 = "任務指派", "否", "內部任務"
        reason += "+任務"
    elif is_ask and not has_示曰:
        主標, 公開, 產出 = "詢問確認", "否", "內部"
        reason += "+詢問"
    elif re.search(r"(唸|素坐|禱唸|心語.*遍|每日.*靜)", c_clean) and n < 200:
        主標, 產出 = "修行指示", "編印｜內部"
        公開 = "是" if kw >= 1 else "否"
        reason += "+修行"
    elif score >= 45 and n >= 120 and not is_task:
        主標, 細標, 產出 = "天訊文", "短示" if n < 250 else "天訊文", "文案"
    else:
        主標, 公開, 產出 = "待標", "否", "—"

    if 主標 == "待標" and re.search(r"(專案|團隊|出版|演講|音樂會|品牌|推廣)", c_clean):
        if n > 80:
            主標, 公開, 產出 = "組織推廣", "否", "內部｜規劃"

    return ScreenResult(
        tx_id="",
        datetime="",
        功能主標=主標,
        天訊文細標=細標,
        公開=公開,
        產出=產出,
        score=score,
        reason=reason,
        length=n,
        preview=preview,
    )


def screen_messages(messages, extract_jinju=False):
    results = []
    for m in messages:
        r = classify_content(m["content"])
        dt = m["datetime"]
        r.datetime = dt.strftime("%Y-%m-%d %H:%M:%S")
        r.tx_id = m.get("tx_id") or f"TX-{dt.strftime('%Y%m%d%H%M%S')}"
        if extract_jinju and r.功能主標 == "天訊文" and r.公開 == "是":
            j = extract_jinju_from_text(m["content"])
            r.jinju_candidates = " || ".join(j)
        results.append(r)
    return results


def main():
    ap = argparse.ArgumentParser(description="天訊文自動篩選（定稿）")
    ap.add_argument("input", help="WhatsApp txt 或 master md / 目錄")
    ap.add_argument("--csv", default="", help="輸出 CSV")
    ap.add_argument("--only", default="", help="只顯示主標，逗號分隔")
    ap.add_argument("--md-report", default="", help="輸出 Markdown 報告")
    ap.add_argument("--extract-jinju", action="store_true", help="從天訊文抽金句")
    args = ap.parse_args()

    path = Path(args.input)
    messages = []
    if path.is_dir():
        for f in sorted(path.glob("*.md")):
            messages.extend(parse_master_md(f))
        for f in sorted(path.glob("*.txt")):
            messages.extend(parse_whatsapp(f))
    elif path.suffix.lower() == ".md":
        messages = parse_master_md(path)
    else:
        messages = parse_whatsapp(path)

    results = screen_messages(messages, extract_jinju=args.extract_jinju)
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else set()

    cnt = Counter(r.功能主標 for r in results)
    sub = Counter(r.天訊文細標 for r in results if r.功能主標 == "天訊文")
    print("========== 篩選統計 ==========")
    print(f"總則數：{len(results)}")
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    if sub:
        print("天訊文細標：")
        for k, v in sorted(sub.items(), key=lambda x: -x[1]):
            print(f"  · {k}: {v}")
    print("==============================\n")

    for r in results:
        if only and r.功能主標 not in only:
            continue
        if not only and r.功能主標 == "待標" and r.score < 20:
            continue
        print(
            f"{r.tx_id} [{r.功能主標}/{r.天訊文細標}] 公開={r.公開} "
            f"score={r.score} ({r.reason})"
        )
        print(f"  {r.preview}...")
        if r.jinju_candidates:
            print(f"  金句：{r.jinju_candidates[:120]}")
        print()

    if args.csv and results:
        outp = Path(args.csv)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
            w.writeheader()
            for r in results:
                w.writerow(asdict(r))
        print(f"CSV：{outp}")

    if args.md_report:
        lines = [
            "# 天訊文自動篩選報告",
            "",
            f"來源：`{path}`",
            "",
            "## 統計（功能主標）",
            "",
            "| 主標 | 則數 |",
            "|------|------|",
        ]
        for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} |")
        lines += ["", "## 天訊文細標", "", "| 細標 | 則數 |", "|------|------|"]
        for k, v in sorted(sub.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} |")
        lines += [
            "",
            "## 天訊文明細（公開）",
            "",
            "| TX-ID | 細標 | 分數 | 摘要 |",
            "|-------|------|------|------|",
        ]
        for r in results:
            if r.功能主標 != "天訊文" or r.公開 != "是":
                continue
            prev = r.preview.replace("|", "｜")[:40]
            lines.append(f"| {r.tx_id} | {r.天訊文細標} | {r.score} | {prev} |")
        if args.extract_jinju:
            lines += ["", "## 金句候選（抽自天訊文）", ""]
            for r in results:
                if not r.jinju_candidates:
                    continue
                lines.append(f"### {r.tx_id}")
                for j in r.jinju_candidates.split(" || "):
                    lines.append(f"- {j}")
                lines.append("")
        Path(args.md_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"MD：{args.md_report}")


if __name__ == "__main__":
    main()
