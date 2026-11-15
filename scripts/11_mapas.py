"""Etapa 11 — mapas (PNG) dos casos mais fortes.

  mapa1_cruz1_gleba_car.png      gleba × CAR informado (caso mais forte do cruzamento 1)
  mapa2_cruz2_dupla_area.png     duas operações sobre a mesma área em bancos diferentes
  mapa3_cruz3_uc.png             glebas dentro da UC de proteção integral com mais casos
  mapa4_cruz3_agua.png           gleba sobre massa d'água grande (reservatório)
  mapa5_cruz5_valor.png          distribuição do grupo do caso mais forte do cruzamento 5
"""
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import shapely

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import OUT, PROC, RES, load_fp  # noqa: E402

M = OUT / "maps"
AZUL, LARANJA, VERDE, CINZA, CINZA_F, TXT, TXT2 = "#2a78d6", "#eb6834", "#008300", "#b9b8b1", "#f3f2ee", "#0b0b0b", "#52514e"
AQUA = "#1baf7a"
plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "axes.titlelocation": "left"})

fp = load_fp()
fpk = fp.set_index(["ref_bacen", "nu_ordem"])
mun = gpd.read_parquet(PROC / "municipios_go.parquet")
car = gpd.read_parquet(PROC / "car_go.parquet")
car_tree = shapely.STRtree(car.geometry.values)


def limpa_ax(ax):
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_color(CINZA)


def enquadra(ax, geoms, pad_frac=0.25, min_half=800):
    xmin, ymin, xmax, ymax = gpd.GeoSeries(geoms).total_bounds
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    half = max(xmax - xmin, ymax - ymin) / 2 * (1 + pad_frac) + min_half
    ax.set_xlim(cx - half, cx + half); ax.set_ylim(cy - half, cy + half); ax.set_aspect("equal")
    return half


def escala(ax, half):
    km = max(1, int(round(half * 2 / 5 / 1000)))
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    xs, ys = x0 + (x1 - x0) * 0.05, y0 + (y1 - y0) * 0.05
    ax.plot([xs, xs + km * 1000], [ys, ys], color=TXT, lw=2)
    ax.text(xs, ys + (y1 - y0) * 0.02, f"{km} km", fontsize=8, color=TXT)


def car_contexto(ax, geom, raio):
    js = car_tree.query(geom.buffer(raio), predicate="intersects")
    gpd.GeoSeries(car.geometry.values[js]).plot(ax=ax, facecolor="none", edgecolor=CINZA, linewidth=0.5)


def rodape(fig, txt):
    fig.text(0.01, 0.01, txt, fontsize=8, color=TXT2)


def brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


# ================================================================ 1. gleba × CAR
t1 = pd.read_csv(RES / "cruz1_top10.csv")
c1 = pd.read_parquet(PROC / "cruz1_ops.parquet")
r = t1.iloc[0]
row = c1[(c1.ref_bacen == r.ref_bacen) & (c1.nu_ordem == r.nu_ordem)].iloc[0]
g = fpk.loc[(r.ref_bacen, r.nu_ordem)].geometry
inf = car[car.cod_norm.isin(list(row.cars))]
melhor = car[car.cod_norm == row.melhor_car]
fig, axs = plt.subplots(1, 3, figsize=(15, 5.6), gridspec_kw=dict(width_ratios=[1.2, 1, 1]))
ax = axs[0]
mun.plot(ax=ax, facecolor=CINZA_F, edgecolor="white", linewidth=0.3)
cg, ci = g.centroid, inf.union_all().centroid
ax.plot([cg.x, ci.x], [cg.y, ci.y], color=TXT2, lw=1, ls="--")
ax.plot(cg.x, cg.y, "o", ms=9, mfc=AZUL, mec="white", mew=1.5)
ax.plot(ci.x, ci.y, "s", ms=9, mfc=LARANJA, mec="white", mew=1.5)
ax.set_title(f"Distância entre gleba e CAR informado: {row.dist_borda_km:,.0f} km")
ax.set_axis_off()
ax = axs[1]
car_contexto(ax, g, 3000)
melhor.plot(ax=ax, facecolor=CINZA_F, edgecolor=TXT2, linewidth=1.2)
gpd.GeoSeries([g]).plot(ax=ax, facecolor=AZUL, edgecolor=AZUL, alpha=0.85)
h = enquadra(ax, [g, melhor.union_all()], 0.2); escala(ax, h); limpa_ax(ax)
ax.set_title(f"Onde a gleba está: dentro de outro imóvel\n({row.melhor_car_frac:.0%} da gleba coberta por um CAR diferente)")
ax = axs[2]
car_contexto(ax, inf.union_all(), 3000)
inf.plot(ax=ax, facecolor=CINZA_F, edgecolor=LARANJA, linewidth=1.6)
h = enquadra(ax, [inf.union_all()], 0.3); escala(ax, h); limpa_ax(ax)
ax.set_title("CAR informado na operação\n(nenhuma sobreposição com a gleba)")
fig.legend(handles=[Patch(fc=AZUL, label="gleba da operação (Sicor)"), Patch(fc=CINZA_F, ec=TXT2, label="imóvel do SICAR que contém a gleba"),
                    Patch(fc=CINZA_F, ec=LARANJA, label="CAR informado na operação"), Patch(fc="none", ec=CINZA, label="outros imóveis do SICAR")],
           loc="upper right", ncol=4, frameon=False, bbox_to_anchor=(0.99, 0.99))
