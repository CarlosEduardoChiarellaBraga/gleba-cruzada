"""Cruzamento 4 — Área incoerente: área calculada da gleba vs VL_AREA_INFORMADA.

razão = área da união das glebas (EPSG:5880) / VL_AREA_INFORMADA. Sinal: razão < 0,5 ou > 2.
Erro de cadastro provável:
  - razão ≈ fator de unidade (±8%): alqueire goiano 4,84; alqueire paulista/mineiro 2,42;
    m²↔ha 10.000; 100; 10 (ou os inversos)
  - glebas repetidas dentro da mesma operação (soma das glebas > 1,5 × área da união)
  - área informada ≤ 0
Indício: o resto (área declarada diferente da desenhada, sem explicação mecânica).
Observação: VL_AREA_FINANC = área informada × crédito/(crédito + recursos próprios); por isso a
comparação é com VL_AREA_INFORMADA.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import PROC, RES, banco, load_fp, resumo, salva_resumo  # noqa: E402

fp = load_fp().drop(columns="geometry")
fp["banco"] = fp.is_bb.map(banco)
fp["razao"] = fp.area_ha / fp.vl_area_informada.where(fp.vl_area_informada > 0)
fp["razao_soma"] = fp.soma_area_glebas_ha / fp.vl_area_informada.where(fp.vl_area_informada > 0)
FAT = {"alqueire goiano (4,84)": 4.84, "alqueire paulista (2,42)": 2.42, "m²↔ha (10.000)": 1e4,
       "×100": 100.0, "×10": 10.0}


def unidade(r):
    if not np.isfinite(r) or r <= 0:
        return None
    for nome, f in FAT.items():
        for v in (f, 1 / f):
            if abs(np.log(r / v)) < np.log(1.08):
                return nome
    return None


fp["sinal"] = (fp.vl_area_informada <= 0) | (fp.razao < 0.5) | (fp.razao > 2)
fp["unidade_suspeita"] = fp.razao.map(unidade)
gl_rep = fp.soma_area_glebas_ha > 1.5 * fp.area_ha
fp["categoria"] = "ok"
c = fp.categoria.copy()
c[fp.sinal & (fp.razao > 2)] = "gleba MAIOR que a área informada (>2×)"
c[fp.sinal & (fp.razao < 0.5)] = "gleba MENOR que a área informada (<0,5×)"
c[fp.sinal & fp.unidade_suspeita.notna()] = "erro de unidade provável"
c[fp.sinal & gl_rep & fp.razao_soma.between(0.5, 2)] = "glebas repetidas na operação"
sem_ref = (fp.finalidade == "Investimento") & ~fp.unidade_medida.fillna("").str.startswith(("Hectare", "Unidade Animal"))
c[fp.sinal & sem_ref & (c.str.startswith("gleba "))] = "investimento sem área de referência (máquina/benfeitoria)"
c[(fp.vl_area_informada > 0) & (fp.vl_area_informada <= 0.1)] = "área informada simbólica (≤ 0,1 ha)"
c[fp.vl_area_informada <= 0] = "área informada zero"
fp["categoria"] = c
fp["sinal"] = fp.sinal | (c != "ok")  # inclui área simbólica com gleba também minúscula (razão ~1)
fp["tipo"] = np.select([c == "ok", c.str.startswith("gleba "), c.str.startswith("investimento sem")],
                       ["ok", "indício", "ruído provável"], "erro de cadastro provável")
fp["forca"] = np.abs(np.log(fp.razao.clip(1e-6))) * np.log10(1 + fp.vl_parc_credito)

res = [resumo(fp, fp.sinal, "4. Área incoerente — qualquer sinal (razão <0,5 ou >2, ou área simbólica)")]
for tp in ["indício", "erro de cadastro provável", "ruído provável"]:
    res.append(resumo(fp, fp.tipo == tp, f"4. — {tp}"))
for cat in sorted(set(c) - {"ok"}):
    res.append(resumo(fp, fp.categoria == cat, f"4. — {cat}"))
# sensibilidade: limiares mais frouxos
res.append(resumo(fp, (fp.razao < 0.8) | (fp.razao > 1.25), "4. (sensibilidade) razão <0,8 ou >1,25"))
salva_resumo("cruz4", res)

cols = ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "unidade_medida", "vl_parc_credito",
        "vl_area_informada", "vl_area_financ", "area_ha", "n_glebas", "razao", "unidade_suspeita", "categoria",
        "tipo", "forca"]
fp[cols].to_parquet(PROC / "cruz4_ops.parquet")
casos = fp[fp.tipo == "indício"].sort_values("forca", ascending=False)
casos[cols].to_csv(RES / "cruz4_casos_indicio.csv", index=False)
t = casos[cols].head(10).copy(); t["ref_bacen"] = t.ref_bacen.astype(str)
t.to_csv(RES / "cruz4_top10.csv", index=False)
print(pd.DataFrame(res)[["cruzamento", "disparam", "pct_elegiveis", "bb_pct", "demais_pct"]].to_string())
print("unidades:", fp.unidade_suspeita.value_counts().to_dict())
print(t[["banco", "produto", "vl_parc_credito", "vl_area_informada", "area_ha", "razao", "categoria"]].to_string())
