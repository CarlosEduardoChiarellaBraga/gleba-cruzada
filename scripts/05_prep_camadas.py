"""Etapa 05 — prepara camadas para os cruzamentos (tudo em EPSG:5880, geometrias válidas).

Saídas em data/processed/ (GeoParquet, CRS métrico SIRGAS 2000 / Brazil Polyconic):
  op_footprint.parquet  1 linha por operação com gleba: união das glebas + atributos da operação
  car_go.parquet        imóveis do SICAR (código normalizado sem separadores)
  municipios_go.parquet malha IBGE 2024
  ti_go.parquet         terras indígenas (FUNAI)
  uc_go.parquet         unidades de conservação (CNUC) com classe PI / RPPN / APA / US
  agua_go.parquet       massas d'água (ANA)
  embargo_go.parquet    embargos IBAMA em GO (polígono ou ponto) — SEM nome/CPF
e outputs/validade_geometrias.csv (quantas geometrias inválidas havia em cada camada).
"""
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CRS_GEO, CRS_METRICO, OUT, PROC, RAW  # noqa: E402

validade = []


def limpa(gdf: gpd.GeoDataFrame, nome: str) -> gpd.GeoDataFrame:
    """Remove nulas/vazias, corrige inválidas (make_valid) e registra contagens."""
    n0 = len(gdf)
    nulas = int(gdf.geometry.isna().sum() + gdf.geometry.is_empty.sum())
    gdf = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty].copy()
    inval = ~gdf.geometry.is_valid
    n_inv = int(inval.sum())
    n_desc = 0
    if n_inv:
        fixed = []
        for g in gdf.loc[inval, "geometry"].values:
            try:
                fixed.append(shapely.make_valid(g))
            except shapely.errors.GEOSException:
                fixed.append(None)  # irrecuperável (ex.: coordenada infinita)
        gdf.loc[inval, "geometry"] = fixed
        n_desc = int(sum(f is None for f in fixed))
        gdf = gdf[~gdf.geometry.isna()].copy()
        # make_valid pode gerar GeometryCollection com linhas/pontos: manter só a parte areal
        gdf["geometry"] = [so_poligonos(g) for g in gdf.geometry.values]
    validade.append(dict(camada=nome, feicoes=n0, nulas_ou_vazias=nulas, invalidas_corrigidas=n_inv - n_desc,
                         descartadas=n_desc,
                         pct_invalidas=round(100 * n_inv / max(n0, 1), 3)))
    print(f"[{nome}] {n0:,} feições; nulas/vazias {nulas:,}; inválidas corrigidas {n_inv:,}", flush=True)
    return gdf


