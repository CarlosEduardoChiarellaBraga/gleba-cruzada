"""Etapa 04 — Passo 0: reconhecimento do Sicor no recorte (GO, safras 2021/22–2024/25).

Gera:
  outputs/reconhecimento.md
  outputs/passo0_*.csv
  outputs/maps/passo0_glebas_aleatorias.png
"""
import gzip
import json
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import shapely

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CRS_GEO, CRS_METRICO, OUT, PROC, RAW  # noqa: E402

S = RAW / "sicor"
(OUT / "maps").mkdir(parents=True, exist_ok=True)
md: list[str] = []
P = lambda *a: md.append(" ".join(str(x) for x in a))  # noqa: E731

# Cores (paleta de referência do skill de dataviz)
AZUL, LARANJA, VERMELHO = "#2a78d6", "#eb6834", "#e34948"
CINZA_LINHA, CINZA_FUNDO, TXT2 = "#c9c8c2", "#f3f2ee", "#52514e"

con = duckdb.connect()
con.sql("INSTALL spatial; LOAD spatial;")
con.sql(f"CREATE VIEW ops AS SELECT * FROM '{PROC / 'operacoes_go.parquet'}'")
con.sql(f"CREATE VIEW prop AS SELECT * FROM '{PROC / 'propriedades_go.parquet'}'")
con.sql(f"CREATE VIEW gl AS SELECT ref_bacen, nu_ordem, nu_indice, wkt_tipo FROM '{PROC / 'glebas_go.parquet'}'")


def tabela(df: pd.DataFrame, floatfmt=None) -> str:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else (floatfmt or "{:,.1f}").format(v))
        elif pd.api.types.is_integer_dtype(df[c]):
            df[c] = df[c].map(lambda v: f"{v:,}")
    return df.to_markdown(index=False)


# =========================================================== 1. arquivos/colunas
P("# Passo 0 — Reconhecimento (Sicor × Goiás, safras 2021/22–2024/25)\n")
P("## 1. Arquivos do Sicor disponíveis\n")
pag = json.dumps(json.load(open(S / "pagina_tabelas.json")), ensure_ascii=False)
import re  # noqa: E402

urls = sorted(set(re.findall(r"/htms/sicor/DadosBrutos/([A-Za-z0-9_]+?)(?:_\d{4}(?:_\d{2})?(?:_\d{4})?)?\.(?:gz|csv)", pag)))
P("Fonte: <https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro> "
  "(microdados em `/htms/sicor/DadosBrutos/`). Famílias de arquivo publicadas:\n")
P(", ".join(f"`{u}`" for u in urls if not u.startswith("recor")) + "\n")
P("Particionados por ano (2013–2026): `SICOR_OPERACAO_BASICA_ESTADO_AAAA`, `sicor_glebas_wkt_AAAA`, "
  "`SICOR_SALDOS_AAAA`. O ano do arquivo = ano de `DT_EMISSAO` (verificado). "
  "Usados aqui: operações e glebas 2021–2025, `SICOR_PROPRIEDADES`, `SICOR_COMPLEMENTO_OPERACAO_BASICA`, "
  "`SICOR_LISTA_IFS` e dicionários (`Empreendimento`, `Programa`).\n")

P("### Colunas reais (cabeçalho dos arquivos baixados)\n")
for f in ["SICOR_OPERACAO_BASICA_ESTADO_2023.gz", "sicor_glebas_wkt_2023.gz", "SICOR_PROPRIEDADES.gz",
          "SICOR_COMPLEMENTO_OPERACAO_BASICA.gz", "SICOR_LISTA_IFS.csv", "Empreendimento.csv"]:
    op = gzip.open if f.endswith(".gz") else open
    with op(S / f, "rt", encoding="latin-1") as fh:
        cols = fh.readline().strip().lstrip("#").split(";")
    P(f"- **{f}** ({len(cols)}): " + ", ".join(f"`{c}`" for c in cols))
