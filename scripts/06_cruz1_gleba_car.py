"""Cruzamento 1 — Gleba × CAR informado.

Para cada operação com gleba e CAR:
  - sobreposição = área(gleba ∩ CAR informado) / área(gleba)
  - distância entre centroides (km) e distância gleba→CAR (0 se tocam)
  - qual imóvel do SICAR cobre a maior parte da gleba (pode ser outro CAR)
Sinal: sobreposição < 50% ou centroides a mais de 5 km.
Categorias (sem sinal → "ok"):
  erro de cadastro provável: CAR não existe no SICAR; gleba majoritariamente num CAR VIZINHO
                             (encosta no informado, < 100 m); CAR informado de outro município
  indício: gleba fora de qualquer CAR; gleba em outro CAR não vizinho; CAR a mais de 5 km
Atenuante registrado: CAR hoje cancelado/retificado (o SICAR baixado é retrato atual, não da data
do contrato).
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import PROC, RES, banco, fmt_top, load_fp, resumo, salva_resumo  # noqa: E402

LIM_SOBREP = 0.5
LIM_DIST_KM = 5.0
VIZINHO_M = 100.0

fp = load_fp()
fp = fp[fp.cars.notna()].reset_index(drop=True)
print(f"operações com gleba e CAR: {len(fp):,}")

car = gpd.read_parquet(PROC / "car_go.parquet")
# códigos repetidos = multipartes do mesmo imóvel -> dissolve
car_d = car.dissolve(by="cod_norm", aggfunc={"ind_status": "first", "ind_tipo": "first", "num_area": "first",
                                             "dat_atuali": "max", "dat_criaca": "min", "des_condic": "first"})
car_d = car_d.reset_index()
idx_car = pd.Series(range(len(car_d)), index=car_d.cod_norm)
print(f"imóveis SICAR (dissolvidos): {len(car_d):,}")

# ---------------------------------------------------------------- CAR informado
linhas = []
geoms_car = car_d.geometry.values
for k, r in enumerate(fp.itertuples()):
    cods = [c for c in r.cars if isinstance(c, str)]
    achados = [idx_car[c] for c in cods if c in idx_car.index]
    rec = dict(k=k, n_car_inf=len(cods), n_car_achado=len(achados))
    g = r.geometry
    if achados:
        u = shapely.union_all(geoms_car[achados])
        rec["sobrep"] = shapely.area(shapely.intersection(g, u)) / shapely.area(g)
        rec["dist_centroides_km"] = shapely.distance(shapely.centroid(g), shapely.centroid(u)) / 1e3
        rec["dist_borda_km"] = shapely.distance(g, u) / 1e3
        st = car_d.iloc[achados]
        rec["car_status"] = ",".join(sorted(set(st.ind_status)))
        rec["car_area_ha"] = float(st.num_area.sum())
        rec["car_atualizado_apos_contrato"] = bool((st.dat_atuali > pd.Timestamp(r.dt_emissao)).any())
        rec["car_criado_apos_contrato"] = bool((st.dat_criaca > pd.Timestamp(r.dt_emissao)).all())
    rec["car_mun_difere"] = bool(r.cd_ibge_municipio and all(c[2:9] != r.cd_ibge_municipio for c in cods))
    linhas.append(rec)
m = pd.DataFrame(linhas)
fp = pd.concat([fp, m.drop(columns="k")], axis=1)

# ---------------------------------------------------------------- melhor CAR (qualquer) para a gleba
tree = shapely.STRtree(geoms_car)
i_fp, i_car = tree.query(fp.geometry.values, predicate="intersects")
inter = shapely.area(shapely.intersection(fp.geometry.values[i_fp], geoms_car[i_car]))
pares = pd.DataFrame({"i": i_fp, "j": i_car, "frac": inter / fp.area.values[i_fp]})
best = pares.sort_values("frac", ascending=False).drop_duplicates("i").set_index("i")
fp["melhor_car"] = pd.Series(car_d.cod_norm.values[best.j.values], index=best.index)
fp["melhor_car_frac"] = best.frac
fp["melhor_car_frac"] = fp.melhor_car_frac.fillna(0.0)
fp["n_car_sobrepostos"] = pares[pares.frac > 0.01].groupby("i").size().reindex(fp.index).fillna(0).astype(int)


def vizinho(r) -> bool:
    """Melhor CAR encosta (≤100 m) no CAR informado?"""
    if not isinstance(r.melhor_car, str) or r.n_car_achado == 0:
        return False
    inf = shapely.union_all(geoms_car[[idx_car[c] for c in r.cars if c in idx_car.index]])
    return shapely.distance(geoms_car[idx_car[r.melhor_car]], inf) <= VIZINHO_M


# ---------------------------------------------------------------- classificação
sinal = (fp.n_car_achado == 0) | (fp.sobrep.fillna(0) < LIM_SOBREP) | (fp.dist_centroides_km.fillna(0) > LIM_DIST_KM)
fp["sinal"] = sinal
fp["categoria"] = "ok"
fp["tipo"] = "ok"
s = fp.sinal
viz = pd.Series(False, index=fp.index)
viz[s] = fp[s].apply(vizinho, axis=1)
fp["melhor_car_vizinho"] = viz

c = fp.categoria.copy()
t = fp.tipo.copy()
c[s & (fp.n_car_achado == 0)] = "CAR informado não existe no SICAR"
t[s & (fp.n_car_achado == 0)] = "erro de cadastro provável"
ok_car = s & (fp.n_car_achado > 0)
baixa = ok_car & (fp.sobrep < LIM_SOBREP)
em_outro = baixa & (fp.melhor_car_frac >= 0.5)
c[em_outro & viz] = "gleba em CAR vizinho ao informado"
t[em_outro & viz] = "erro de cadastro provável"
c[em_outro & ~viz] = "gleba em outro CAR (não vizinho)"
t[em_outro & ~viz] = "indício"
fora = baixa & (fp.melhor_car_frac < 0.5)
c[fora] = "gleba fora de qualquer CAR (<50% coberta)"
t[fora] = "indício"
longe = ok_car & (fp.sobrep >= LIM_SOBREP) & (fp.dist_centroides_km > LIM_DIST_KM)
c[longe] = "sobreposição ok mas centroides > 5 km (CAR grande)"
t[longe] = "ruído provável"
# CAR de outro município no código: rebaixa para erro de cadastro quando gleba está fora
c[baixa & fp.car_mun_difere & ~em_outro] = "CAR de outro município e gleba fora dele"
t[baixa & fp.car_mun_difere & ~em_outro] = "erro de cadastro provável"
fp["categoria"], fp["tipo"] = c, t
fp["banco"] = fp.is_bb.map(banco)

# força do sinal: quanto menos sobreposição e mais distante, mais forte; pondera valor
fp["forca"] = (1 - fp.sobrep.fillna(0)) * (1 + fp.dist_borda_km.fillna(0)) * np.log10(1 + fp.vl_parc_credito)

# ---------------------------------------------------------------- saídas
res = []
res.append(resumo(fp, fp.sinal, "1. Gleba × CAR — qualquer sinal (sobrep<50% ou >5 km)"))
for tp in ["indício", "erro de cadastro provável", "ruído provável"]:
    res.append(resumo(fp, fp.tipo == tp, f"1. Gleba × CAR — {tp}"))
for cat in sorted(fp.categoria.unique()):
    if cat != "ok":
        res.append(resumo(fp, fp.categoria == cat, f"1. — {cat}"))
res.append(resumo(fp, fp.car_status.fillna("").str.contains("CA"), "1. (contexto) CAR informado hoje cancelado"))
salva_resumo("cruz1", res)

cols = ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "vl_parc_credito", "area_ha",
        "sobrep", "dist_centroides_km", "dist_borda_km", "melhor_car_frac", "melhor_car_vizinho",
        "car_status", "car_atualizado_apos_contrato", "categoria", "tipo", "forca"]
fp_out = fp.drop(columns="geometry")
fp_out[cols + ["cars", "melhor_car", "cd_ibge_municipio"]].to_parquet(PROC / "cruz1_ops.parquet")
casos = fp_out[fp_out.tipo == "indício"].sort_values("forca", ascending=False)
casos[cols + ["cd_ibge_municipio"]].to_csv(RES / "cruz1_casos_indicio.csv", index=False)
fmt_top(casos, cols[:-1]).to_csv(RES / "cruz1_top10.csv", index=False)

print(pd.DataFrame(res)[["cruzamento", "elegiveis", "disparam", "pct_elegiveis", "bb_pct", "demais_pct"]].to_string())
print("\nsobreposição (quantis):", fp.sobrep.quantile([.01, .05, .1, .25, .5]).round(3).to_dict())
print("CAR atualizado após contrato:", fp.car_atualizado_apos_contrato.mean().round(3))