def so_poligonos(g):
    if g is None or g.geom_type in ("Polygon", "MultiPolygon", "Point", "MultiPoint"):
        return g
    if g.geom_type == "GeometryCollection":
        polys = [p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
        return shapely.union_all(polys) if polys else None
    return g


def fix_txt(s):
    return s.encode("latin1").decode("utf-8", "replace") if isinstance(s, str) else s


# ------------------------------------------------------------------ municípios
mun = gpd.read_file(RAW / "ibge" / "GO_Municipios_2024" / "GO_Municipios_2024.shp").to_crs(CRS_METRICO)
mun = limpa(mun[["CD_MUN", "NM_MUN", "AREA_KM2", "geometry"]], "IBGE municípios GO")
mun.to_parquet(PROC / "municipios_go.parquet")
go = mun.union_all()

# ------------------------------------------------------------------ glebas -> footprint por operação
gl = gpd.read_parquet(PROC / "glebas_go.parquet").set_crs(CRS_GEO, allow_override=True).to_crs(CRS_METRICO)
gl = limpa(gl, "Sicor glebas")
gl["area_gleba_ha"] = gl.area / 1e4
fp = (gl.groupby(["ref_bacen", "nu_ordem"])
        .agg(n_glebas=("nu_indice", "size"), soma_area_glebas_ha=("area_gleba_ha", "sum"),
             geometry=("geometry", lambda s: shapely.union_all(s.values)))
        .reset_index())
fp = gpd.GeoDataFrame(fp, geometry="geometry", crs=CRS_METRICO)
fp["area_ha"] = fp.area / 1e4
ops = duckdb.sql(f"SELECT * FROM '{PROC / 'operacoes_go.parquet'}'").df()
fp = fp.merge(ops, on=["ref_bacen", "nu_ordem"], how="left")
car_op = duckdb.sql(f"""SELECT ref_bacen, nu_ordem, list(DISTINCT upper(cd_car)) AS cars
                        FROM '{PROC / 'propriedades_go.parquet'}' WHERE cd_car IS NOT NULL GROUP BY ALL""").df()
fp = fp.merge(car_op, on=["ref_bacen", "nu_ordem"], how="left")
fp.to_parquet(PROC / "op_footprint.parquet")
print(f"op_footprint: {len(fp):,} operações com gleba", flush=True)

# ------------------------------------------------------------------ CAR (SICAR)
car = pyogrio.read_dataframe(RAW / "car" / "AREA_IMOVEL" / "AREA_IMOVEL_1.shp", encoding="ISO-8859-1",
                             columns=["cod_imovel", "num_area", "ind_status", "ind_tipo", "des_condic",
                                      "municipio", "dat_criaca", "dat_atuali"], use_arrow=True)
car = car.to_crs(CRS_METRICO)
car = limpa(car, "SICAR área do imóvel GO")
car["cod_norm"] = car.cod_imovel.str.replace(r"[-.\s]", "", regex=True).str.upper()
car["dat_criaca"] = pd.to_datetime(car.dat_criaca, format="%d/%m/%Y", errors="coerce")
car["dat_atuali"] = pd.to_datetime(car.dat_atuali, format="%d/%m/%Y", errors="coerce")
car["area_calc_ha"] = car.area / 1e4
dup = car.cod_norm.duplicated(keep=False).sum()
print(f"  CAR: códigos repetidos (multipartes em linhas separadas): {dup:,}")
car.to_parquet(PROC / "car_go.parquet")

# ------------------------------------------------------------------ terras indígenas
ti = gpd.read_file(RAW / "funai" / "tis_poligonais_go.geojson").to_crs(CRS_METRICO)
ti = limpa(ti, "FUNAI terras indígenas")
ti = ti[ti.intersects(go)][["terrai_nome", "fase_ti", "modalidade_ti", "uf_sigla", "geometry"]]
ti.to_parquet(PROC / "ti_go.parquet")

# ------------------------------------------------------------------ unidades de conservação
uc = gpd.read_file(RAW / "cnuc" / "shp" / "cnuc_2025_08.shp", encoding="latin1")
for c in ["nome_uc", "categoria", "grupo", "esfera", "situacao"]:
    uc[c] = uc[c].map(fix_txt)
uc = uc.to_crs(CRS_METRICO)
uc = limpa(uc, "CNUC unidades de conservação")
uc = uc[uc.intersects(go.buffer(20_000))]


def classe_uc(r):
    if r.grupo == "Proteção Integral":
        return "PI"
    if "Particular" in str(r.categoria):
        return "RPPN"
    if "Proteção Ambiental" in str(r.categoria):
        return "APA"
    return "US-outras"


uc["classe"] = uc.apply(classe_uc, axis=1)
uc[["cd_cnuc", "nome_uc", "categoria", "grupo", "esfera", "cria_ano", "situacao", "classe", "geometry"]].to_parquet(PROC / "uc_go.parquet")

# ------------------------------------------------------------------ massas d'água
ag = gpd.read_file(RAW / "ana" / "massa_dagua_go.geojson").to_crs(CRS_METRICO)
ag = limpa(ag, "ANA massas d'água")
ag["area_ha"] = ag.area / 1e4
ag = ag[ag.intersects(go.buffer(5_000))]
ag["grande"] = (ag.area_ha >= 100) | (ag.detipomass == "Natural")
ag[["nmoriginal", "detipomass", "area_ha", "grande", "geometry"]].to_parquet(PROC / "agua_go.parquet")

# ------------------------------------------------------------------ embargos IBAMA (sem nome/CPF)
emb = duckdb.sql(f"""
SELECT SEQ_TAD AS seq_tad, NUM_TAD AS num_tad, SIT_CANCELADO AS sit_cancelado,
       DES_STATUS_FORMULARIO AS status_formulario,
       TRY_CAST(DAT_EMBARGO AS TIMESTAMP) AS dat_embargo,
       SIT_DESEMBARGO AS sit_desembargo, TIPO_DESEMBARGO AS tipo_desembargo,
       TRY_CAST(DAT_DESEMBARGO AS TIMESTAMP) AS dat_desembargo,
       COD_MUNICIPIO AS cod_municipio, TIPO_AREA AS tipo_area,
       TRY_CAST(replace(QTD_AREA_EMBARGADA, ',', '.') AS DOUBLE) AS qtd_area_embargada_ha,
       TRY_CAST(replace(NUM_LONGITUDE_TAD, ',', '.') AS DOUBLE) AS lon,
       TRY_CAST(replace(NUM_LATITUDE_TAD, ',', '.') AS DOUBLE) AS lat,
       nullif(GEOM_AREA_EMBARGADA, '') AS wkt
       -- NOME_EMBARGADO, CPF_CNPJ_EMBARGADO, NOME_IMOVEL e textos livres descartados de propósito
FROM read_csv('{RAW / 'ibama' / 'termo_de_embargo.csv'}', delim=';', header=true, all_varchar=true,
              quote='"', max_line_size=50000000)
WHERE UF = 'GO'
""").df()
hoje = pd.Timestamp("2026-11-15")
for c in ["dat_embargo", "dat_desembargo"]:
    emb.loc[emb[c] > hoje, c] = pd.NaT  # datas digitadas no futuro (ex.: 2925) -> inválidas
wkt_arr = np.array([w if isinstance(w, str) else None for w in emb.wkt], dtype=object)
poly = shapely.from_wkt(wkt_arr, on_invalid="ignore")
pts = shapely.points(emb.lon.values, emb.lat.values)
plaus = (emb.lon.between(-54, -45) & emb.lat.between(-20.5, -12)).to_numpy()  # faixa plausível p/ GO
print(f"  embargos com ponto fora da faixa plausível (descartados se sem polígono): {(~plaus).sum():,}")
pts = np.where(plaus, pts, None)
emb["geom_tipo"] = np.where(~shapely.is_missing(poly), "poligono", np.where(pts != None, "ponto", "sem"))  # noqa: E711
geom = np.where(~shapely.is_missing(poly), poly, pts)
emb = gpd.GeoDataFrame(emb.drop(columns=["wkt"]), geometry=list(geom), crs=CRS_GEO)
emb = emb[emb.geom_tipo != "sem"].to_crs(CRS_METRICO)
emb = limpa(emb, "IBAMA embargos GO")
print("  embargos por tipo de geometria:", emb.geom_tipo.value_counts().to_dict())
emb.to_parquet(PROC / "embargo_go.parquet")

pd.DataFrame(validade).to_csv(OUT / "validade_geometrias.csv", index=False)
print(pd.DataFrame(validade).to_string(index=False))
