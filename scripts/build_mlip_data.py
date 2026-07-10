#!/usr/bin/env python
"""登记 MLIP 训练集（DFT 标注）并为前端 MLIP dataset 板块预计算数据。

输入:
  data/MLIP_training_data_DFT_labeled/*.xyz   —— extended XYZ，含 REF_energy / REF_forces

输出:
  data/metadata/mlip_metadata.json / .csv     —— 每帧一条记录（数据库登记，全量）
  docs/mlip.json                              —— 站点载荷：数据集统计 + 直方图分箱 + 抽样点元数据
  docs/mlip_descriptors.json                  —— 抽样帧的 SOAP 向量（base64 float32，按需懒加载）

要点:
  * 直方图与数据集统计走全量帧；SOAP 分布图对每个数据集沿轨迹均匀抽样（默认上限 800 帧），
    因为 MD 相邻帧高度相关，抽样几乎不改变分布形状，却能把描述符文件压到与
    docs/descriptors.json 同量级。
  * SOAP 超参与 build_descriptors.py 完全一致（元素无关，252 维），因此 MLIP 帧与主库结构
    落在同一可比特征空间。

用法（在 pcm_database 环境内）:
  python scripts/build_mlip_data.py [--cap 800] [--bins 60]
"""
import argparse
import base64
import csv
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from ase.io import iread
from dscribe.descriptors import SOAP

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "MLIP_training_data_DFT_labeled"
META_DIR = ROOT / "data" / "metadata"
DOCS = ROOT / "docs"

# 与 build_descriptors.py 保持一致 —— 同一 252 维元素无关特征空间
SOAP_PARAMS = dict(r_cut=6.0, n_max=8, l_max=6, periodic=True, average="outer")
DUMMY_Z = 6
SOAP_BATCH = 32

# 直方图分位裁剪：抑制极少数离群力/能量把色标和坐标轴拉飞
CLIP = (0.001, 0.999)

DATASETS = [
    ("GST225", "GST225.xyz", "Ge2Sb2Te5"),
    ("GeTe", "GeTe.xyz", "GeTe"),
    ("Sb2Te3", "Sb2Te3.xyz", "Sb2Te3"),
    ("MP_pure_GST", "MP_filtered_pure_GST.xyz", "Materials Project (Ge–Sb–Te)"),
]


def frame_records(path: Path, key: str, cap: int):
    """单遍扫描一个 xyz：产出每帧标量记录、力分量数组、以及抽样帧的 Atoms 副本。

    抽样索引需要总帧数，故先廉价数一遍帧头（读 natoms 行后跳过 natoms+1 行）。
    """
    n_frames = 0
    with path.open() as fh:
        while True:
            line = fh.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            nat = int(line)
            for _ in range(nat + 1):
                fh.readline()
            n_frames += 1

    stride = max(1, int(np.ceil(n_frames / cap)))
    want = set(range(0, n_frames, stride))

    rows, fcomp, fmag, sampled = [], [], [], []
    for i, atoms in enumerate(iread(str(path), format="extxyz")):
        nat = len(atoms)
        e = float(atoms.info["REF_energy"])
        f = np.asarray(atoms.arrays["REF_forces"], dtype=np.float64)
        mag = np.linalg.norm(f, axis=1)
        vol = float(atoms.get_volume())
        rows.append(
            {
                "帧ID": f"{key}:{i:05d}",
                "数据集": key,
                "化学式": atoms.get_chemical_formula(empirical=True),
                "完整化学式": atoms.get_chemical_formula(mode="hill"),
                "体系原子数": nat,
                "构型标签": str(atoms.info.get("config_type", "")),
                "能量_eV": round(e, 6),
                "能量_eV_per_atom": round(e / nat, 6),
                "力_最大模长_eV_per_A": round(float(mag.max()), 6),
                "力_RMS_eV_per_A": round(float(np.sqrt((f**2).sum() / nat)), 6),
                "体积_Angstrom3": round(vol, 4),
                "密度_Atom_per_Angstrom3": round(nat / vol, 6),
                "源文件": f"data/MLIP_training_data_DFT_labeled/{path.name}",
                "帧序号": i,
            }
        )
        fcomp.append(f.ravel())
        fmag.append(mag)
        if i in want:
            a = atoms.copy()
            a.set_atomic_numbers([DUMMY_Z] * nat)
            a.set_pbc(True)
            sampled.append((i, a))
        if (i + 1) % 500 == 0:
            print(f"  {key}: {i + 1}/{n_frames}", flush=True)

    return rows, np.concatenate(fcomp), np.concatenate(fmag), sampled


