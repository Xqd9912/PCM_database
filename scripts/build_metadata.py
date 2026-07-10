#!/usr/bin/env python3
"""基于去重模型清单 + 本地 data/raw 结构文件，用 ASE 生成 metadata (JSON+CSV)。

字段：化学式 | 相 | 温度 | 结构文件 | 密度(Atom/Å³) | 体系原子数 | 贡献者 | HPC来源路径
"""
import csv
import json
import re
from pathlib import Path

from ase.io import read

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DEDUP = ROOT / "data" / "metadata" / "pcm_models_dedup.tsv"

# 贡献者：按第一批成员目录映射真名
CONTRIBUTOR = {
    "xqd": "Qundao Xu",
    "ysj": "Shaojie Yuan",
    "yyf": "Yifan Yan",
    "tsq": "Siqi Tang",
    "hhy": "Henyi Hu",
    "wyh": "Yuhao Wang",
    "wh": "Huan Wang",
}
DEFAULT_CONTRIBUTOR = "Qundao Xu"


def incar_tebeg(incar_path: Path):
    if not incar_path.is_file():
        return None
    txt = incar_path.read_text(errors="replace")
    for line in txt.splitlines():
        s = re.sub(r"[!#].*", "", line)
        m = re.search(r"TEBEG\s*=\s*(-?[0-9.]+)", s, re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def temperature_label(how, tebeg):
    # 非晶模型代表 300K 淬火结构；若 rep INCAR TEBEG 在常温区间则用其值
    if tebeg is not None and 250 <= tebeg <= 450:
        return f"{int(round(tebeg))}K"
    return "300K"


def main():
    rows = []
    with DEDUP.open(encoding="utf-8") as f:
        for x in csv.DictReader(f, delimiter="\t"):
            rows.append(x)

    # 晶态假阳性判据：路径段含 bond/crystal/c，或原子数过小(<30)不可能是非晶
    CRYST_SEG = re.compile(r"(^|/)(bond|crystal|cryst|c)(/|$|-)", re.I)

    records, missing, excluded = [], [], []
    for x in rows:
        rp = x["rep_path"]
        fname = "CONTCAR" if x["how"] == "opt-CONTCAR" else "POSCAR"
        fpath = RAW / rp / fname
        if not fpath.is_file():
            missing.append((rp, fname, x["how"]))
            continue
        try:
            atoms = read(str(fpath), format="vasp")
        except Exception as e:
            missing.append((rp, fname, f"read-fail:{e}"))
            continue
        n = len(atoms)
        reason = None
        if CRYST_SEG.search(rp):
            reason = "路径标记晶态(bond/crystal/c)"
        elif n < 30:
            reason = f"原子数过小(N={n})，疑晶态原胞"
        if reason:
            excluded.append({"rep_path": rp, "化学式": atoms.get_chemical_formula(),
                             "N": n, "reason": reason})
            continue
        vol = atoms.get_volume()
        member = rp.split("/", 1)[0]
        tebeg = incar_tebeg(RAW / rp / "INCAR")
        records.append(
            {
                "化学式": atoms.get_chemical_formula(),
                "相": "amorphous",
                "温度": temperature_label(x["how"], tebeg),
                "结构文件": f"{rp}/{fname}",
                "密度_Atom_per_Angstrom3": round(len(atoms) / vol, 5) if vol else None,
                "体系原子数": len(atoms),
                "贡献者": CONTRIBUTOR.get(member, DEFAULT_CONTRIBUTOR),
                "HPC来源路径": f"~/{rp}/{fname}",
                "代表帧来源": x["how"],
            }
        )

    out_json = ROOT / "data" / "metadata" / "pcm_metadata.json"
    out_csv = ROOT / "data" / "metadata" / "pcm_metadata.csv"
    out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    import pandas as pd

    pd.DataFrame(records).to_csv(out_csv, index=False, encoding="utf-8-sig")

    # 晶态假阳性 -> 复核文件（分离，不删除）
    excl_path = ROOT / "data" / "metadata" / "excluded_crystalline_review.tsv"
    with excl_path.open("w", encoding="utf-8") as g:
        g.write("rep_path\t化学式\tN\treason\n")
        for e in excluded:
            g.write(f"{e['rep_path']}\t{e['化学式']}\t{e['N']}\t{e['reason']}\n")

    print(f"成功入库(非晶): {len(records)} 条")
    print(f"分离晶态假阳性(复核): {len(excluded)} 条 -> {excl_path.name}")
    print(f"缺结构文件(已剔除): {len(missing)} 条")
    print(f"\nJSON -> {out_json}")
    print(f"CSV  -> {out_csv}")


if __name__ == "__main__":
    main()