fig.suptitle(f"Cruzamento 1 · operação {r.ref_bacen}/{r.nu_ordem} · {r.banco} · {r.safra} · {r.finalidade} {r.produto} · "
             f"{brl(r.vl_parc_credito)} · {r.area_ha:,.0f} ha", x=0.01, ha="left", fontsize=12, weight="bold", y=0.93)
rodape(fig, "Fontes: BCB/Sicor (gleba, CAR informado), SICAR/GO (imóveis, retrato de nov/2026), IBGE. SIRGAS 2000 / Brazil Polyconic.")
fig.subplots_adjust(top=0.78, bottom=0.06, wspace=0.08)
fig.savefig(M / "mapa1_cruz1_gleba_car.png", dpi=150); plt.close(fig)
print("mapa 1 ok")

# ================================================================ 2. dupla área (bancos diferentes)
P = pd.read_parquet(PROC / "cruz2_pares.parquet")
cand = P[(P.tipo == "indício") & ~P.mesmo_banco]
agr = cand[cand.agricola]
r = (agr if len(agr) else cand).sort_values("forca", ascending=False).iloc[0]
ga = fpk.loc[(r.ref_bacen_a, r.nu_ordem_a)].geometry
gb = fpk.loc[(r.ref_bacen_b, r.nu_ordem_b)].geometry
fig, ax = plt.subplots(figsize=(9, 8))
car_contexto(ax, ga, 2500)
gpd.GeoSeries([ga]).plot(ax=ax, facecolor=AZUL, edgecolor=AZUL, alpha=0.35, linewidth=1.5)
gpd.GeoSeries([gb]).plot(ax=ax, facecolor="none", edgecolor=LARANJA, linewidth=2.2, linestyle="--")
h = enquadra(ax, [ga, gb], 0.5); escala(ax, h); limpa_ax(ax)
ax.legend(handles=[Patch(fc=AZUL, alpha=0.35, ec=AZUL, label=f"op. A {r.ref_bacen_a}/{r.nu_ordem_a} · {r.nome_if_a.strip()[:24]} · "
                         f"{pd.Timestamp(r.dt_emissao_a):%d/%m/%Y} · {brl(r.vl_parc_credito_a)} · {r.vl_area_informada_a:,.0f} ha inf."),
                   Line2D([], [], color=LARANJA, lw=2.2, ls="--", label=f"op. B {r.ref_bacen_b}/{r.nu_ordem_b} · {r.nome_if_b.strip()[:24]} · "
                          f"{pd.Timestamp(r.dt_emissao_b):%d/%m/%Y} · {brl(r.vl_parc_credito_b)} · {r.vl_area_informada_b:,.0f} ha inf."),
                   Patch(fc="none", ec=CINZA, label="imóveis do SICAR")],
          loc="upper left", bbox_to_anchor=(0, -0.02), frameon=False, fontsize=8.5)
fig.suptitle(f"Cruzamento 2 · mesma área, mesma safra ({r.safra}), {r.finalidade.lower()} de {r.produto_a.lower()}, "
             f"bancos diferentes", x=0.02, ha="left", fontsize=12, weight="bold")
fig.text(0.02, 0.925, f"Sobreposição: {r.frac_menor:.0%} da menor gleba · área declarada somada = {r.excesso_area:.2f}× a área real · "
         f"{r.classe}", fontsize=9, color=TXT2)