def stats(a: np.ndarray) -> dict:
    a = np.asarray(a, dtype=np.float64)
    return {
        "min": float(a.min()),
        "max": float(a.max()),
        "mean": float(a.mean()),
        "std": float(a.std()),
    }


def shared_edges(arrays, bins, lo_zero=False):
    """跨数据集共享分箱边界（按分位裁剪后取并集范围），使各数据集直方图可直接比较。

    lo_zero：|F| 这类非负量把下界钉在 0——否则 0.1% 分位会把弛豫结构的近零受力
    判成「范围外」而丢弃。
    """
    allv = np.concatenate([np.asarray(a) for a in arrays])
    lo = 0.0 if lo_zero else float(np.quantile(allv, CLIP[0]))
    hi = float(np.quantile(allv, CLIP[1]))
    if not hi > lo:
        lo, hi = float(allv.min()), float(allv.max()) or 1.0
    if not hi > lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, bins + 1)


def counts_on(edges, values):
    """在给定边界上计数。范围外的样本单独计数而非并入首/末箱——
    折进边界箱会在图上造出并不存在的尖峰，这里如实报告被裁掉的尾部数量。"""
    v = np.asarray(values)
    c, _ = np.histogram(v, bins=edges)
    below = int((v < edges[0]).sum())
    above = int((v > edges[-1]).sum())
    return [int(x) for x in c], [below, above]


