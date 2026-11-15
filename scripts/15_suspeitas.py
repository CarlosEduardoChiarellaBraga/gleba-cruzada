"""KML com os 5 casos de suspeitas.md: glebas financiadas, CAR informado, CAR que contém a gleba e embargos.
Saída: outputs/revisao/suspeitas.kml (abrir no Google Earth)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent))
import geopandas as gpd, pandas as pd
from common import PROC, OUT

CASOS = {  # caso: (título, contratos, CARs informados, CARs que contêm a gleba)
    1: ("Café financiado 2x — BB e Rabobank (Campo Alegre de Goiás)", ["512969168", "513267165"],
        ["GO52048055DF1FF916A724CBCA5392301AE19A720"], ["GO5210109B147BBA555F643CDBAEC854E51F1C448"]),
    2: ("Gleba desenhada fora do CAR embargado (Porangatu)", ["512628425", "514044225"],
        ["GO5218003CE4BE8FCD7304EFF9CA5F1D9325D8279"], ["GO5218003D1CB441EBE0E4283B766EB983BDC6D46"]),
    3: ("Mesma terra, 2º contrato com CAR de Portelândia (Mineiros)", ["513159196", "513918443"],
        ["GO5218102D423C00CCEDF4334A0CEB9078836133C"], ["GO521310328B92120D0274806A9030E2AE0809ABB"]),
    4: ("Correção de solo financiada 2x — BB e Sicredi (Palestina de Goiás)", ["516330397", "517600549"],
        [], ["GO5215652544BC96957D84BD49A41E085FEE2AF49", "GO5215652A2EDC31D3A794C8F934F3169B8352535"]),
    5: ("3 contratos no teto de R$ 500 mil na mesma terra (Trombas)", ["518924190", "519479638", "519626683"],
        [], ["GO5221452CF80B0A14B0C453196B6D5D2012C1425"]),
}
f = gpd.read_parquet(PROC / "op_footprint.parquet")
car = gpd.read_parquet(PROC / "car_go.parquet")
emb = gpd.read_parquet(PROC / "embargo_go.parquet")
emb = emb[(emb.sit_cancelado != "S") & emb.dat_desembargo.isna()]

def coords(r): return " ".join(f"{x:.6f},{y:.6f}" for x, y in r.coords)
def kml_geom(geom):
    out = []
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type == "Polygon":
            inner = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{coords(r)}</coordinates></LinearRing></innerBoundaryIs>" for r in g.interiors)
            out.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(g.exterior)}</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>")
        elif g.geom_type == "Point":
            out.append(f"<Point><coordinates>{g.x:.6f},{g.y:.6f}</coordinates></Point>")
    return f"<MultiGeometry>{''.join(out)}</MultiGeometry>"
def pm(nome, desc, estilo, geom):
    return f"<Placemark><name>{nome}</name><description><![CDATA[{desc}]]></description><styleUrl>#{estilo}</styleUrl>{kml_geom(geom)}</Placemark>"

K = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Suspeitas — revisão</name>',
     '<Style id="gleba"><LineStyle><color>ff3468eb</color><width>3</width></LineStyle><PolyStyle><color>403468eb</color></PolyStyle></Style>',
     '<Style id="car_inf"><LineStyle><color>ffd6782a</color><width>3</width></LineStyle><PolyStyle><color>18d6782a</color></PolyStyle></Style>',
     '<Style id="car_cont"><LineStyle><color>ff7aaf1b</color><width>3</width></LineStyle><PolyStyle><color>187aaf1b</color></PolyStyle></Style>',
     '<Style id="emb"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle><PolyStyle><color>600000ff</color></PolyStyle></Style>']
for n, (tit, refs, inf, cont) in CASOS.items():
    K.append(f"<Folder><name>Caso {n} — {tit}</name>")
    ops = f[f.ref_bacen.astype(str).isin(refs)]
    for _, o in ops.to_crs(4326).iterrows():
        d = (f"Operação {o.ref_bacen}/{o.nu_ordem} · {o.nome_if}<br>Emissão {pd.Timestamp(o.dt_emissao):%d/%m/%Y} · safra {o.safra}"
             f"<br>{o.finalidade} · {o.modalidade} · {o.produto}<br>R$ {o.vl_parc_credito:,.2f} · área declarada {o.vl_area_informada} ha"
             f" · gleba {o.area_ha:.1f} ha<br>CAR informado: {', '.join(o.cars) if o.cars is not None else '-'}")
        K.append(pm(f"Gleba {o.ref_bacen} ({o.nome_if[:12]})", d, "gleba", o.geometry))
    zona = ops.geometry.union_all()
    for cods, estilo, rot in [(inf, "car_inf", "CAR informado"), (cont, "car_cont", "CAR que contém a gleba")]:
        for c in cods:
            g = car[car.cod_norm == c]
            if len(g):
                r = g.iloc[0]; zona = zona.union(g.geometry.union_all())
                K.append(pm(f"{rot}: {r.cod_imovel}", f"{r.cod_imovel}<br>{r.area_calc_ha:.1f} ha · criado {r.dat_criaca} · atualizado {r.dat_atuali}",
                            estilo, gpd.GeoSeries([g.geometry.union_all()], crs=car.crs).to_crs(4326).iloc[0]))
    e = emb[emb.intersects(zona.buffer(500))]
    for _, r in e.to_crs(4326).iterrows():
        K.append(pm(f"Embargo IBAMA TAD {r.num_tad}", f"TAD {r.num_tad} · embargado em {pd.Timestamp(r.dat_embargo):%d/%m/%Y} · {r.qtd_area_embargada_ha} ha",
                    "emb", r.geometry))
    K.append("</Folder>")
K.append("</Document></kml>")
(OUT / "revisao" / "suspeitas.kml").write_text("".join(K), encoding="utf-8")
print("ok:", OUT / "revisao" / "suspeitas.kml")
