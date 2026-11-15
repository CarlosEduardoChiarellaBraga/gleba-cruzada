"""Cruzamento 5 — Valor por hectare fora da curva.

valor/ha = VL_PARC_CREDITO / VL_AREA_INFORMADA (crédito por hectare do empreendimento).
Grupo = finalidade × produto × município × safra; ignora grupos com < 20 operações.
Sinal: valor/ha > mediana + 3 × MAD (MAD = mediana dos desvios absolutos, SEM fator 1,4826, como
pedido). Sensibilidade: também com MAD escalado (×1,4826), que é o "z robusto > 3" usual.
Grupos com MAD = 0 (mais da metade com o mesmo valor/ha) não são avaliados (o limiar viraria a
própria mediana).
Elegíveis: área informada > 0,1 ha; custeio (qualquer unidade) ou investimento medido em hectare/UA
(em máquinas e benfeitorias a área não é base de cálculo).
Município: complemento do Sicor; na falta, o município embutido no código do CAR.
Erro de cadastro provável: área informada < 1 ha; ou valor/ha ≈ mediana × fator de unidade
(4,84 alqueire goiano; 2,42 alqueire paulista; 10/100/10.000) ±8%.
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import PROC, RES, banco, load_ops, resumo, salva_resumo  # noqa: E402

MIN_GRUPO = 20
ops = load_ops()
ops["banco"] = ops.is_bb.map(banco)
car_mun = duckdb.sql(f"""SELECT ref_bacen, nu_ordem, min(substr(upper(cd_car),3,7)) AS mun_car
                         FROM '{PROC / 'propriedades_go.parquet'}' WHERE cd_car IS NOT NULL GROUP BY ALL""").df()
ops = ops.merge(car_mun, on=["ref_bacen", "nu_ordem"], how="left")
ops["municipio"] = ops.cd_ibge_municipio.fillna(ops.mun_car)
ops["fonte_municipio"] = np.where(ops.cd_ibge_municipio.notna(), "complemento",
                                  np.where(ops.mun_car.notna(), "CAR", "sem"))

unid = ops.unidade_medida.fillna("")
por_cabeca = unid.str.startswith(("Unidade Animal", "Quantidade"))
unid_ok = unid.str.startswith(("Hectare", "Unidade Animal"))
ele_base = (ops.vl_area_informada > 0.1) & (ops.vl_parc_credito > 0) & \
    ((ops.finalidade == "Custeio") | unid_ok)
chave = ["finalidade", "produto", "metrica", "municipio", "safra"]


def unidade(v):
    for f in (4.84, 2.42, 10, 100, 1e4):
        if abs(np.log(v / f)) < np.log(1.08):
            return True
    return False


def analisa(e: pd.DataFrame) -> pd.DataFrame:
    g = e.groupby(chave).valor_un
    e["n_grupo"] = g.transform("size")
    e["mediana"] = g.transform("median")
    e["mad"] = (e.valor_un - e.mediana).abs().groupby([e[k] for k in chave]).transform("median")
    e["avaliavel"] = (e.n_grupo >= MIN_GRUPO) & (e.mad > 0)
    e["limiar"] = e.mediana + 3 * e.mad
    e["sinal"] = e.avaliavel & (e.valor_un > e.limiar)
    e["sinal_escalado"] = e.avaliavel & (e.valor_un > e.mediana + 3 * 1.4826 * e.mad)
    e["vezes_mediana"] = e.valor_un / e.mediana
    e["z_robusto"] = (e.valor_un - e.mediana) / (1.4826 * e.mad)
    e["unidade_suspeita"] = e.vezes_mediana.map(unidade)
    peq = e.base < np.where(e.metrica == "R$/ha", 1, 0.5)
    e["categoria"] = np.where(~e.sinal, "ok", np.where(peq, "erro de cadastro provável: base minúscula",
                              np.where(e.unidade_suspeita, "erro de cadastro provável: fator de unidade",
                                       "indício: acima de mediana + 3 MAD")))
    e["tipo"] = np.where(e.categoria == "ok", "ok", np.where(e.categoria.str.startswith("indício"), "indício",
                                                              "erro de cadastro provável"))
    e["excesso_rs"] = ((e.valor_un - e.limiar) * e.base).where(e.sinal, 0)
    return e


base = ops[ele_base & ops.municipio.notna()].copy()
# (a) regra literal: R$/ha para tudo
lit = base.assign(metrica="R$/ha", base=base.vl_area_informada)
lit["valor_un"] = lit.vl_parc_credito / lit.base
lit = analisa(lit)
# (b) adaptada: R$/ha para lavoura; R$/UA ou R$/cabeça para pecuária (crédito pecuário é por animal;
#     confinamento tem área pequena e valor/ha legitimamente altíssimo)
ad = base.copy()
pc = por_cabeca.reindex(ad.index) & (ad.vl_quantidade > 0)
ad["metrica"] = np.where(pc, np.where(ad.unidade_medida.str.startswith("Unidade Animal"), "R$/UA", "R$/cabeça"), "R$/ha")
ad["base"] = np.where(pc, ad.vl_quantidade, ad.vl_area_informada)
ad["valor_un"] = ad.vl_parc_credito / ad.base
e = analisa(ad)
av, lav = e[e.avaliavel], lit[lit.avaliavel]

info = dict(
    ops_recorte=len(ops), elegiveis_base=int(ele_base.sum()), com_municipio=int(len(base)),
    municipio_do_complemento=int((base.fonte_municipio == "complemento").sum()),
    municipio_so_do_car=int((base.fonte_municipio == "CAR").sum()),
    grupos_ge20=int(e[e.n_grupo >= MIN_GRUPO].groupby(chave).ngroups),
    grupos_mad_zero=int(e[(e.n_grupo >= MIN_GRUPO) & (e.mad == 0)].groupby(chave).ngroups),
    ops_avaliaveis=int(len(av)),
)
print(info)
res = [resumo(av, av.sinal, "5. Valor por unidade > mediana + 3·MAD (R$/ha lavoura; R$/UA pecuária)", info)]
for tp in ["indício", "erro de cadastro provável"]:
    res.append(resumo(av, av.tipo == tp, f"5. — {tp}"))
for met in ["R$/ha", "R$/UA", "R$/cabeça"]:
    m_ = av.metrica == met
    res.append(resumo(av[m_], av[m_].tipo == "indício", f"5. — indício em {met}"))
res.append(resumo(av, av.sinal_escalado, "5. (sensibilidade) MAD escalado ×1,4826"))
res.append(resumo(lav, lav.sinal, "5. (regra literal) R$/ha para tudo, inclusive pecuária"))
salva_resumo("cruz5", res)
# produtos que mais disparam
pp = av.groupby(["finalidade", "produto", "metrica"]).agg(avaliaveis=("sinal", "size"), disparam=("sinal", "sum"))
pp["pct"] = (100 * pp.disparam / pp.avaliaveis).round(2)
pp.sort_values("disparam", ascending=False).head(15).to_csv(RES / "cruz5_por_produto.csv")

cols = ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "municipio", "fonte_municipio",
        "vl_parc_credito", "vl_area_informada", "vl_quantidade", "metrica", "base", "valor_un", "mediana", "mad", "limiar", "vezes_mediana",
        "z_robusto", "n_grupo", "excesso_rs", "categoria", "tipo"]
e[cols + ["sinal", "sinal_escalado"]].to_parquet(PROC / "cruz5_ops.parquet")
casos = av[av.tipo == "indício"].sort_values("excesso_rs", ascending=False)
casos[cols].to_csv(RES / "cruz5_casos_indicio.csv", index=False)
t = casos[cols].head(10).copy(); t["ref_bacen"] = t.ref_bacen.astype(str)
t.to_csv(RES / "cruz5_top10.csv", index=False)
print(pd.DataFrame(res)[["cruzamento", "elegiveis", "disparam", "pct_elegiveis", "bb_pct", "demais_pct"]].to_string())
print(pp.sort_values("disparam", ascending=False).head(8).to_string())
print(t[["banco", "safra", "produto", "vl_parc_credito", "vl_area_informada", "vl_quantidade", "metrica", "base", "valor_un", "mediana", "vezes_mediana", "n_grupo"]].to_string())
