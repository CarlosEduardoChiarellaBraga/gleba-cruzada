"""Cruzamento 2 — Mesma área financiada duas vezes.

Pares de operações distintas (REF_BACEN diferente) da MESMA safra e finalidade cujas glebas se
sobrepõem em > 50% da área da menor. Classificação do par:
  indício forte : mesmo produto e ciclos (plantio→colheita) sobrepostos [agrícola]
  indício       : mesmo produto, pecuária ou investimento (sem calendário para separar ciclos)
  provável legítimo : mesmo produto em ciclos que não se sobrepõem (ex.: milho verão + safrinha)
  ruído (sucessão/consórcio): produtos diferentes (ex.: soja → milho safrinha; lavoura + bovinos)
A regra original (só safra + finalidade) também é contada, para comparação.
Medida de excesso: (área informada A + área informada B) / área da união das glebas.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import PROC, RES, banco, load_fp, resumo, salva_resumo  # noqa: E402

LIM = 0.5
fp = load_fp().reset_index(drop=True)
fp["area_m2"] = fp.area
fp["ini"] = pd.to_datetime(fp.dt_inic_plantio)
fp["fim"] = pd.to_datetime(fp.dt_fim_colheita)

tree = shapely.STRtree(fp.geometry.values)
a, b = tree.query(fp.geometry.values, predicate="intersects")
m = a < b
a, b = a[m], b[m]
P = pd.DataFrame({"a": a, "b": b})
A, B = fp.iloc[P.a].reset_index(drop=True), fp.iloc[P.b].reset_index(drop=True)
mesmo = (A.safra.values == B.safra.values) & (A.finalidade.values == B.finalidade.values) & \
        (A.ref_bacen.values != B.ref_bacen.values)
P, A, B = P[mesmo].reset_index(drop=True), A[mesmo].reset_index(drop=True), B[mesmo].reset_index(drop=True)
print(f"pares que se tocam na mesma safra+finalidade: {len(P):,}")

inter = shapely.area(shapely.intersection(A.geometry.values, B.geometry.values))
P["inter_ha"] = inter / 1e4
P["frac_menor"] = inter / np.minimum(A.area_m2.values, B.area_m2.values)
keep = P.frac_menor > LIM
P, A, B = P[keep].reset_index(drop=True), A[keep].reset_index(drop=True), B[keep].reset_index(drop=True)
print(f"pares com sobreposição > {LIM:.0%} da menor: {len(P):,}")

uniao = shapely.area(shapely.union(A.geometry.values, B.geometry.values)) / 1e4
P["excesso_area"] = (A.vl_area_informada.values + B.vl_area_informada.values) / uniao
P["mesmo_produto"] = A.produto.values == B.produto.values
ua = A.unidade_medida.str.startswith("Unidade Animal").values & B.unidade_medida.str.startswith("Unidade Animal").values
P["ua_ha_par"] = np.where(ua, (A.vl_quantidade.values + B.vl_quantidade.values) / uniao, np.nan)
P["agricola"] = (A.atividade.values == "Agrícola") & (B.atividade.values == "Agrícola")
tem_cal = A.ini.notna().values & A.fim.notna().values & B.ini.notna().values & B.fim.notna().values
ciclo_sobrep = (A.ini.values <= B.fim.values) & (B.ini.values <= A.fim.values)
P["calendario"] = np.where(~tem_cal, "sem datas", np.where(ciclo_sobrep, "ciclos sobrepostos", "ciclos distintos"))
P["mesmo_banco"] = A.cnpj_if.values == B.cnpj_if.values
P["bancos"] = [("BB" if x else "Demais") + "×" + ("BB" if y else "Demais") for x, y in zip(A.is_bb, B.is_bb)]
P["bancos"] = P.bancos.replace({"Demais×BB": "BB×Demais"})
P["mesmo_car"] = [bool(set(x if isinstance(x, (list, np.ndarray)) else []) &
                       set(y if isinstance(y, (list, np.ndarray)) else [])) for x, y in zip(A.cars, B.cars)]

cl = np.full(len(P), "ruído: produtos diferentes (sucessão/consórcio)", dtype=object)
mp = P.mesmo_produto.values
cl[mp & P.agricola.values & (P.calendario.values == "ciclos sobrepostos")] = "indício forte: mesmo produto, mesmo ciclo"
cl[mp & P.agricola.values & (P.calendario.values == "ciclos distintos")] = "provável legítimo: mesmo produto, ciclos distintos"
cl[mp & P.agricola.values & (P.calendario.values == "sem datas")] = "indício: mesmo produto agrícola, sem datas"
# pecuária/investimento: sem calendário; usa o código do empreendimento e a sequência dos contratos
mesmo_emp = A.cd_empreendimento.values == B.cd_empreendimento.values
venc_a, venc_b = pd.to_datetime(A.dt_vencimento).values, pd.to_datetime(B.dt_vencimento).values
emi_a, emi_b = pd.to_datetime(A.dt_emissao).values, pd.to_datetime(B.dt_emissao).values
sequencial = (venc_a <= emi_b) | (venc_b <= emi_a)  # um venceu antes de o outro ser emitido
P["mesmo_empreendimento"], P["sequencial"] = mesmo_emp, sequencial
np_ = mp & ~P.agricola.values
cl[np_ & mesmo_emp & ~sequencial] = "indício: mesmo empreendimento, contratos simultâneos (pecuária/invest.)"
cl[np_ & mesmo_emp & sequencial] = "provável legítimo: mesmo empreendimento, contratos sequenciais"
cl[np_ & ~mesmo_emp] = "provável legítimo: mesmo produto, empreendimentos diferentes (pecuária/invest.)"
P["classe"] = cl
P["tipo"] = np.where(pd.Series(cl).str.startswith("indício"), "indício",
                     np.where(pd.Series(cl).str.startswith("provável"), "provável legítimo", "ruído provável"))

for lado, D in (("a", A), ("b", B)):
    for c in ["ref_bacen", "nu_ordem", "produto", "vl_parc_credito", "vl_area_informada", "area_ha",
              "dt_emissao", "nome_if"]:
        P[f"{c}_{lado}"] = D[c].values
P["safra"], P["finalidade"] = A.safra.values, A.finalidade.values
P["valor_par"] = P.vl_parc_credito_a + P.vl_parc_credito_b
P["forca"] = P.frac_menor * P.excesso_area.clip(upper=3) * np.log10(1 + P.valor_par) * \
    np.where(P.mesmo_banco, 1.0, 1.3)  # bancos diferentes pesam mais (driblar controle interno)

# ---------------------------------------------------------------- flags por operação
def ops_em(mask):
    s = set(zip(P.ref_bacen_a[mask], P.nu_ordem_a[mask])) | set(zip(P.ref_bacen_b[mask], P.nu_ordem_b[mask]))
    return pd.Series([(r, n) in s for r, n in zip(fp.ref_bacen, fp.nu_ordem)], index=fp.index)


res = [
    resumo(fp, ops_em(np.ones(len(P), bool)), "2. Regra original: mesma safra+finalidade, >50% (qualquer produto)"),
    resumo(fp, ops_em(P.tipo == "indício"), "2. Indício (mesmo produto; exclui ciclos distintos)"),
    resumo(fp, ops_em(P.classe == "indício forte: mesmo produto, mesmo ciclo"), "2. — indício forte (agrícola, mesmo ciclo)"),
    resumo(fp, ops_em(P.classe.str.startswith("indício: mesmo empreendimento")), "2. — mesmo empreendimento simultâneo (pecuária/invest.)"),
    resumo(fp, ops_em(P.classe == "indício: mesmo produto agrícola, sem datas"), "2. — mesmo produto agrícola sem datas"),
    resumo(fp, ops_em((P.tipo == "indício") & ~P.mesmo_banco), "2. — indício com bancos diferentes"),
    resumo(fp, ops_em(P.tipo == "provável legítimo"), "2. (contexto) provável legítimo (ciclos distintos, sequenciais ou empreend. diferentes)"),
    resumo(fp, ops_em(P.tipo == "ruído provável"), "2. (contexto) produtos diferentes"),
]
salva_resumo("cruz2", res)
tab = P.groupby(["classe", "bancos"]).size().unstack(fill_value=0)
tab.to_csv(RES / "cruz2_pares_por_classe_banco.csv")

P.to_parquet(PROC / "cruz2_pares.parquet")
cols = ["safra", "finalidade", "classe", "bancos", "mesmo_car", "sequencial", "ua_ha_par", "frac_menor", "inter_ha", "excesso_area",
        "ref_bacen_a", "nu_ordem_a", "produto_a", "vl_parc_credito_a", "vl_area_informada_a", "dt_emissao_a",
        "ref_bacen_b", "nu_ordem_b", "produto_b", "vl_parc_credito_b", "vl_area_informada_b", "dt_emissao_b",
        "forca"]
P["prioridade"] = np.select([P.classe.str.startswith("indício forte"), ~P.mesmo_banco], [1, 2], 3)
casos = P[P.tipo == "indício"].sort_values(["prioridade", "forca"], ascending=[True, False])
casos[cols].to_csv(RES / "cruz2_casos_indicio.csv", index=False)
top = casos[cols].head(10).copy()
top["ref_bacen_a"] = top.ref_bacen_a.astype(str); top["ref_bacen_b"] = top.ref_bacen_b.astype(str)
top.to_csv(RES / "cruz2_top10.csv", index=False)

print(pd.DataFrame(res)[["cruzamento", "elegiveis", "disparam", "pct_elegiveis", "bb_pct", "demais_pct"]].to_string())
print("\npares por classe × bancos:\n", tab.to_string())
print("\nfração da menor (pares indício):", casos.frac_menor.quantile([.1, .5, .9]).round(3).to_dict(),
      "| excesso de área:", casos.excesso_area.quantile([.1, .5, .9]).round(2).to_dict(),
      "| mesmo CAR:", round(casos.mesmo_car.mean(), 3))