P("\nChave de operação: (`REF_BACEN`, `NU_ORDEM`); `REF_BACEN` é mascarado. Gleba: + `NU_INDICE`. "
  "Município vem só do complemento (`CD_IBGE_MUNICIPIO`). Finalidade/produto vêm do dicionário "
  "`Empreendimento` via `CD_EMPREENDIMENTO`. Segundo o manual, "
  "`VL_AREA_FINANC = VL_AREA_INFORMADA × VL_PARC_CREDITO / (VL_PARC_CREDITO + VL_REC_PROPRIO)` — "
  "a área comparável com a gleba é `VL_AREA_INFORMADA`. `CD_CNPJ_CPF` de propriedades **não** foi "
  "carregado.\n")

# =========================================================== 2. tamanho do recorte
P("## 2. Tamanho do recorte\n")
rec = con.sql("""
SELECT safra, finalidade,
       count(*) AS operacoes,
       count(*) FILTER (WHERE is_bb) AS op_bb,
       round(100.0 * count(*) FILTER (WHERE is_bb) / count(*), 1) AS pct_bb,
       sum(vl_parc_credito) / 1e9 AS valor_rs_bi,
       sum(vl_parc_credito) FILTER (WHERE is_bb) / 1e9 AS valor_bb_rs_bi
FROM ops GROUP BY ALL ORDER BY safra, finalidade
""").df()
tot = con.sql("""SELECT count(*) n, count(*) FILTER (WHERE is_bb) bb, sum(vl_parc_credito)/1e9 v,
                 count(*) FILTER (WHERE cd_ibge_municipio IS NULL) sem_mun,
                 count(*) FILTER (WHERE cd_ibge_municipio NOT LIKE '52%') mun_fora_go,
                 count(DISTINCT cnpj_if) n_if FROM ops""").fetchall()[0]
P(tabela(rec, "{:,.2f}"), "\n")
P(f"**Total: {tot[0]:,} operações**, R$ {tot[2]:,.1f} bi; BB = {tot[1]:,} ({100*tot[1]/tot[0]:.1f}%); "
  f"{tot[5]} instituições. Sem município no complemento: {tot[3]:,}; município fora de GO "
  f"(apesar de `CD_ESTADO='GO'`): {tot[4]:,}.\n")
rec.to_csv(OUT / "passo0_recorte.csv", index=False)

top_if = con.sql("""SELECT coalesce(nome_if, cnpj_if) AS instituicao, count(*) n,
                    round(100.0*count(*)/sum(count(*)) over (), 1) pct, sum(vl_parc_credito)/1e9 valor_rs_bi
                    FROM ops GROUP BY ALL ORDER BY n DESC LIMIT 8""").df()
P("Maiores instituições no recorte:\n")
P(tabela(top_if, "{:,.2f}"), "\n")

