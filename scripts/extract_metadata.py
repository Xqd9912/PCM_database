#!/usr/bin/env python3
"""从 POSCAR/CONTCAR 结构文件提取 metadata，输出 JSON 和 CSV。

用法：
    python extract_metadata.py <结构文件根目录> [--contributor "Qundao Xu"] \
        [--out-json data/metadata/pcm_metadata.json] \
        [--out-csv  data/metadata/pcm_metadata.csv]

字段：
    化学式 / 相 / 温度 / 结构文件 / 密度(Atom/Angstrom^3) / 体系原子数 / 贡献者

注意：
    - 相态(phase)与温度(temperature)无法从 POSCAR 本身获得，
      这里从文件路径启发式推断；无法确定时留空，待人工核对。
    - 密度定义为数密度 = 原子数 / 晶胞体积 (Atom/Angstrom^3)。
"""
import argparse
import json
import re
from pathlib import Path

from ase.io import read

# 结构文件名（大小写不敏感），可含后缀如 POSCAR_300K
STRUCT_PATTERNS = ("poscar", "contcar")

PHASE_KEYWORDS = {
    "amorphous": ["amorphous", "amor", "非晶", "aimd", "melt-quench", "quench"],
    "liquid": ["liquid", "liq", "液态", "melt"],
    "crystalline": ["crystal", "crystalline", "cryst", "晶态", "xtal"],
}

# 匹配温度，如 300K / 300k / T300 / 1200K
TEMP_RE = re.compile(r"(?<![0-9])(\d{2,4})\s*[kK](?![a-zA-Z])")


def infer_phase(path_str: str):
    low = path_str.lower()
    for phase, kws in PHASE_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                return phase
    return ""


def infer_temperature(path_str: str):
    m = TEMP_RE.search(path_str)
    if m:
        return f"{int(m.group(1))}K"
    return ""


def is_struct_file(name: str) -> bool:
    low = name.lower()
    return any(low.startswith(p) or p in low for p in STRUCT_PATTERNS)


def number_density(atoms) -> float:
    """数密度 Atom/Angstrom^3。"""
    vol = atoms.get_volume()
    return len(atoms) / vol if vol > 0 else float("nan")


def process(root: Path, contributor: str):
    records = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or not is_struct_file(f.name):
            continue
        rel = str(f.relative_to(root))
        try:
            atoms = read(str(f), format="vasp")
        except Exception as e:
            print(f"[skip] 读取失败 {rel}: {e}")
            continue
        records.append(
            {
                "化学式": atoms.get_chemical_formula(),
                "相": infer_phase(rel),
                "温度": infer_temperature(rel),
                "结构文件": rel,
                "密度_Atom_per_Angstrom3": round(number_density(atoms), 5),
                "体系原子数": len(atoms),
                "贡献者": contributor,
            }
        )
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="结构文件根目录")
    ap.add_argument("--contributor", default="", help="贡献者")
    ap.add_argument("--out-json", type=Path, default=Path("data/metadata/pcm_metadata.json"))
    ap.add_argument("--out-csv", type=Path, default=Path("data/metadata/pcm_metadata.csv"))
    args = ap.parse_args()

    records = process(args.root, args.contributor)
    if not records:
        print("未找到任何 POSCAR/CONTCAR 结构文件。")
        return

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    import pandas as pd

    pd.DataFrame(records).to_csv(args.out_csv, index=False, encoding="utf-8-sig")

    print(f"共 {len(records)} 条记录")
    print(f"JSON -> {args.out_json}")
    print(f"CSV  -> {args.out_csv}")


if __name__ == "__main__":
    main()
