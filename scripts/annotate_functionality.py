#!/usr/bin/env python3
"""初步标注材料功能性 (PCM / OTS / SOM / PCM candidates / Others)。

规则见项目讨论：
  - MP 晶态(source_frame=materials-project)：成分仅 {Ge,Sb,Te} 且含≥2 种 -> PCM；否则 PCM candidates。
  - 其余(HPC)：AIST->PCM；Te 占比>0.7->Others；含 Te 且(Ge 或 Sb)且 GST 占比>=0.6->PCM；
    含 Ge 且(Se 或 S)且无 Te->OTS；否则 Others。
写回 docs/data.json 的 functionality 字段，并同步 data/metadata/pcm_metadata.json(.csv) 的“功能性”。
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = ROOT / "docs" / "data.json"
META_JSON = ROOT / "data" / "metadata" / "pcm_metadata.json"
META_CSV = ROOT / "data" / "metadata" / "pcm_metadata.csv"

GST = {"Ge", "Sb", "Te"}


def parse_counts(formula):
    c = {}
    for sym, num in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        if not sym:
            continue
        c[sym] = c.get(sym, 0) + (int(num) if num else 1)
    return c


def classify(formula, is_mp):
    counts = parse_counts(formula)
    n = sum(counts.values()) or 1
    els = set(counts)
    f = {e: counts[e] / n for e in counts}
    fTe = f.get("Te", 0.0)
    gst_frac = sum(f.get(e, 0.0) for e in GST)

    if is_mp:
        if els <= GST and (len(els & GST) >= 2 or els == {"Sb"}):
            return "PCM"
        return "PCM candidates"

    if {"Ag", "In", "Sb", "Te"} <= els:
        return "PCM"
    if "As" in els and ("Ge" in els or "Si" in els) and ("Se" in els or "Te" in els):
        return "OTS"  # 含 As 的 Ge/Si 硒/碲化物（AsGeSiTe/AsGeNSiTe/AsGeSe …）
    if {"In", "Si", "Te"} <= els and not ({"Ge", "Sb"} & els):
        return "OTS"  # In-Si-Te 族（无 Ge/Sb）
    if len(els) == 2 and "Te" in els and "Sb" not in els and (fTe > 0.5 or "In" in els):
        return "OTS"  # x-Te 二元：Te-rich(InTe9/GeTe9)或 In-Te(任意比例)；Sb-Te 例外→PCM
    if "Te" in els and ("Ge" in els or "Sb" in els) and gst_frac >= 0.6:
        return "PCM"
    if "Ge" in els and ("Se" in els or "S" in els) and "Te" not in els:
        return "OTS"
    return "Others"


def main():
    data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    by_path = {}
    dist = Counter()
    sys_map = {}  # system -> Counter(functionality)
    for r in data:
        is_mp = r.get("source_frame") == "materials-project"
        fn = classify(r["formula"], is_mp)
        r["functionality"] = fn
        by_path[r["path"]] = fn
        dist[fn] += 1
        sys_map.setdefault(r["system"], Counter())[fn] += 1
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 同步 metadata
    if META_JSON.exists():
        recs = json.loads(META_JSON.read_text(encoding="utf-8"))
        for r in recs:
            r["功能性"] = by_path.get(r.get("结构文件"), "Others")
        META_JSON.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            import pandas as pd

            pd.DataFrame(recs).to_csv(META_CSV, index=False, encoding="utf-8-sig")
        except Exception as e:  # noqa: BLE001
            print("CSV 跳过:", e)

    print("=== 功能性分布 ===")
    for k, v in dist.most_common():
        print(f"  {k:16s} {v}")
    print(f"  合计 {sum(dist.values())}")

    print("\n=== 按体系(Top 系统的标注)——供复核 ===")
    order = ["PCM", "OTS", "SOM", "PCM candidates", "Others"]
    rows = sorted(sys_map.items(), key=lambda kv: -sum(kv[1].values()))
    for system, c in rows[:40]:
        tag = "/".join(f"{k}:{c[k]}" for k in order if c[k])
        print(f"  {system:14s} n={sum(c.values()):<4d} {tag}")


if __name__ == "__main__":
    main()