# =========================================================== 3. cobertura
P("## 3. Cobertura de localização (gleba) e de CAR\n")
con.sql("""
CREATE TEMP TABLE cov AS
SELECT o.ref_bacen, o.nu_ordem, o.safra, o.finalidade, o.is_bb, o.vl_parc_credito,
       g.n_glebas, g.n_poly, p.n_car, p.n_sncr
FROM ops o
LEFT JOIN (SELECT ref_bacen, nu_ordem, count(*) n_glebas,
                  count(*) FILTER (WHERE wkt_tipo IN ('POLYGON','MULTIPOLYGON')) n_poly
           FROM gl GROUP BY ALL) g USING (ref_bacen, nu_ordem)
LEFT JOIN (SELECT ref_bacen, nu_ordem, count(DISTINCT cd_car) n_car, count(DISTINCT cd_sncr) n_sncr
           FROM prop GROUP BY ALL) p USING (ref_bacen, nu_ordem)
""")
cov_sql = """
SELECT {g} count(*) operacoes,
  round(100.0*count(*) FILTER (WHERE n_glebas>0)/count(*),1) AS pct_com_gleba,
  round(100.0*count(*) FILTER (WHERE n_poly>0)/count(*),1) AS pct_com_poligono,
  round(100.0*count(*) FILTER (WHERE n_glebas>0 AND coalesce(n_poly,0)=0)/count(*),1) AS pct_so_ponto,
  round(100.0*count(*) FILTER (WHERE n_car>0)/count(*),1) AS pct_com_car,
  round(100.0*count(*) FILTER (WHERE n_poly>0 AND n_car>0)/count(*),1) AS pct_poligono_e_car,
  round(100.0*sum(vl_parc_credito) FILTER (WHERE n_glebas>0)/sum(vl_parc_credito),1) AS pct_valor_com_gleba
FROM cov {gb}"""
c_all = con.sql(cov_sql.format(g="'TOTAL' AS grupo,", gb="")).df()
c_fin = con.sql(cov_sql.format(g="finalidade AS grupo,", gb="GROUP BY ALL ORDER BY 1")).df()
c_bb = con.sql(cov_sql.format(g="CASE WHEN is_bb THEN 'BB' ELSE 'Demais' END AS grupo,", gb="GROUP BY ALL ORDER BY 1")).df()
c_saf = con.sql(cov_sql.format(g="safra AS grupo,", gb="GROUP BY ALL ORDER BY 1")).df()
c_fb = con.sql(cov_sql.format(g="finalidade || ' / ' || CASE WHEN is_bb THEN 'BB' ELSE 'Demais' END AS grupo,",
                              gb="GROUP BY ALL ORDER BY 1")).df()
cov = pd.concat([c_all, c_fin, c_bb, c_saf, c_fb])
P(tabela(cov), "\n")
cov.to_csv(OUT / "passo0_cobertura.csv", index=False)

dist = con.sql("""SELECT coalesce(n_glebas,0) AS glebas_por_operacao, count(*) n FROM cov
                  GROUP BY 1 ORDER BY 1""").df()
dist["faixa"] = pd.cut(dist.glebas_por_operacao, [-1, 0, 1, 2, 5, 10, 1e9],
                       labels=["0", "1", "2", "3–5", "6–10", ">10"])
P("Glebas por operação: " + ", ".join(f"{k}: {v:,}" for k, v in dist.groupby("faixa", observed=True).n.sum().items()) + "\n")
ncar = con.sql("SELECT coalesce(n_car,0) k, count(*) n FROM cov GROUP BY 1 ORDER BY 1").df()
P("CARs distintos por operação: " + ", ".join(f"{int(k) if k < 5 else '5+'}: {n:,}" for k, n in
  ncar.assign(k=ncar.k.clip(upper=5)).groupby("k").n.sum().items()) + "\n")

# No Sicor o CAR vem SEM hífens/pontos: UF(2) + IBGE(7) + hash(32) = 41 caracteres.
# No SICAR o mesmo código é escrito "GO-5218003-XXXX.XXXX....": normalizar antes de casar.
carfmt = con.sql("""
SELECT count(*) n,
  count(*) FILTER (WHERE regexp_full_match(cd_car, '[A-Z]{2}\\d{7}[0-9A-Fa-f]{32}')) AS formato_ok,
  count(*) FILTER (WHERE cd_car LIKE 'GO%') AS uf_go,
  count(*) FILTER (WHERE o.cd_ibge_municipio IS NOT NULL) AS com_mun,
  count(*) FILTER (WHERE o.cd_ibge_municipio IS NOT NULL AND substr(cd_car,3,7) = o.cd_ibge_municipio) AS mun_igual_op
FROM prop p JOIN ops o USING (ref_bacen, nu_ordem) WHERE cd_car IS NOT NULL
""").fetchall()[0]
P(f"Códigos CAR informados (linhas operação×CAR): {carfmt[0]:,}. Formato no Sicor: **sem hífens**, "
  f"`UF`+`IBGE7`+`HASH32` (41 caracteres) — {100*carfmt[1]/max(carfmt[0],1):.1f}% seguem esse padrão; "
  f"prefixo `GO`: {100*carfmt[2]/max(carfmt[0],1):.1f}%; município embutido no CAR = município da "
  f"operação (quando há município): {100*carfmt[4]/max(carfmt[3],1):.1f}%.\n")

