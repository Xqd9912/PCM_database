#!/usr/bin/env python3
"""批量入库 Materials Project 晶态结构 (c_PCM_database/mp-*/POSCAR)。

口径与 scripts/serve_local.py 一致：
  - 结构复制到 data/raw/mp/<mp-id-formula>/POSCAR
  - ASE 读取算化学式 / 数密度(Atom/Å³) / 原子数
  - 追加 data/metadata/pcm_metadata.json + .csv
  - 追加 docs/data.json，并复制到 docs/structures/<sid>.poscar
固定：相=crystalline，温度=0K，贡献者=Materials Project，HPC来源=MP URL。
按 raw 相对路径去重，可安全重跑。
"""
import json
import re
import shutil
from pathlib import Path

from ase.io import read

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "c_PCM_database"
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "docs"
META_JSON = ROOT / "data" / "metadata" / "pcm_metadata.json"
META_CSV = ROOT / "data" / "metadata" / "pcm_metadata.csv"
DATA_JSON = DOCS / "data.json"
STRUCT_DIR = DOCS / "structures"

PHASE = "crystalline"
TEMP = "0K"
CONTRIBUTOR = "Materials Project"
SOURCE_FRAME = "materials-project"


def elements(formula):
    return sorted(set(re.findall(r"[A-Z][a-z]?", formula)))


def next_sid_gen(used):
    n = 0
    while True:
        sid = f"s{n:04d}"
        if sid not in used:
            used.add(sid)
            yield sid
        n += 1


def main():
    recs = json.loads(META_JSON.read_text(encoding="utf-8")) if META_JSON.exists() else []
    data = json.loads(DATA_JSON.read_text(encoding="utf-8")) if DATA_JSON.exists() else []
    existing_paths = {r["结构文件"] for r in recs}
    used_sids = {d["sid"] for d in data}
    sid_gen = next_sid_gen(used_sids)
    STRUCT_DIR.mkdir(parents=True, exist_ok=True)

    dirs = sorted(d for d in SRC.iterdir() if d.is_dir() and d.name.startswith("mp-"))
    added, skipped, failed = 0, 0, []
    for d in dirs:
        poscar = d / "POSCAR"
        if not poscar.is_file():
            failed.append((d.name, "无 POSCAR"))
            continue
        rel = f"mp/{d.name}/POSCAR"
        if rel in existing_paths:
            skipped += 1
            continue
        try:
            atoms = read(str(poscar), format="vasp")
        except Exception as e:  # noqa: BLE001
            failed.append((d.name, f"读取失败:{e}"))
            continue
        n = len(atoms)
        vol = atoms.get_volume()
        formula = atoms.get_chemical_formula()

        # MP URL 作溯源
        mp_url = ""
        info = d / "info.json"
        if info.is_file():
            try:
                j = json.loads(info.read_text(encoding="utf-8"))
                mp_url = j.get("mp_url") or (
                    f"https://materialsproject.org/materials/{j.get('mp_id')}" if j.get("mp_id") else ""
                )
            except Exception:  # noqa: BLE001
                pass

        # 复制结构到 data/raw
        content = poscar.read_text(encoding="utf-8", errors="replace")
        dst = RAW / "mp" / d.name / "POSCAR"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")

        rec = {
            "化学式": formula,
            "相": PHASE,
            "温度": TEMP,
            "结构文件": rel,
            "密度_Atom_per_Angstrom3": round(n / vol, 5) if vol else None,
            "体系原子数": n,
            "贡献者": CONTRIBUTOR,
            "HPC来源路径": mp_url,
            "代表帧来源": SOURCE_FRAME,
        }
        recs.append(rec)
        existing_paths.add(rel)

        sid = next(sid_gen)
        (STRUCT_DIR / f"{sid}.poscar").write_text(content, encoding="utf-8")
        els = elements(formula)
        data.append(
            {
                "sid": sid, "formula": formula, "system": "".join(els), "elements": els,
                "phase": PHASE, "temperature": TEMP, "natoms": n,
                "density": rec["密度_Atom_per_Angstrom3"], "contributor": CONTRIBUTOR,
                "path": rel, "hpc_source": mp_url, "source_frame": SOURCE_FRAME,
            }
        )
        added += 1

    META_JSON.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    import pandas as pd

    pd.DataFrame(recs).to_csv(META_CSV, index=False, encoding="utf-8-sig")
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"新增晶态: {added} 条")
    print(f"已存在跳过: {skipped} 条")
    print(f"失败: {len(failed)} 条")
    for name, why in failed:
        print(f"  - {name}: {why}")
    print(f"总记录: {len(recs)} 条 (data.json {len(data)} 条)")


if __name__ == "__main__":
    main()