def b64(a):
    return base64.b64encode(np.asarray(a, np.float32).ravel(order="C").tobytes()).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=800, help="每个数据集参与 SOAP 分布图的抽样帧上限")
    ap.add_argument("--bins", type=int, default=60)
    ap.add_argument("--skip-soap", action="store_true",
                    help="沿用已有的 docs/mlip_descriptors.json（仅当 --cap 未变时有效），只重算统计")
    args = ap.parse_args()

    all_rows, ds_meta, sample_pool = [], [], []
    epa_by_ds, fmag_by_ds, fcomp_by_ds = {}, {}, {}

    for key, fname, label in DATASETS:
        path = SRC / fname
        if not path.is_file():
            print(f"跳过缺失文件 {path}")
            continue
        print(f"[{key}] 解析 {fname}")
        rows, fcomp, fmag, sampled = frame_records(path, key, args.cap)
        all_rows += rows

        epa = np.array([r["能量_eV_per_atom"] for r in rows])
        epa_by_ds[key], fmag_by_ds[key], fcomp_by_ds[key] = epa, fmag, fcomp

        elems = sorted({e for r in rows for e in re.findall(r"[A-Z][a-z]?", r["化学式"])})
        top_cfg = Counter(r["构型标签"] for r in rows if r["构型标签"]).most_common(5)
        ds_meta.append(
            {
                "key": key,
                "label": label,
                "file": fname,
                "n_frames": len(rows),
                "n_atoms": int(sum(r["体系原子数"] for r in rows)),
                "natoms_min": min(r["体系原子数"] for r in rows),
                "natoms_max": max(r["体系原子数"] for r in rows),
                "elements": elems,
                "top_config_types": [{"k": k, "v": v} for k, v in top_cfg],
                "epa": stats(epa),
                "fmag": stats(fmag),
                "n_sampled": len(sampled),
            }
        )
        by_idx = {r["帧序号"]: r for r in rows}
        sample_pool += [(key, by_idx[i], a) for i, a in sampled]
        print(f"  帧={len(rows)} 原子={ds_meta[-1]['n_atoms']} 抽样={len(sampled)}")

    if not all_rows:
        raise SystemExit("没有解析到任何帧")

    # ---------- 数据库登记（全量） ----------
    META_DIR.mkdir(parents=True, exist_ok=True)
    mj = META_DIR / "mlip_metadata.json"
    mj.write_text(json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    mc = META_DIR / "mlip_metadata.csv"
    with mc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print(f"mlip_metadata: {len(all_rows)} 帧 → {mj.name} / {mc.name}")

    # ---------- 直方图（全量，共享分箱） ----------
    keys = [d["key"] for d in ds_meta]
    hist = {}
    for name, src in (("epa", epa_by_ds), ("fmag", fmag_by_ds), ("fcomp", fcomp_by_ds)):
        edges = shared_edges([src[k] for k in keys], args.bins, lo_zero=(name == "fmag"))
        per = {k: counts_on(edges, src[k]) for k in keys}
        hist[name] = {
            "edges": [float(x) for x in edges],
            "counts": {k: per[k][0] for k in keys},
            "outside": {k: per[k][1] for k in keys},  # [低于下界, 高于上界] 的样本数
        }

    # ---------- SOAP（抽样帧） ----------
    desc_out = DOCS / "mlip_descriptors.json"
    if args.skip_soap:
        existing = json.loads(desc_out.read_text())
        if existing["n"] != len(sample_pool):
            raise SystemExit(f"--skip-soap 不可用：已有描述符 {existing['n']} 行 ≠ 当前抽样 {len(sample_pool)} 帧")
        dim, vecs = existing["dim"], None
        print(f"复用已有描述符 {desc_out.name}（{existing['n']}×{dim}）")
    else:
        soap = SOAP(species=[DUMMY_Z], **SOAP_PARAMS)
        dim = soap.get_number_of_features()
        print(f"SOAP dim={dim}，抽样帧 {len(sample_pool)} 个")
        vecs = np.zeros((len(sample_pool), dim), dtype=np.float64)
        for s in range(0, len(sample_pool), SOAP_BATCH):
            chunk = [a for _, _, a in sample_pool[s : s + SOAP_BATCH]]
            vecs[s : s + len(chunk)] = np.atleast_2d(soap.create(chunk, n_jobs=1))
            print(f"  soap {min(s + SOAP_BATCH, len(sample_pool))}/{len(sample_pool)}", flush=True)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs /= norms

    # 抽样点的轻量元数据（着色 / tooltip 用），顺序与 SOAP 行一一对应
    formulas = sorted({r["化学式"] for _, r, _ in sample_pool})
    fidx = {f: i for i, f in enumerate(formulas)}
    points = {
        "ds": [keys.index(k) for k, _, _ in sample_pool],
        "fid": [r["帧ID"] for _, r, _ in sample_pool],
        "formula": [fidx[r["化学式"]] for _, r, _ in sample_pool],
        "natoms": [r["体系原子数"] for _, r, _ in sample_pool],
        "epa": [r["能量_eV_per_atom"] for _, r, _ in sample_pool],
        "fmax": [r["力_最大模长_eV_per_A"] for _, r, _ in sample_pool],
        "frms": [r["力_RMS_eV_per_A"] for _, r, _ in sample_pool],
        "density": [r["密度_Atom_per_Angstrom3"] for _, r, _ in sample_pool],
    }

    DOCS.mkdir(exist_ok=True)
    site = {
        "meta": {
            "n_frames": len(all_rows),
            "n_atoms": int(sum(d["n_atoms"] for d in ds_meta)),
            "n_datasets": len(ds_meta),
            "label_level": "DFT",
            "energy_key": "REF_energy",
            "forces_key": "REF_forces",
            "sample_cap": args.cap,
            "n_sampled": len(sample_pool),
            "hist_clip": list(CLIP),
            "soap": {k: v for k, v in SOAP_PARAMS.items()},
            "soap_species_mode": "element-agnostic",
            "note": "Histograms and per-dataset statistics cover all frames; the SOAP map uses a uniform per-dataset subsample.",
        },
        "datasets": ds_meta,
        "formulas": formulas,
        "hist": hist,
        "points": points,
    }
    (DOCS / "mlip.json").write_text(json.dumps(site, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if vecs is not None:
        desc_out.write_text(json.dumps({"dim": dim, "n": len(sample_pool), "data": b64(vecs)}), encoding="utf-8")
    for p in (DOCS / "mlip.json", desc_out):
        print(f"wrote {p} ({p.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