rodape(fig, "Fontes: BCB/Sicor, SICAR/GO. SIRGAS 2000 / Brazil Polyconic.")
fig.subplots_adjust(top=0.9, bottom=0.17)
fig.savefig(M / "mapa2_cruz2_dupla_area.png", dpi=150); plt.close(fig)
print("mapa 2 ok")

# ================================================================ 3. UC proteção integral
c3 = pd.read_parquet(PROC / "cruz3_ops.parquet")
uc = gpd.read_parquet(PROC / "uc_go.parquet")
top_uc = c3[(c3.uc_PI_frac > 0.1) & (c3.uc_nome != "")].uc_nome.value_counts().index[0]
u = uc[uc.nome_uc == top_uc]
dentro = c3[(c3.uc_PI_frac > 0.1) & (c3.uc_nome == top_uc)]
gd = fp.merge(dentro[["ref_bacen", "nu_ordem"]], on=["ref_bacen", "nu_ordem"])
fig, ax = plt.subplots(figsize=(10, 8.5))
car_contexto(ax, u.union_all(), 1000)
u.plot(ax=ax, facecolor=VERDE, alpha=0.12, edgecolor=VERDE, linewidth=1.6)
gd.plot(ax=ax, facecolor=AZUL, edgecolor="white", linewidth=0.4)
h = enquadra(ax, [u.union_all()], 0.1); escala(ax, h); limpa_ax(ax)
ax.legend(handles=[Patch(fc=VERDE, alpha=0.3, ec=VERDE, label=f"{top_uc.title()} (CNUC; criação {u.cria_ano.iloc[0]})"),
                   Patch(fc=AZUL, label=f"glebas financiadas com > 10% dentro da UC ({len(gd)} operações)"),
                   Patch(fc="none", ec=CINZA, label="imóveis do SICAR")], loc="upper left", frameon=True, fontsize=8.5)
nimo = len({c for lst in dentro.merge(fp[["ref_bacen", "nu_ordem", "cars"]], on=["ref_bacen", "nu_ordem"]).cars.dropna() for c in lst})
fig.suptitle(f"Cruzamento 3 · crédito rural dentro de UC de proteção integral", x=0.02, ha="left", fontsize=12, weight="bold")
fig.text(0.02, 0.925, f"{len(gd)} operações · {nimo} imóveis (CAR) · {brl(dentro.vl_parc_credito.sum())} no total · "
         f"{(dentro.banco == 'BB').mean():.0%} BB · safras 2021/22–2024/25", fontsize=9, color=TXT2)
rodape(fig, "Fontes: BCB/Sicor, MMA/CNUC 2025-08, SICAR/GO. Parques com regularização fundiária pendente ainda contêm imóveis privados.")
fig.subplots_adjust(top=0.9, bottom=0.05)
fig.savefig(M / "mapa3_cruz3_uc.png", dpi=150); plt.close(fig)
print("mapa 3 ok")

# ================================================================ 4. água grande
ag = gpd.read_parquet(PROC / "agua_go.parquet")
w = c3[c3.motivos.str.contains("água grande")].sort_values("forca", ascending=False)
r = w.iloc[0]
g = fpk.loc[(r.ref_bacen, r.nu_ordem)].geometry
fig, ax = plt.subplots(figsize=(9, 8))
car_contexto(ax, g, 3000)
js = shapely.STRtree(ag.geometry.values).query(g.buffer(4000), predicate="intersects")
ag.iloc[js].plot(ax=ax, facecolor=AQUA, alpha=0.35, edgecolor=AQUA, linewidth=0.6)
gpd.GeoSeries([g]).plot(ax=ax, facecolor="none", edgecolor=AZUL, linewidth=2.2)
h = enquadra(ax, [g], 0.8, 1500); escala(ax, h); limpa_ax(ax)
nome_ag = ag.iloc[js].sort_values("area_ha", ascending=False).nmoriginal.iloc[0].strip() or "massa d'água natural"
ax.legend(handles=[Line2D([], [], color=AZUL, lw=2.2, label="gleba da operação"),
                   Patch(fc=AQUA, alpha=0.35, ec=AQUA, label=f"massa d'água (ANA) — {nome_ag}"),
                   Patch(fc="none", ec=CINZA, label="imóveis do SICAR")], loc="upper left", frameon=True, fontsize=8.5)