# ------------------------------------------- viés de cobertura (quem tem localização?)
P("### Quem tem localização publicada? (viés de seleção)\n")
con.sql("CREATE TEMP VIEW cov2 AS SELECT o.*, c.n_glebas, c.n_car FROM ops o JOIN cov c USING (ref_bacen, nu_ordem)")
vies_sql = """SELECT {g} AS grupo, count(*) operacoes,
  round(100.0*count(*) FILTER (WHERE n_glebas>0)/count(*),1) pct_gleba,
  round(100.0*count(*) FILTER (WHERE n_car>0)/count(*),1) pct_car,
  round(100.0*count(cd_ibge_municipio)/count(*),1) pct_municipio
FROM cov2 GROUP BY 1 ORDER BY 1"""
v_cat = con.sql(vies_sql.format(g="""CASE cd_categ_emitente WHEN '2222' THEN '1 pequeno produtor'
            WHEN '3333' THEN '2 médio produtor' WHEN '4444' THEN '3 grande produtor' ELSE cd_categ_emitente END""")).df()
v_prog = con.sql(vies_sql.format(g="""CASE WHEN programa LIKE 'PRONAF%' THEN 'Pronaf' WHEN programa LIKE 'PRONAMP%'
            THEN 'Pronamp' WHEN cd_programa='0999' THEN 'Sem programa' ELSE 'Outros programas' END""")).df()
v_val = con.sql(vies_sql.format(g="""CASE WHEN vl_parc_credito<50e3 THEN 'a) < 50 mil' WHEN vl_parc_credito<200e3
            THEN 'b) 50–200 mil' WHEN vl_parc_credito<1e6 THEN 'c) 200 mil–1 mi' WHEN vl_parc_credito<5e6
            THEN 'd) 1–5 mi' ELSE 'e) > 5 mi' END""")).df()
