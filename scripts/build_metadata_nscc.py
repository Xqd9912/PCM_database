#!/usr/bin/env python3
"""NSCC 批次：由 data/metadata/nscc/models_dedup.tsv + data/raw 生成 metadata，
合并追加到主 metadata (data/metadata/pcm_metadata.json / .csv)。

- 贡献者按源目录：xqd=Qundao Xu, xumeng=Meng Xu, grc=Rongchuan Gu
- HPC 来源：<account>@10.68.0.1:~/<rel>/<file>
- 晶态假阳性分离：段恰好为 'c' / 含 crystal/cryst / 含 bond / 原子数<30
  （注意：不把 'C-...' 成分目录误判为晶态）
"""
import csv
import json
import re
from pathlib import Path

from ase.io import read

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DEDUP = ROOT / "data" / "metadata" / "nscc" / "models_dedup.tsv"
META_JSON = ROOT / "data" / "metadata" / "pcm_metadata.json"
META_CSV = ROOT / "data" / "metadata" / "pcm_metadata.csv"
EXCL = ROOT / "data" / "metadata" / "nscc" / "excluded_crystalline_review.tsv"

CONTRIB = {"xqd": "Qundao Xu", "xumeng": "Meng Xu", "grc": "Rongchuan Gu"}


def is_crystalline_path(rel: str) -> bool:
    for seg in rel.split("/"):
        s = seg.lower()
        if s == "c" or "crystal" in s or "cryst" in s or "bond" in s:
            return True
    return False


def incar_tebeg(p: Path):
    if not p.is_file():
        return None
    for line in p.read_text(errors="replace").splitlines():
        s = re.sub(r"[!#].*", "", line)
        m = re.search(r"TEBEG\s*=\s*(-?[0-9.]+)", s, re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def temp_label(tebeg):
    if tebeg is not None and 250 <= tebeg <= 450:
        return f"{int(round(tebeg))}K"
    return "300K"


def main():
    rows = []
    with DEDUP.open(encoding="utf-8") as f:
        for x in csv.DictReader(f, delimiter="\t"):
            rows.append(x)

    new, excluded, missing = [], [], []
    for x in rows:
        rp = x["rep_path"]                      # <account>/<dir>/...
        parts = rp.split("/")
        account, topdir = parts[0], parts[1]
        rel = "/".join(parts[1:])               # dir/... (相对账号家目录)
        fname = "CONTCAR" if x["how"] == "opt-CONTCAR" else "POSCAR"
        fpath = RAW / rp / fname
        if not fpath.is_file():
            missing.append(rp)
            continue
        try:
            atoms = read(str(fpath), format="vasp")
        except Exception as e:
            missing.append(f"{rp} (read-fail:{e})")
            continue
        n = len(atoms)
        reason = None
        if is_crystalline_path(rp):
            reason = "路径标记晶态(=c/crystal/bond)"
        elif n < 30:
            reason = f"原子数过小(N={n})"
        if reason:
            excluded.append({"rep_path": rp, "formula": atoms.get_chemical_formula(),
                             "N": n, "reason": reason})
            continue
        vol = atoms.get_volume()
        tebeg = incar_tebeg(RAW / rp / "INCAR")
        new.append({
            "化学式": atoms.get_chemical_formula(),
            "相": "amorphous",
            "温度": temp_label(tebeg),
            "结构文件": f"{rp}/{fname}",
            "密度_Atom_per_Angstrom3": round(n / vol, 5) if vol else None,
            "体系原子数": n,
            "贡献者": CONTRIB.get(topdir, topdir),
            "HPC来源路径": f"{account}@10.68.0.1:~/{rel}/{fname}",
            "代表帧来源": x["how"],
        })

    existing = json.loads(META_JSON.read_text(encoding="utf-8")) if META_JSON.exists() else []
    have = {r["结构文件"] for r in existing}
    added = [r for r in new if r["结构文件"] not in have]
    merged = existing + added

    META_JSON.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    import pandas as pd
    pd.DataFrame(merged).to_csv(META_CSV, index=False, encoding="utf-8-sig")

    EXCL.parent.mkdir(parents=True, exist_ok=True)
    with EXCL.open("w", encoding="utf-8") as g:
        g.write("rep_path\tformula\tN\treason\n")
        for e in excluded:
            g.write(f"{e['rep_path']}\t{e['formula']}\t{e['N']}\t{e['reason']}\n")

    print(f"NSCC 新增非晶: {len(added)} 条 (原库 {len(existing)} → 合并后 {len(merged)})")
    print(f"晶态假阳性分离: {len(excluded)} 条 -> {EXCL.name}")
    print(f"缺结构文件: {len(missing)} 条")
    from collections import Counter
    print("新增贡献者分布:", dict(Counter(r["贡献者"] for r in added)))


if __name__ == "__main__":
    main()
