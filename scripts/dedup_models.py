#!/usr/bin/env python3
"""对候选清单做「智能去重」，每个独立非晶模型保留一个代表结构。

去重键：从路径剥掉「阶段叶子段」（opt/md/scf/relax/prep/300K...），
再合并「泛函/步长/帧数」变体段；保留密度(dens)/尺寸(atom)/成分/model 索引等物理区分。

同一模型内代表选取：优先 opt 且 CONTCAR 最大者（opt 末帧）；否则 md-amorphous（第一帧）。
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

# 阶段叶子段：应剥离（大小写不敏感）
STAGE = re.compile(
    r"^\d*[-_]?(opt|md|scf|relax|relaxation|prep|top|bottom|median|equb|equil|sp|static)\w*$",
    re.I,
)
TEMPK = re.compile(r"^\d*[-_]?\d{2,4}k$", re.I)  # 阶段温度目录 300K / 2-400K（不含 kstep）
# 变体段：应合并（泛函 / MD 时长步长 / 采样帧）—— 方案A：frames 也合并
FUNC = re.compile(r"(hse|blyp|pbe0?|scan|lda|gga|b3lyp|pbesol)", re.I)  # 泛函关键词；勿用 -0.\d(会误匹配压缩比/密度)
STEP = re.compile(r"(\d+k?step|\d+\s*frames?|\d+ns|\d+ps)", re.I)  # kstep/step + frames
# 必须保留的物理区分段：密度/尺寸/model 索引/浓度 等（frame 不保留=合并）
KEEP = re.compile(r"(dens|density|atom|model|%|conc|scale|bond|chain)", re.I)


def model_key(path):
    parts = path.split("/")
    # 从尾部剥离阶段/变体段（frame/dens/size/model 等物理区分段不剥）
    while len(parts) > 2:
        leaf = parts[-1]
        if KEEP.search(leaf):
            break
        if STAGE.match(leaf) or TEMPK.match(leaf) or FUNC.search(leaf) or STEP.search(leaf):
            parts.pop()
            continue
        break
    return "/".join(parts)


def formula(sp, ct):
    s, c = sp.split(), ct.split()
    if len(s) != len(c):
        return f"{sp}|{ct}"
    return "".join(f"{a}{b}" for a, b in zip(s, c))


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/metadata/pcm_candidates.tsv")
    rows = []
    with src.open(encoding="utf-8") as f:
        for x in csv.DictReader(f, delimiter="\t"):
            rows.append(x)

    groups = defaultdict(list)
    for x in rows:
        groups[model_key(x["path"])].append(x)

    def rep(cands):
        opts = [c for c in cands if c["type"] == "opt" and c.get("contcar_size", "0") not in ("", "0")]
        if opts:
            return max(opts, key=lambda c: int(c["contcar_size"] or 0)), "opt-CONTCAR"
        amd = [c for c in cands if c["type"] == "md-amorphous"]
        if amd:
            return amd[0], "md-first-frame"
        return cands[0], cands[0]["type"]

    chosen = []
    for key, cands in sorted(groups.items()):
        r, how = rep(cands)
        chosen.append({"key": key, "rep": r, "how": how, "n": len(cands)})

    print(f"候选 {len(rows)} → 去重后独立模型 {len(chosen)}")
    multi = [c for c in chosen if c["n"] > 1]
    print(f"其中 {len(multi)} 个模型由多个候选合并而来\n")

    print("=== 合并样本(候选数最多的前15个模型) ===")
    for c in sorted(multi, key=lambda z: -z["n"])[:15]:
        print(f"[{c['n']}候选→1] {c['key']}")
        print(f"      取: {c['rep']['path']}  ({c['how']})")

    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        with out.open("w", encoding="utf-8") as g:
            g.write("model_key\trep_path\thow\tn_merged\tformula\tspecies\tcounts\tnatoms\ttebeg\n")
            for c in chosen:
                r = c["rep"]
                g.write(
                    f"{c['key']}\t{r['path']}\t{c['how']}\t{c['n']}\t"
                    f"{formula(r['species'], r['counts'])}\t{r['species']}\t{r['counts']}\t"
                    f"{r['natoms']}\t{r['tebeg']}\n"
                )
        print(f"\n去重模型清单已写入: {out} ({len(chosen)} 行)")


if __name__ == "__main__":
    main()