v_prod = con.sql("""SELECT finalidade || ' · ' || produto AS grupo, count(*) operacoes,
  round(100.0*count(*) FILTER (WHERE n_glebas>0)/count(*),1) pct_gleba,
  round(sum(vl_parc_credito)/1e9,2) valor_rs_bi
FROM cov2 GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").df()
P("Por porte do produtor:\n"); P(tabela(v_cat), "\n")
P("Por programa:\n"); P(tabela(v_prog), "\n")
P("Por valor da operação:\n"); P(tabela(v_val), "\n")
P("Por produto (10 maiores em nº de operações):\n"); P(tabela(v_prod, "{:,.2f}"), "\n")
n_car_sem_gl = con.sql("SELECT count(*) FROM cov WHERE n_car>0 AND coalesce(n_glebas,0)=0").fetchall()[0][0]
n_gl_sem_car = con.sql("SELECT count(*) FROM cov WHERE n_glebas>0 AND coalesce(n_car,0)=0").fetchall()[0][0]
P(f"Gleba, CAR e município andam juntos: operações com gleba e sem CAR = {n_gl_sem_car:,}; com CAR e sem "
  f"gleba = {n_car_sem_gl:,} (sobretudo máquinas/investimentos sem área). Toda operação com gleba tem "
  "município no complemento. O BCB não documenta o critério de publicação; o padrão observado é que a "
  "localização aparece muito mais para pequenos produtores, Pronaf, pecuária e operações de menor valor. "
  "A família de arquivos `*_CONTRAT` (glebas como lista de pontos) cobre só contratos a partir de "
  "nov/2025 — fora do recorte — e não preenche essa lacuna.\n")

# =========================================================== 4. geometria
P("## 4. Formato e qualidade das glebas\n")
g = gpd.read_parquet(PROC / "glebas_go.parquet")
g = g.set_crs(CRS_GEO, allow_override=True)
n_gl = len(g)
tipos = g.wkt_tipo.value_counts()
nulas = int(g.geometry.isna().sum())
geom = g.geometry.values
vazias = int(shapely.is_empty(geom[~g.geometry.isna().values]).sum())
validas = shapely.is_valid(geom)
invalidas = int((~validas & ~g.geometry.isna().values).sum())
nverts = shapely.get_num_coordinates(geom)
P(f"- Glebas no recorte: **{n_gl:,}**. Tipo WKT: " + ", ".join(f"`{k}` {v:,}" for k, v in tipos.items()))
P(f"- WKT não interpretável: {nulas:,}; vazias: {vazias:,}; **inválidas (antes de make_valid): {invalidas:,} "
  f"({100*invalidas/n_gl:.2f}%)**")
P(f"- Vértices por gleba: mediana {np.nanmedian(nverts):.0f}, p05 {np.nanpercentile(nverts,5):.0f}, "
  f"p95 {np.nanpercentile(nverts,95):.0f}; glebas com ≤ 4 vértices (triângulo/ponto degenerado): "
  f"{int((nverts <= 4).sum()):,}")
P("- Coordenadas em graus decimais (lon lat), com Z = 0 (descartado). Assumido SIRGAS 2000 (EPSG:4674).")

g["geometry"] = shapely.make_valid(geom)
gm = g.to_crs(CRS_METRICO)
g["area_ha"] = gm.area.values / 1e4
cent = gm.geometry.centroid.to_crs(CRS_GEO)
g["cent_x"], g["cent_y"] = cent.x.values, cent.y.values

mun = gpd.read_file(RAW / "ibge" / "GO_Municipios_2024" / "GO_Municipios_2024.shp").to_crs(CRS_GEO)
go = mun.union_all()
go_m = gpd.GeoSeries([go], crs=CRS_GEO).to_crs(CRS_METRICO).iloc[0]


def dentro_go(x, y):
    return shapely.contains_xy(go, x, y)


x, y = g.cent_x.values, g.cent_y.values
ok = dentro_go(x, y)
cat = np.full(len(g), "fora de GO (outra localização no Brasil)", dtype=object)
cat[ok] = "dentro de GO"
ok_fin = np.isfinite(x) & np.isfinite(y)
troca = ~ok & ok_fin & dentro_go(y, x)
sinal = ~ok & ~troca & ok_fin & (dentro_go(-x, y) | dentro_go(x, -y) | dentro_go(-x, -y))
br = (x > -74) & (x < -34) & (y > -34) & (y < 6)
cat[troca] = "erro: lat/lon invertidos"
cat[sinal] = "erro: sinal trocado"
cat[~ok & ~troca & ~sinal & ~br] = "erro: coordenada fora do Brasil"
cat[~ok_fin] = "sem geometria"
g["loc_cat"] = cat
loc = g.loc_cat.value_counts().rename_axis("categoria").reset_index(name="glebas")
loc["pct"] = 100 * loc.glebas / loc.glebas.sum()
P("\n### Sanidade das coordenadas (centroide da gleba)\n")
P(tabela(loc, "{:.2f}"), "\n")

# município declarado (prévia; o cruzamento 3 fará com área)
ops_mun = con.sql("SELECT ref_bacen, nu_ordem, cd_ibge_municipio, vl_area_informada, vl_parc_credito, "
                  "safra, finalidade, produto, is_bb FROM ops").df()
g = g.merge(ops_mun, on=["ref_bacen", "nu_ordem"], how="left")
pts = gpd.GeoDataFrame(g[["ref_bacen", "nu_ordem", "nu_indice"]],
                       geometry=gpd.points_from_xy(g.cent_x, g.cent_y), crs=CRS_GEO)
sj = gpd.sjoin(pts, mun[["CD_MUN", "geometry"]], how="left", predicate="within")
sj = sj[~sj.index.duplicated()]
g["mun_centroide"] = sj["CD_MUN"].values
dec = g[g.loc_cat == "dentro de GO"]
pct_mun = 100 * (dec.mun_centroide == dec.cd_ibge_municipio).mean()
P(f"Das glebas dentro de GO, **{pct_mun:.1f}%** têm o centroide no município declarado da operação "
  "(prévia — o cruzamento 3 refaz isso por área e com tolerância de borda).\n")

# área: gleba vs informada (prévia por operação)
area_op = g[g.wkt_tipo.isin(["POLYGON", "MULTIPOLYGON"])].groupby(["ref_bacen", "nu_ordem"]).agg(area_gleba_ha=("area_ha", "sum"),
                                                    vl_area_informada=("vl_area_informada", "first"))
area_op = area_op[(area_op.vl_area_informada > 0)]
r = area_op.area_gleba_ha / area_op.vl_area_informada
P(f"Área: soma das glebas ÷ `VL_AREA_INFORMADA` por operação — mediana {r.median():.3f}, "
  f"p01 {r.quantile(.01):.2f}, p10 {r.quantile(.1):.3f}, p90 {r.quantile(.9):.3f}, p99 {r.quantile(.99):.2f}; "
  f"razão entre 0,8 e 1,25 em {100*((r>=0.8)&(r<=1.25)).mean():.1f}% das {len(r):,} operações; "
  f"fora de [0,5; 2]: {int(((r<0.5)|(r>2)).sum()):,} (prévia do cruzamento 4).\n")
P(f"Área da gleba (ha): mediana {g.area_ha.median():.1f}, p95 {g.area_ha.quantile(.95):,.0f}, "
  f"máx {g.area_ha.max():,.0f}.\n")
P("**Leitura:** área e município batem quase perfeitamente com a gleba. Isso indica que o Sicor "
  "valida esses campos contra o polígono na entrada (ou a área é derivada dele). Consequência: os "
  "cruzamentos 3 (fora do município) e 4 (área incoerente) devem disparar pouco e funcionar mais "
  "como controle de qualidade do que como detector.\n")
fora = g[g.loc_cat != "dentro de GO"][["ref_bacen", "nu_ordem", "nu_indice", "loc_cat", "cent_x", "cent_y",
                                       "area_ha", "cd_ibge_municipio"]]
if len(fora):
    P("Glebas com centroide fora de GO:\n")
    P(tabela(fora.assign(ref_bacen=fora.ref_bacen.astype(str)).round(4)), "\n")

# =========================================================== 5. mapa 10 glebas aleatórias
rng = np.random.default_rng(20261115)
ops_com = g.dropna(subset=["cent_x"])[["ref_bacen", "nu_ordem"]].drop_duplicates()
amostra = ops_com.iloc[rng.choice(len(ops_com), 10, replace=False)]
gs = g.merge(amostra, on=["ref_bacen", "nu_ordem"])
gs = gpd.GeoDataFrame(gs, geometry="geometry", crs=CRS_GEO).to_crs(CRS_METRICO)
mun_m = mun.to_crs(CRS_METRICO)

fig = plt.figure(figsize=(17, 8.5), facecolor="white")
gsp = fig.add_gridspec(2, 7, width_ratios=[1.5, 1.5, 1, 1, 1, 1, 1], wspace=0.12, hspace=0.42,
                       top=0.86, bottom=0.08, left=0.01, right=0.99)
ax0 = fig.add_subplot(gsp[:, :2])
mun_m.plot(ax=ax0, facecolor=CINZA_FUNDO, edgecolor=CINZA_LINHA, linewidth=0.3)
linhas = []
for i, ((rb, no), sub) in enumerate(gs.groupby(["ref_bacen", "nu_ordem"], sort=False), start=1):
    c = sub.union_all().centroid
    dentro = go_m.contains(c)
    if dentro:
        ax0.plot(c.x, c.y, "o", ms=9, mfc=AZUL, mec="white", mew=1.5, zorder=3)
        ax0.annotate(str(i), (c.x, c.y), xytext=(6, 6), textcoords="offset points", fontsize=10,
                     color="#0b0b0b", weight="bold")
    j = i - 1
    ax = fig.add_subplot(gsp[j // 5, 2 + j % 5])
    cod = sub.cd_ibge_municipio.iloc[0]
    md_ = mun_m[mun_m.CD_MUN == cod]
    # enquadramento: município declarado inteiro + a gleba (quadrado, com folga)
    alvo = pd.concat([md_.geometry, sub.geometry]) if len(md_) else sub.geometry
    xmin, ymin, xmax, ymax = alvo.total_bounds
    cx_, cy_ = (xmin + xmax) / 2, (ymin + ymax) / 2
    half = max(xmax - xmin, ymax - ymin) / 2 * 1.08 + 500
    mun_m.plot(ax=ax, facecolor="white", edgecolor=CINZA_LINHA, linewidth=0.5)
    if len(md_):
        md_.plot(ax=ax, facecolor=CINZA_FUNDO, edgecolor=LARANJA, linewidth=1.6)
    sub.plot(ax=ax, facecolor=AZUL, edgecolor=AZUL, linewidth=0.8, zorder=3)
    gc = sub.union_all().centroid
    ax.plot(gc.x, gc.y, "o", ms=16, mfc="none", mec=AZUL, mew=1.5, zorder=4)  # anel: gleba é pequena
    ax.set_xlim(cx_ - half, cx_ + half); ax.set_ylim(cy_ - half, cy_ + half)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_color(CINZA_LINHA)
    nome = md_.NM_MUN.iloc[0] if len(md_) else f"mun. {cod}"
    no_mun = len(md_) and md_.geometry.iloc[0].contains(sub.union_all().centroid)
    a_calc, a_inf = sub.area.sum() / 1e4, sub.vl_area_informada.iloc[0]
    ax.set_title(f"{i}. {nome[:18]}", fontsize=9, loc="left", color="#0b0b0b")
    ax.text(0.0, -0.03, f"{a_calc:,.0f} ha calculados / {a_inf:,.0f} ha informados\n"
            f"{len(sub)} gleba(s) · {'dentro do município' if no_mun else 'FORA do município'}",
            transform=ax.transAxes, fontsize=8, color=TXT2, va="top")
    linhas.append(dict(n=i, ref_bacen=rb, nu_ordem=no, municipio_declarado=nome, safra=sub.safra.iloc[0],
                       finalidade=sub.finalidade.iloc[0], produto=sub.produto.iloc[0],
                       banco="BB" if sub.is_bb.iloc[0] else "Demais", n_glebas=len(sub),
                       area_calc_ha=round(a_calc, 1), area_informada_ha=a_inf,
                       centroide_no_municipio=bool(no_mun), dentro_go=bool(dentro)))
ax0.set_axis_off()
fig.text(0.01, 0.955, "10 operações sorteadas: glebas do Sicor sobre a malha municipal de Goiás (IBGE 2024)",
         fontsize=14, color="#0b0b0b", weight="bold")
fig.text(0.01, 0.92, "Esquerda: posição de cada operação no estado (o vazio é o DF).  Direita: município "
         "declarado inteiro (laranja) com a gleba em azul; o anel marca a posição.", fontsize=10, color=TXT2)
fig.text(0.01, 0.025, "Fontes: BCB/Sicor (glebas, município do complemento), IBGE malha municipal 2024.  "
         "Projeção: SIRGAS 2000 / Brazil Polyconic (EPSG:5880).", fontsize=9, color=TXT2)
fig.savefig(OUT / "maps" / "passo0_glebas_aleatorias.png", dpi=150, bbox_inches="tight")
amostra_df = pd.DataFrame(linhas)
amostra_df.to_csv(OUT / "passo0_amostra_10.csv", index=False)

P("## 5. Amostra visual (10 operações sorteadas)\n")
P("![10 glebas](maps/passo0_glebas_aleatorias.png)\n")
P(tabela(amostra_df.drop(columns=["ref_bacen"]).assign(ref_bacen=amostra_df.ref_bacen.astype(str))))

# =========================================================== 6. camadas de cruzamento
P("\n## 6. Camadas de cruzamento — o que foi possível baixar\n")
cam = []
cam.append(dict(base="Malha municipal (IBGE 2024)", status="ok (geoftp IBGE)", feicoes_em_GO=len(mun),
                obs="246 municípios"))
ti = gpd.read_file(RAW / "funai" / "tis_poligonais_go.geojson").to_crs(CRS_GEO)
ti_go = ti[ti.intersects(go)]
cam.append(dict(base="Terras indígenas (FUNAI)", status="ok (WFS geoserver.funai.gov.br)",
                feicoes_em_GO=len(ti_go), obs="; ".join(sorted(ti_go.terrai_nome.unique()))[:90]))
uc = gpd.read_file(RAW / "cnuc" / "shp" / "cnuc_2025_08.shp", encoding="latin1")
uc = uc.to_crs(CRS_GEO)
uc["geometry"] = uc.make_valid()
uc_go = uc[uc.intersects(go)]
grp = uc_go.grupo.map(lambda s: s.encode("latin1").decode("utf-8", "replace") if isinstance(s, str) else s)
cat_ = uc_go.categoria.map(lambda s: s.encode("latin1").decode("utf-8", "replace") if isinstance(s, str) else s)
cam.append(dict(base="Unidades de conservação (MMA/CNUC 2025-08)", status="ok (dados.mma.gov.br)",
                feicoes_em_GO=len(uc_go),
                obs=f"Proteção Integral {int((grp=='Proteção Integral').sum())}; APA {int(cat_.str.contains('Proteção Ambiental').sum())}; "
                    f"RPPN {int(cat_.str.contains('Particular').sum())}; outras US {int((grp=='Uso Sustentável').sum() - cat_.str.contains('Proteção Ambiental|Particular').sum())}"))
emb = con.sql(f"""SELECT count(*) n, count(*) FILTER (WHERE GEOM_AREA_EMBARGADA <> '') poli,
  count(*) FILTER (WHERE SIT_CANCELADO='S') canc
  FROM read_csv('{RAW / 'ibama' / 'termo_de_embargo.csv'}', delim=';', header=true, all_varchar=true,
                quote='"', max_line_size=50000000) WHERE UF='GO'""").fetchall()[0]
cam.append(dict(base="Áreas embargadas (IBAMA, termos de embargo)", status="ok (dadosabertos.ibama.gov.br)",
                feicoes_em_GO=emb[0], obs=f"{emb[1]:,} com polígono, demais só ponto; {emb[2]} cancelados; "
                "arquivo traz nome/CPF — descartados na ingestão"))
ma = gpd.read_file(RAW / "ana" / "massa_dagua_go.geojson")
cam.append(dict(base="Massas d'água (ANA/SNIRH)", status="ok (ArcGIS REST snirh.gov.br)",
                feicoes_em_GO=len(ma), obs="envelope de GO; inclui açudes pequenos. Rios como linha (BHO) não "
                "baixados: sem área, não servem ao critério >10% da gleba"))
cam.append(dict(base="CAR — polígonos dos imóveis (SICAR)", status="**MANUAL**", feicoes_em_GO=None,
                obs="download por estado exige navegador (página com captcha) — ver instruções abaixo"))
P(tabela(pd.DataFrame(cam)), "\n")
P("**CAR de Goiás (manual):** acesse <https://consultapublica.car.gov.br/publico/estados/downloads>, "
  "escolha **Goiás**, tema **Área do Imóvel** (shapefile `AREA_IMOVEL`), preencha o captcha/e-mail e "
  "salve o .zip em `data/raw/car/` (qualquer nome). O código do SICAR tem hífens/pontos "
  "(`GO-5218003-XXXX.XXXX...`); será normalizado para o formato do Sicor (sem separadores).\n")

# salva atributos de gleba para as próximas etapas
g[["ref_bacen", "nu_ordem", "nu_indice", "area_ha", "cent_x", "cent_y", "loc_cat", "mun_centroide"]].to_parquet(
    PROC / "glebas_go_atributos.parquet")
stats = dict(n_glebas=n_gl, invalidas=invalidas, nulas=nulas, vazias=vazias)
json.dump(stats, open(OUT / "passo0_stats.json", "w"))
(OUT / "reconhecimento.md").write_text("\n".join(md) + "\n")
print("\n".join(md))
