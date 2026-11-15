"""Cruzamento 3 — Geometria impossível.

Para cada operação com gleba:
  a) massa d'água: fração da gleba sobre água. Indício se > 10% sobre água "grande" (≥ 100 ha ou
     natural); > 10% só sobre açudes pequenos = ruído provável (bebedouro/represa de fazenda).
  b) terra indígena: > 10% da gleba dentro de TI.
  c) unidade de conservação: > 10% em Proteção Integral ou RPPN (indício); APA e outras de uso
     sustentável admitem produção (contexto).  UC criada depois do contrato não conta.
  d) embargo IBAMA: polígono embargado cobrindo > 10% da gleba (ou ponto do embargo dentro da
     gleba), com embargo ANTERIOR à emissão, não cancelado e sem desembargo antes do contrato.
  e) fora do município declarado: < 50% da gleba no município declarado. Se a maior parte está num
     município vizinho → erro de cadastro provável; não vizinho ou fora de GO → indício.
     Coordenada trocada (lat/lon invertidos, sinal) → erro de cadastro (testado no passo 0: 0 casos).
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import PROC, RES, banco, fracao_sobreposta, load_fp, resumo, salva_resumo  # noqa: E402

LIM = 0.10
fp = load_fp().reset_index(drop=True)
fp["banco"] = fp.is_bb.map(banco)
fp["dt"] = pd.to_datetime(fp.dt_emissao)
print(f"operações com gleba: {len(fp):,}")


def junta(df, prefixo):
    d = df.set_index("idx")[["inter_ha", "frac"]].add_prefix(prefixo)
    for c in d.columns:
        fp[c] = d[c].reindex(fp.index).fillna(0.0)


# ---------------------------------------------------------------- a) água
ag = gpd.read_parquet(PROC / "agua_go.parquet")
junta(fracao_sobreposta(fp, ag), "agua_")
junta(fracao_sobreposta(fp, ag, "grande", True), "aguag_")
print("água ok", flush=True)

# ---------------------------------------------------------------- b) TI
ti = gpd.read_parquet(PROC / "ti_go.parquet")
junta(fracao_sobreposta(fp, ti), "ti_")
fp["ti_nome"] = ""
if (fp.ti_frac > 0).any():
    j = gpd.sjoin(fp[fp.ti_frac > 0][["geometry"]], ti[["terrai_nome", "geometry"]], predicate="intersects")
    fp.loc[j.index, "ti_nome"] = j.groupby(level=0).terrai_nome.first()

# ---------------------------------------------------------------- c) UC por classe (só UCs criadas antes)
uc = gpd.read_parquet(PROC / "uc_go.parquet")
uc["cria_ano"] = pd.to_numeric(uc.cria_ano, errors="coerce")
for cl in ["PI", "RPPN", "APA", "US-outras"]:
    junta(fracao_sobreposta(fp, uc, "classe", cl), f"uc_{cl}_")
fp["uc_nome"] = ""
sel = (fp["uc_PI_frac"] > 0) | (fp["uc_RPPN_frac"] > 0)
if sel.any():
    j = gpd.sjoin(fp[sel][["geometry", "dt"]], uc[uc.classe.isin(["PI", "RPPN"])][["nome_uc", "cria_ano", "geometry"]],
                  predicate="intersects")
    fp.loc[j.index, "uc_nome"] = j.groupby(level=0).nome_uc.first()
    fp["uc_cria_ano"] = j.groupby(level=0).cria_ano.max().reindex(fp.index)
else:
    fp["uc_cria_ano"] = np.nan
fp["uc_posterior"] = fp.uc_cria_ano > fp.dt.dt.year
print("UC ok", flush=True)

# ---------------------------------------------------------------- d) embargos
emb = gpd.read_parquet(PROC / "embargo_go.parquet")
emb = emb[emb.sit_cancelado.fillna("N") != "S"]
tree = shapely.STRtree(emb.geometry.values)
i_fp, i_e = tree.query(fp.geometry.values, predicate="intersects")
pares = pd.DataFrame({"i": i_fp, "e": i_e})
pares["dt"] = fp.dt.values[pares.i]
pares["dat_embargo"] = emb.dat_embargo.values[pares.e]
pares["dat_desembargo"] = emb.dat_desembargo.values[pares.e]
pares["geom_tipo"] = emb.geom_tipo.values[pares.e]
pares["num_tad"] = emb.num_tad.values[pares.e]
pares["frac"] = shapely.area(shapely.intersection(fp.geometry.values[pares.i], emb.geometry.values[pares.e])) / \
    fp.area.values[pares.i]
pares["anterior"] = pares.dat_embargo < pares.dt
pares["vigente"] = pares.dat_desembargo.isna() | (pares.dat_desembargo > pares.dt)
pares["relevante"] = np.where(pares.geom_tipo == "poligono", pares.frac > LIM, True)
pares["dias_antes"] = (pares.dt - pares.dat_embargo).dt.days
val = pares[pares.anterior & pares.vigente & pares.relevante]
fp["emb_poligono"] = False
fp["emb_ponto"] = False
fp.loc[val[val.geom_tipo == "poligono"].i.unique(), "emb_poligono"] = True
fp.loc[val[val.geom_tipo == "ponto"].i.unique(), "emb_ponto"] = True
ag_e = val.sort_values("frac", ascending=False).drop_duplicates("i").set_index("i")
fp["emb_frac"] = ag_e.frac.reindex(fp.index)
fp["emb_dias_antes"] = ag_e.dias_antes.reindex(fp.index)
fp["emb_num_tad"] = ag_e.num_tad.reindex(fp.index)
fp["emb_posterior"] = False  # contexto: embargo DEPOIS do contrato (não é sinal, mas é informação)
post = pares[~pares.anterior & pares.relevante]
fp.loc[post.i.unique(), "emb_posterior"] = True
print(f"embargos: pares gleba×embargo {len(pares):,}; válidos {len(val):,}", flush=True)

# ---------------------------------------------------------------- e) município
mun = gpd.read_parquet(PROC / "municipios_go.parquet")
mi = mun.set_index("CD_MUN")
mgeo = mun.geometry.values
shapely.prepare(mgeo)
go_u = shapely.union_all(mgeo)
shapely.prepare(go_u)
tree_m = shapely.STRtree(mgeo)
# caminho rápido: gleba inteiramente dentro de um município (a imensa maioria)
gi, mj = tree_m.query(fp.geometry.values, predicate="within")
dentro = pd.Series(mun.CD_MUN.values[mj], index=gi)
dentro = dentro[~dentro.index.duplicated()]
n = len(fp)
mun_maior = np.array([None] * n, dtype=object)
frac_maior = np.zeros(n)
mun_maior[dentro.index.values] = dentro.values
frac_maior[dentro.index.values] = 1.0
borda = np.setdiff1d(np.arange(n), dentro.index.values)
print(f"  glebas inteiras num município: {len(dentro):,}; de borda: {len(borda):,}", flush=True)
for i in borda:
    g = fp.geometry.values[i]
    js = tree_m.query(g, predicate="intersects")
    if len(js):
        fr = shapely.area(shapely.intersection(g, mgeo[js])) / shapely.area(g)
        k = int(np.argmax(fr))
        mun_maior[i], frac_maior[i] = mun.CD_MUN.values[js[k]], fr[k]
frac_dec = np.full(n, np.nan)
cod_dec = fp.cd_ibge_municipio.values
for i in range(n):
    if frac_maior[i] == 1.0 and mun_maior[i] is not None:
        frac_dec[i] = 1.0 if mun_maior[i] == cod_dec[i] else 0.0
    elif cod_dec[i] in mi.index:
        g = fp.geometry.values[i]
        frac_dec[i] = shapely.area(shapely.intersection(g, mi.geometry[cod_dec[i]])) / shapely.area(g)
fp["frac_mun_declarado"] = frac_dec
fp["mun_maior_parte"] = mun_maior
frac_go = np.ones(n)
for i in borda:
    g = fp.geometry.values[i]
    frac_go[i] = shapely.area(shapely.intersection(g, go_u)) / shapely.area(g)
fp["frac_em_go"] = frac_go
viz = []
for cod_d, cod_m in zip(fp.cd_ibge_municipio, fp.mun_maior_parte):
    if cod_d in mi.index and cod_m in mi.index and cod_d != cod_m:
        viz.append(bool(shapely.distance(mi.geometry[cod_d], mi.geometry[cod_m]) < 1.0))
    else:
        viz.append(False)
fp["maior_parte_em_vizinho"] = viz
print("município ok", flush=True)

# ---------------------------------------------------------------- classificação
F = fp
aqui = (F.modalidade.fillna("").str.contains("AQUI|PISCI", case=False) |
        F.unidade_medida.fillna("").str.contains("lâmina|Tanque", case=False) |
        F.produto.fillna("").str.contains("PEIXE|ALEVIN|TILÁPIA|CAMAR|AQUIC", case=False))
F["aquicultura"] = aqui
varzea = F.produto.fillna("").str.contains("ARROZ", case=False)  # arroz irrigado em várzea: área alagável
F["arroz_varzea"] = varzea
sinais = {
    "água grande > 10% (indício)": (F.aguag_frac > LIM) & ~aqui & ~varzea,
    "arroz sobre várzea/água (ruído provável)": (F.agua_frac > LIM) & varzea,
    "aquicultura sobre água (esperado)": (F.agua_frac > LIM) & aqui,
    "açude pequeno > 10% (ruído provável)": (F.agua_frac > LIM) & ~(F.aguag_frac > LIM) & ~aqui & ~varzea,
    "terra indígena > 10% (indício)": F.ti_frac > LIM,
    "UC proteção integral > 10% (indício)": (F.uc_PI_frac > LIM) & ~F.uc_posterior.fillna(False),
    "RPPN > 10% (indício)": (F.uc_RPPN_frac > LIM) & ~F.uc_posterior.fillna(False),
    "APA > 10% (contexto, permitido)": F.uc_APA_frac > LIM,
    "embargo IBAMA vigente (polígono > 10%) antes do contrato (indício)": F.emb_poligono,
    "embargo IBAMA vigente (ponto na gleba) antes do contrato (indício fraco)": F.emb_ponto & ~F.emb_poligono,
    "embargo só DEPOIS do contrato (contexto)": F.emb_posterior & ~F.emb_poligono & ~F.emb_ponto,
    "fora do município: maior parte em vizinho (erro de cadastro provável)":
        (F.frac_mun_declarado < 0.5) & F.maior_parte_em_vizinho & (F.frac_em_go > 0.5),
    "fora do município: não vizinho (indício)":
        (F.frac_mun_declarado < 0.5) & ~F.maior_parte_em_vizinho & (F.frac_em_go > 0.5),
    "fora de GO (> 50% da gleba)": F.frac_em_go <= 0.5,
}
indicio_cols = [k for k in sinais if "(indício" in k or k.startswith("fora de GO")]
F["n_sinais"] = sum(sinais[k].astype(int) for k in indicio_cols)
F["sinal"] = F.n_sinais > 0
F["motivos"] = [";".join(k.split(" (")[0] for k in indicio_cols if sinais[k].iloc[i]) for i in range(len(F))]

def n_imoveis(mask):
    cs = F.loc[mask, "cars"].dropna()
    return len({c for lst in cs for c in lst}) if len(cs) else 0


def n_areas(mask):  # glebas distintas (geometria arredondada) — mesma área em safras diferentes conta 1
    return F.loc[mask, "geometry"].apply(lambda g: shapely.normalize(shapely.set_precision(g, 1.0)).wkb).nunique()


res = [resumo(F, F.sinal, "3. Geometria impossível — qualquer indício",
              dict(imoveis_car=n_imoveis(F.sinal), areas_distintas=n_areas(F.sinal)))]
for k, m_ in sinais.items():
    res.append(resumo(F, m_, f"3. — {k}", dict(imoveis_car=n_imoveis(m_), areas_distintas=n_areas(m_))))
salva_resumo("cruz3", res)

F["forca"] = (F.aguag_frac.where((F.aguag_frac > LIM) & ~aqui & ~varzea, 0) + F.ti_frac.where(F.ti_frac > LIM, 0) +
              F.uc_PI_frac.where(F.uc_PI_frac > LIM, 0) + F.uc_RPPN_frac.where(F.uc_RPPN_frac > LIM, 0) +
              F.emb_frac.fillna(0).where(F.emb_poligono, 0) + 0.3 * F.emb_ponto +
              (1 - F.frac_mun_declarado.fillna(1)).where(~F.maior_parte_em_vizinho, 0)) * \
    np.log10(1 + F.vl_parc_credito)
cols = ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "vl_parc_credito", "area_ha",
        "motivos", "aguag_frac", "agua_frac", "ti_frac", "ti_nome", "uc_PI_frac", "uc_RPPN_frac", "uc_nome",
        "emb_frac", "emb_dias_antes", "frac_mun_declarado", "cd_ibge_municipio", "mun_maior_parte",
        "maior_parte_em_vizinho", "forca"]
out = F.drop(columns="geometry")
keep = ["ref_bacen", "nu_ordem", "sinal", "n_sinais", "uc_APA_frac", "agua_inter_ha", "emb_num_tad"]
out[cols + [c for c in keep if c not in cols]].to_parquet(PROC / "cruz3_ops.parquet")
casos = out[out.sinal].sort_values("forca", ascending=False)
casos[cols].to_csv(RES / "cruz3_casos_indicio.csv", index=False)
t = casos[cols].head(10).copy(); t["ref_bacen"] = t.ref_bacen.astype(str)
t.to_csv(RES / "cruz3_top10.csv", index=False)
print(pd.DataFrame(res)[["cruzamento", "disparam", "pct_elegiveis", "bb_pct", "demais_pct", "imoveis_car", "areas_distintas"]].to_string())