fig.suptitle(f"Cruzamento 3 · gleba sobre massa d'água · operação {r.ref_bacen}/{r.nu_ordem}", x=0.02, ha="left",
             fontsize=12, weight="bold")
fig.text(0.02, 0.925, f"{r.banco} · {r.safra} · {r.finalidade} {r.produto} · {brl(r.vl_parc_credito)} · {r.area_ha:,.0f} ha · "
         f"{r.aguag_frac:.0%} da gleba sobre água", fontsize=9, color=TXT2)
rodape(fig, "Fontes: BCB/Sicor, ANA/SNIRH (massas d'água; contorno de reservatório pode estar na cota máxima), SICAR/GO.")
fig.subplots_adjust(top=0.9, bottom=0.05)
fig.savefig(M / "mapa4_cruz3_agua.png", dpi=150); plt.close(fig)
print("mapa 4 ok")

# ================================================================ 5. valor por unidade (gráfico)
c5 = pd.read_parquet(PROC / "cruz5_ops.parquet")
t5 = pd.read_csv(RES / "cruz5_top10.csv")
r = t5.iloc[0]
grp = c5[(c5.finalidade == r.finalidade) & (c5.produto == r.produto) & (c5.metrica == r.metrica) &
         (c5.municipio.astype(str) == str(r.municipio)) & (c5.safra == r.safra)].copy()
nome_mun = mun.set_index("CD_MUN").NM_MUN.get(str(r.municipio), str(r.municipio))
grp = grp.sort_values("valor_un")
fig, ax = plt.subplots(figsize=(10, 4.8))
rng = np.random.default_rng(1)
y = rng.uniform(-0.25, 0.25, len(grp))
cor = np.where(grp.sinal, LARANJA, AZUL)
ax.scatter(grp.valor_un, y, s=36, c=cor, edgecolor="white", linewidth=0.8, zorder=3)
alvo = (grp.ref_bacen == r.ref_bacen) & (grp.nu_ordem == r.nu_ordem)
ax.scatter(grp.valor_un[alvo], y[alvo.values], s=140, facecolor="none", edgecolor=TXT, linewidth=1.5, zorder=4)
med, lim = grp.mediana.iloc[0], grp.limiar.iloc[0]
ax.axvline(med, color=TXT2, lw=1); ax.axvline(lim, color=LARANJA, lw=1, ls="--")
ax.text(med, 0.42, f" mediana {brl(med)}", color=TXT2, fontsize=8.5)
ax.text(lim, 0.34, f" mediana + 3·MAD = {brl(lim)}", color=TXT, fontsize=8.5)
ax.annotate(f"op. {r.ref_bacen}/{r.nu_ordem}\n{brl(r.vl_parc_credito)} · {r.base:,.0f} {r.metrica.split('/')[1]}\n"
            f"{brl(r.valor_un)} por {r.metrica.split('/')[1]} ({r.vezes_mediana:.1f}× a mediana)",
            (r.valor_un, y[alvo.values][0]), xytext=(-170, -55), textcoords="offset points", fontsize=8.5,
            arrowprops=dict(arrowstyle="-", color=TXT2))
ax.set_ylim(-0.5, 0.5); ax.set_yticks([])
ax.set_xlabel(f"crédito por {r.metrica.split('/')[1]} ({r.metrica})")
ax.spines[["left", "top", "right"]].set_visible(False)
ax.grid(axis="x", color="#e6e5e0", lw=0.6); ax.set_axisbelow(True)
ax.legend(handles=[Line2D([], [], marker="o", ls="", mfc=AZUL, mec="white", ms=7, label="dentro da curva"),
                   Line2D([], [], marker="o", ls="", mfc=LARANJA, mec="white", ms=7, label="acima do limiar")],
          loc="upper right", frameon=False)
fig.suptitle(f"Cruzamento 5 · {r.finalidade} {r.produto.lower()} · {nome_mun} · safra {r.safra} · {len(grp)} operações",
             x=0.02, ha="left", fontsize=12, weight="bold")
rodape(fig, "Fonte: BCB/Sicor. Cada ponto é uma operação do grupo (finalidade × produto × município × safra); dispersão vertical só para legibilidade.")
fig.subplots_adjust(top=0.88, bottom=0.2)
fig.savefig(M / "mapa5_cruz5_valor.png", dpi=150); plt.close(fig)
print("mapa 5 ok")
