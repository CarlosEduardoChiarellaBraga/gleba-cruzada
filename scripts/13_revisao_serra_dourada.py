"""Pacote de revisão manual: glebas financiadas dentro do PE Serra Dourada (Cruzamento 3).
Gera outputs/revisao/serra_dourada.kml (abrir no Google Earth) + CSVs por imóvel e por operação."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent))
from xml.sax.saxutils import escape
import geopandas as gpd, pandas as pd
from common import PROC, OUT

R = OUT / "revisao"; R.mkdir(parents=True, exist_ok=True)
c = pd.read_parquet(PROC / "cruz3_ops.parquet")
s = c[(c.uc_PI_frac > 0.1) & c.uc_nome.str.contains("SERRA DOURADA", na=False)]
f = gpd.read_parquet(PROC / "op_footprint.parquet")
g = f.merge(s[["ref_bacen", "nu_ordem", "uc_PI_frac"]], on=["ref_bacen", "nu_ordem"]).to_crs(4326)
g["car"] = g.cars.apply(lambda x: ",".join(x) if x is not None and len(x) else "")
mun = gpd.read_parquet(PROC / "municipios_go.parquet")
col_nome = [k for k in mun.columns if k.upper().startswith("NM_MUN")][0]
col_cd = [k for k in mun.columns if k.upper().startswith("CD_MUN")][0]
nomes = dict(zip(mun[col_cd].astype(str), mun[col_nome]))
g["municipio"] = g.cd_ibge_municipio.astype(str).map(nomes)
p = g.geometry.representative_point(); g["lat"] = p.y.round(5); g["lon"] = p.x.round(5)
g["id_imovel"] = g.car.where(g.car != "", g.lat.astype(str) + "," + g.lon.astype(str))
g["data_emissao"] = pd.to_datetime(g.dt_emissao).dt.strftime("%Y-%m-%d")

im = (g.groupby("id_imovel", as_index=False).agg(n_ops=("ref_bacen", "size"), safras=("safra", lambda x: ", ".join(sorted(set(x)))),
      produtos=("produto", lambda x: ", ".join(sorted(set(x)))[:80]), bancos=("nome_if", lambda x: ", ".join(sorted(set(x)))),
      valor_total=("vl_parc_credito", "sum"), area_ha=("area_ha", "max"), pct_na_uc=("uc_PI_frac", "max"),
      municipio=("municipio", "first"), lat=("lat", "first"), lon=("lon", "first"), car=("car", "first"))
      .sort_values("valor_total", ascending=False).reset_index(drop=True))
im.insert(0, "caso", range(1, len(im) + 1))
im["pct_na_uc"] = (im.pct_na_uc * 100).round(0); im["area_ha"] = im.area_ha.round(1); im["valor_total"] = im.valor_total.round(0)
im["google_maps"] = [f"https://www.google.com/maps/@{a},{o},1500m/data=!3m1!1e3" for a, o in zip(im.lat, im.lon)]
im.drop(columns="id_imovel").to_csv(R / "serra_dourada_imoveis.csv", index=False)
g["caso"] = g.id_imovel.map(dict(zip(im.id_imovel, im.caso)))
g[["caso", "ref_bacen", "nu_ordem", "nome_if", "safra", "data_emissao", "finalidade", "produto", "vl_parc_credito", "area_ha",
   "uc_PI_frac", "municipio", "car", "lat", "lon"]].sort_values(["caso", "data_emissao"]).to_csv(R / "serra_dourada_operacoes.csv", index=False)

uc = gpd.read_parquet(PROC / "uc_go.parquet"); uc = uc[uc.nome_uc == "PARQUE ESTADUAL DA SERRA DOURADA"].to_crs(4326)

def coords(ring): return " ".join(f"{x:.6f},{y:.6f}" for x, y in ring.coords)
def poly_kml(geom):
    out = []
    for pg in getattr(geom, "geoms", [geom]):
        if pg.geom_type != "Polygon": continue
        inner = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{coords(r)}</coordinates></LinearRing></innerBoundaryIs>" for r in pg.interiors)
        out.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(pg.exterior)}</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>")
    return f"<MultiGeometry>{''.join(out)}</MultiGeometry>"

K = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Serra Dourada — revisão</name>',
     '<Style id="uc"><LineStyle><color>ff00a000</color><width>3</width></LineStyle><PolyStyle><color>2000a000</color></PolyStyle></Style>',
     '<Style id="gl"><LineStyle><color>ff3468eb</color><width>2</width></LineStyle><PolyStyle><color>403468eb</color></PolyStyle></Style>']
for _, u in uc.iterrows():
    K.append(f'<Placemark><name>PE Serra Dourada (criado {u.cria_ano})</name><styleUrl>#uc</styleUrl>{poly_kml(u.geometry)}</Placemark>')
K.append("<Folder><name>Glebas financiadas (por caso)</name>")
for caso, grp in g.sort_values("caso").groupby("caso"):
    r = im.loc[im.caso == caso].iloc[0]
    K.append(f"<Folder><name>Caso {caso} — {r.municipio} — R$ {r.valor_total:,.0f}</name>")
    for _, o in grp.iterrows():
        d = (f"Operação {o.ref_bacen}/{o.nu_ordem}<br>{o.nome_if}<br>Emissão {o.data_emissao} · safra {o.safra}<br>{o.finalidade} · {o.produto}"
             f"<br>R$ {o.vl_parc_credito:,.2f} · {o.area_ha:.1f} ha · {o.uc_PI_frac:.0%} no parque<br>CAR {o.car}")
        K.append(f"<Placemark><name>{o.safra} {escape(str(o.produto))[:30]}</name><description><![CDATA[{d}]]></description>"
                 f"<styleUrl>#gl</styleUrl>{poly_kml(o.geometry)}</Placemark>")
    K.append("</Folder>")
K.append("</Folder></Document></kml>")
(R / "serra_dourada.kml").write_text("".join(K), encoding="utf-8")
print(f"{len(im)} imóveis, {len(g)} operações -> {R}")
print(uc[["nome_uc", "esfera", "cria_ano", "situacao"]].to_string())
