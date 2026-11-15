"""Padrões mais próximos de engano (não só falha de controle), com foco no BB.
A) custeio agrícola ou correção de solo: mesma terra (glebas quase idênticas), mesma safra, mesmo produto e mesmo ciclo,
   com área declarada somada > 1,3× a terra (cada contrato declara a terra inteira).
A2) pecuária: compra de animais financiada na mesma terra/safra somando 3–30 UA/ha, gleba ≥ 10 ha (implausível em pasto).
B) 2+ contratos de investimento no teto (R$ 480–500 mil) na mesma terra e safra (possível fracionamento).
Saídas: data/processed/{clusters_mesma_area,mesma_terra_mesmo_produto,fracionamento_teto}.parquet,
        outputs/revisao/bb_padroes_engano.csv"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent))
import geopandas as gpd, pandas as pd, numpy as np, shapely
from common import PROC, OUT

R = OUT / "revisao"; R.mkdir(parents=True, exist_ok=True)

def comps(n, i, j):
    par = list(range(n))
    def fd(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for a, b in zip(i, j):
        ra, rb = fd(a), fd(b)
        if ra != rb: par[ra] = rb
    return np.array([fd(a) for a in range(n)])

f = gpd.read_parquet(PROC / "op_footprint.parquet").reset_index(drop=True)
f["key"] = f.ref_bacen.astype(str) + "/" + f.nu_ordem.astype(str)
f["car"] = f.cars.apply(lambda x: "+".join(sorted(x)) if x is not None and len(x) else None)  # conjunto de CARs
pec = f.produto.str.contains("BOVINO", na=False) & f.unidade_medida.str.contains("Unidade Animal|Quantidade", na=False)
f["ua"] = np.where(pec, f.vl_quantidade * np.where(f.unidade_medida.str.startswith("Quant"), 0.75, 1.0), np.nan)

# 1) agrupa operações da mesma safra com glebas quase idênticas: interseção > 80% da MAIOR gleba
#    (usar a menor deixava encadear glebas disjuntas contidas numa gleba grande da mesma fazenda)
partes = []
for s, g in f.groupby("safra"):
    g = g.reset_index(drop=True); geo = g.geometry.values
    i, j = shapely.STRtree(geo).query(geo, predicate="intersects"); m = i < j; i, j = i[m], j[m]
    inter = shapely.area(shapely.intersection(geo[i], geo[j]))
    k = inter / np.maximum(shapely.area(geo[i]), shapely.area(geo[j])) > 0.8
    g["cluster"] = s + "#" + pd.Series(comps(len(g), i[k], j[k])).astype(str)
    partes.append(g)
g = pd.concat(partes); sz = g.groupby("cluster").size(); g = g[g.cluster.isin(sz[sz > 1].index)]

def agg(d):
    return pd.Series(dict(safra=d.safra.iloc[0], n_ops=len(d), n_cars=d.car.nunique(), n_ifs=d.nome_if.nunique(),
        ifs=" | ".join(sorted(set(d.nome_if.str[:22]))), bb_ops=int(d.is_bb.sum()), valor=d.vl_parc_credito.sum(),
        area_ha=shapely.union_all(d.geometry.values).area / 1e4, produtos=", ".join(sorted(set(d.produto)))[:40],
        ua_custeio=d.loc[d.finalidade == "Custeio", "ua"].sum(), ua_invest=d.loc[d.finalidade == "Investimento", "ua"].sum(),
        ops=" ".join(d.key)))
C = g.groupby("cluster").apply(agg)
C["ua_ha"] = C[["ua_custeio", "ua_invest"]].max(axis=1) / C.area_ha
C.to_parquet(PROC / "clusters_mesma_area.parquet")
memb = g[["key", "cluster"]]

# 2) padrões A e A2
rows = []
for cl, r in C.iterrows():
    d = f[f.key.isin(r.ops.split())]
    for (fin, prod), h in d.groupby(["finalidade", "produto"]):
        if len(h) >= 2 and h.is_bb.any() and h.ref_bacen.nunique() >= 2:
            rows.append(dict(cluster=cl, safra=r.safra, finalidade=fin, produto=prod, n_ops=len(h), n_cars=h.car.nunique(),
                n_ifs=h.nome_if.nunique(), ifs=" | ".join(sorted(set(h.nome_if.str[:20]))), bb=int(h.is_bb.sum()),
                valor=h.vl_parc_credito.sum(), area_ha=r.area_ha, area_decl_soma=h.vl_area_informada.drop_duplicates().sum()
                    if h.ref_bacen.nunique() < len(h) else h.vl_area_informada.sum(),
                ua=h.ua.sum(), pecuaria=bool(h.ua.notna().any()), agricola=not str(h.atividade.iloc[0]).startswith("Pecu"),
                datas=", ".join(sorted(pd.to_datetime(h.dt_emissao).dt.strftime("%Y-%m-%d"))),
                plantio=", ".join(sorted(set(pd.to_datetime(h.dt_inic_plantio).dt.strftime("%m/%y").dropna()))),
                ops=" ".join(h.key)))
X = pd.DataFrame(rows); X["decl_sobre_area"] = X.area_decl_soma / X.area_ha; X["ua_ha"] = X.ua / X.area_ha
X.to_parquet(PROC / "mesma_terra_mesmo_produto.parquet")
# só itens financiados "por área, uma vez por ciclo": custeio agrícola e correção de solo
# (benfeitorias, irrigação, granjas etc. somam vários investimentos legítimos sobre a mesma área)
por_area = ((X.finalidade == "Custeio") & X.agricola) | (X.produto == "CORREÇÃO INTENSIVA DO SOLO")
A = X[por_area & (X.decl_sobre_area > 1.3) & ~X.plantio.str.contains(",")]
# > 30 UA/ha ou gleba < 10 ha é quase sempre erro de unidade/desenho, não sinal
A2 = X[X.pecuaria & (X.finalidade == "Investimento") & X.ua_ha.between(3, 30) & (X.area_ha >= 10)]

# 3) padrão B
h = f.merge(memb, on="key")
h = h[(h.finalidade == "Investimento") & h.vl_parc_credito.between(480e3, 500e3)]
T = h.groupby("cluster").agg(n_contr=("ref_bacen", "nunique"), n_cars=("car", "nunique"), bb=("is_bb", "sum"),
    ifs=("nome_if", lambda x: " | ".join(sorted(set(x.str[:18])))), valor=("vl_parc_credito", "sum"),
    area_ha=("area_ha", "max"), mun=("cd_ibge_municipio", "first"), ops=("key", " ".join))
T = T[T.n_contr >= 2]; T.to_parquet(PROC / "fracionamento_teto.parquet")
base = f[(f.finalidade == "Investimento") & f.vl_parc_credito.between(480e3, 500e3)].drop_duplicates("ref_bacen") \
        .merge(memb, on="key", how="left")
taxa = base.groupby("is_bb").apply(lambda d: round(100 * d.cluster.isin(T.index).mean(), 1))
print("contratos no teto que estão em grupo fracionado (%):", taxa.to_dict())

# 4) lista para revisão
c1 = pd.read_parquet(PROC / "cruz1_ops.parquet"); c1["key"] = c1.ref_bacen.astype(str) + "/" + c1.nu_ordem.astype(str)
lst = pd.concat([A.assign(padrao="A: lavoura/solo — mesma terra financiada 2x no mesmo ciclo")[["cluster", "ops", "padrao"]],
                 A2.assign(padrao="A2: pecuária — gado financiado acima de 3 UA/ha na mesma terra")[["cluster", "ops", "padrao"]],
                 T[T.bb > 0].reset_index().assign(padrao="B: 2+ contratos no teto de R$500k na mesma terra/safra")[["cluster", "ops", "padrao"]]])
lst = lst.assign(key=lst.ops.str.split()).explode("key").drop(columns="ops").rename(columns={"cluster": "grupo"})
out = lst.merge(f[["key", "nome_if", "safra", "dt_emissao", "finalidade", "modalidade", "produto", "vl_parc_credito",
                   "vl_area_informada", "vl_quantidade", "unidade_medida", "area_ha", "cd_ibge_municipio", "car", "geometry"]], on="key")
out = out.merge(c1[["key", "categoria", "sobrep"]], on="key", how="left").rename(columns={"categoria": "gleba_vs_car"})
p = gpd.GeoSeries(out.geometry, crs=f.crs).to_crs(4326).representative_point(); out["lat"] = p.y.round(5); out["lon"] = p.x.round(5)
out["google_maps"] = [f"https://www.google.com/maps/@{a},{o},1500m/data=!3m1!1e3" for a, o in zip(out.lat, out.lon)]
out["dt_emissao"] = pd.to_datetime(out.dt_emissao).dt.date
out["valor_grupo"] = out.groupby("grupo").vl_parc_credito.transform("sum")
out = out.drop(columns="geometry").sort_values(["padrao", "valor_grupo", "grupo", "dt_emissao"], ascending=[True, False, True, True])
out.to_csv(R / "bb_padroes_engano.csv", index=False)
print(out.groupby("padrao").agg(grupos=("grupo", "nunique"), ops=("key", "size")))
