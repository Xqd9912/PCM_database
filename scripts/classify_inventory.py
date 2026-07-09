#!/usr/bin/env python3
"""分析 HPC 扫描清单 pcm_inv.tsv：分布摸底 + 非晶模型候选分类。

分类判据（基于 INCAR 的 IBRION/TEBEG/TEEND/NSW）：
  - static  : IBRION=-1 (或缺省) 且 NSW<=1  —— 静态单点，多为 ML 采样，排除
  - opt     : IBRION in {1,2}               —— 几何优化，取 CONTCAR(末帧)
  - md      : IBRION=0                       —— 分子动力学
      * liquid    : TEBEG>=1200
      * quench    : TEBEG!=TEEND (升降温)
      * amorphous : 250<=TEBEG<=450 且 TEBEG==TEEND
  - other   : 其它

非晶「代表性模型」候选：
  - 优先 opt 且有非空 CONTCAR
  - 否则 amorphous-md（取第一帧=POSCAR）
"""
import sys
from collections import Counter
from pathlib import Path


def to_num(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def natoms(counts):
    tot = 0
    for x in counts.split():
        try:
            tot += int(x)
        except ValueError:
            return None
    return tot if tot else None


def classify(r):
    ib = to_num(r["ibrion"])
    tb = to_num(r["tebeg"])
    tn = to_num(r["teend"])
    nsw = to_num(r["nsw"])
    if ib == -1 or (ib is None and (nsw is None or nsw <= 1)):
        return "static"
    if ib in (1.0, 2.0):
        return "opt"
    if ib == 0.0:
        if tb is not None and tb >= 1200:
            return "md-liquid"
        if tb is not None and tn is not None and abs(tb - tn) > 1:
            return "md-quench"
        if tb is not None and 250 <= tb <= 450:
            return "md-amorphous"
        return "md-other"
    return "other"


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/metadata/pcm_inv.tsv")
    rows = []
    with path.open(encoding="utf-8", errors="replace") as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                parts += [""] * (len(header) - len(parts))
            rows.append(dict(zip(header, parts)))

    print(f"总计算目录: {len(rows)}")
    for r in rows:
        r["type"] = classify(r)
        r["natoms"] = natoms(r.get("counts", ""))
        r["has_contcar"] = to_num(r.get("contcar_size", "0")) not in (None, 0.0)

    print("\n=== 按类型分布 ===")
    for t, c in Counter(r["type"] for r in rows).most_common():
        print(f"  {t:14s} {c}")

    print("\n=== IBRION 分布 ===")
    for v, c in Counter(r["ibrion"] or "(空)" for r in rows).most_common():
        print(f"  IBRION={v:6s} {c}")

    print("\n=== TEBEG 分布(top15) ===")
    for v, c in Counter(r["tebeg"] or "(空)" for r in rows).most_common(15):
        print(f"  TEBEG={v:8s} {c}")

    # 非晶代表性候选
    opt = [r for r in rows if r["type"] == "opt" and r["has_contcar"]]
    amd = [r for r in rows if r["type"] == "md-amorphous"]
    print(f"\n=== 非晶模型候选 ===")
    print(f"  opt+CONTCAR : {len(opt)}")
    print(f"  md-amorphous: {len(amd)}")

    print("\n=== 各成员 opt+CONTCAR 候选数 ===")
    def member(p):
        return p.split("/", 1)[0]
    for m, c in Counter(member(r["path"]) for r in opt).most_common():
        print(f"  {m:8s} {c}")

    print("\n=== opt+CONTCAR 候选样本(前20) ===")
    for r in opt[:20]:
        print(f"  {r['path']}  [{r['species']} | {r['counts']} | N={r['natoms']}]")

    # 导出候选清单（opt+CONTCAR 优先，md-amorphous 兜底）
    out_cand = None
    for i, a in enumerate(sys.argv):
        if a == "--out-candidates" and i + 1 < len(sys.argv):
            out_cand = Path(sys.argv[i + 1])
    if out_cand:
        with out_cand.open("w", encoding="utf-8") as g:
            g.write("path\ttype\tspecies\tcounts\tnatoms\tcontcar_size\ttebeg\tteend\tnsw\n")
            for r in opt + amd:
                g.write(
                    f"{r['path']}\t{r['type']}\t{r['species']}\t{r['counts']}\t"
                    f"{r['natoms']}\t{r['contcar_size']}\t{r['tebeg']}\t{r['teend']}\t{r['nsw']}\n"
                )
        print(f"\n候选清单已写入: {out_cand} (共 {len(opt)+len(amd)} 行)")


if __name__ == "__main__":
    main()
