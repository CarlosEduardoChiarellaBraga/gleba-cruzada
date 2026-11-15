"""Utilitários comuns aos cruzamentos (etapas 06–10)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CRS_METRICO, OUT, PROC  # noqa: E402,F401

RES = OUT / "cruzamentos"
RES.mkdir(parents=True, exist_ok=True)

N_TOTAL = duckdb.sql(f"SELECT count(*) FROM '{PROC / 'operacoes_go.parquet'}'").fetchall()[0][0]


def load_fp() -> gpd.GeoDataFrame:
    fp = gpd.read_parquet(PROC / "op_footprint.parquet")
    return fp.set_crs(CRS_METRICO, allow_override=True)


def load_ops() -> pd.DataFrame:
    return duckdb.sql(f"SELECT * FROM '{PROC / 'operacoes_go.parquet'}'").df()


def banco(is_bb) -> str:
    return "BB" if bool(is_bb) else "Demais"


def resumo(ele: pd.DataFrame, flag: pd.Series | np.ndarray, nome: str, extra: dict | None = None) -> dict:
    """Contagem de disparos: total, % dos elegíveis, % do recorte, BB vs demais."""
    ele = ele.assign(_f=np.asarray(flag, dtype=bool))
    bb, de = ele[ele.is_bb], ele[~ele.is_bb]
    r = dict(
        cruzamento=nome,
        elegiveis=int(len(ele)),
        disparam=int(ele._f.sum()),
        pct_elegiveis=round(100 * ele._f.mean(), 2) if len(ele) else None,
        pct_recorte=round(100 * ele._f.sum() / N_TOTAL, 3),
        valor_disparos_rs_mi=round(ele.loc[ele._f, "vl_parc_credito"].sum() / 1e6, 1),
        bb_elegiveis=int(len(bb)), bb_disparam=int(bb._f.sum()),
        bb_pct=round(100 * bb._f.mean(), 2) if len(bb) else None,
        demais_elegiveis=int(len(de)), demais_disparam=int(de._f.sum()),
        demais_pct=round(100 * de._f.mean(), 2) if len(de) else None,
    )
    if extra:
        r.update(extra)
    return r


def salva_resumo(nome_arquivo: str, linhas: list[dict]):
    pd.DataFrame(linhas).to_csv(RES / f"{nome_arquivo}_resumo.csv", index=False)
    json.dump(linhas, open(RES / f"{nome_arquivo}_resumo.json", "w"), ensure_ascii=False, indent=1, default=str)


def fracao_sobreposta(fp: gpd.GeoDataFrame, camada: gpd.GeoDataFrame, col_filtro: str | None = None,
                      valor_filtro=None) -> pd.DataFrame:
    """Para cada operação de fp, área (ha) e fração da gleba coberta pela união da camada."""
    cam = camada if col_filtro is None else camada[camada[col_filtro] == valor_filtro]
    if cam.empty:
        return pd.DataFrame(columns=["idx", "inter_ha", "frac"])
    tree = shapely.STRtree(cam.geometry.values)
    i_fp, i_cam = tree.query(fp.geometry.values, predicate="intersects")
    if len(i_fp) == 0:
        return pd.DataFrame(columns=["idx", "inter_ha", "frac"])
    pares = pd.DataFrame({"i": i_fp, "j": i_cam})
    out = []
    for i, grp in pares.groupby("i"):
        g = fp.geometry.values[i]
        u = shapely.union_all(cam.geometry.values[grp.j.values])
        a = shapely.area(shapely.intersection(g, u))
        out.append((fp.index[i], a / 1e4, a / max(shapely.area(g), 1e-9)))
    return pd.DataFrame(out, columns=["idx", "inter_ha", "frac"])


def fmt_top(df: pd.DataFrame, cols: list[str], n: int = 10) -> pd.DataFrame:
    t = df[cols].head(n).copy()
    if "ref_bacen" in t:
        t["ref_bacen"] = t["ref_bacen"].astype(str)
    return t
