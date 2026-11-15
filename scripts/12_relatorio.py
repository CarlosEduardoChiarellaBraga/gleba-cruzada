"""Etapa 12 — monta outputs/relatorio.md a partir dos resultados dos cruzamentos.

Também gera outputs/cruzamentos/convergencia.csv (operações com indício em ≥ 2 cruzamentos).
"""
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cruz_common import N_TOTAL, OUT, PROC, RES  # noqa: E402

K = ["ref_bacen", "nu_ordem"]
L: list[str] = []
def P(*a):
    L.append("".join(str(x) for x in a))


def R(n):
    return pd.DataFrame(json.load(open(RES / f"cruz{n}_resumo.json")))


def linha(df, nome):
    return df[df.cruzamento == nome].iloc[0]


def fmt(v, d=0):
    if pd.isna(v):
        return ""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tab_resumo(df, linhas=None):
    d = df if linhas is None else df[df.cruzamento.isin(linhas)]
    t = pd.DataFrame({
        "regra / categoria": d.cruzamento.str.replace(r"^\d\. (— )?", "", regex=True),
        "disparam": d.disparam.map(fmt),
        "% elegíveis": d.pct_elegiveis.map(lambda v: fmt(v, 2)),
        "% do recorte": d.pct_recorte.map(lambda v: fmt(v, 2)),
        "R$ mi": d.valor_disparos_rs_mi.map(lambda v: fmt(v, 1)),
        "BB": [f"{fmt(a)} ({fmt(b, 2)}%)" for a, b in zip(d.bb_disparam, d.bb_pct)],
        "demais": [f"{fmt(a)} ({fmt(b, 2)}%)" for a, b in zip(d.demais_disparam, d.demais_pct)],
    })
    return t.to_markdown(index=False, disable_numparse=True)


def tab_top(path, cols, nomes, fmts=None):
    t = pd.read_csv(path)
    t = t[cols].copy()
    for c, f in (fmts or {}).items():
        t[c] = t[c].map(f)
    t.columns = nomes
    t.insert(0, "#", range(1, len(t) + 1))
    return t.to_markdown(index=False, disable_numparse=True)


pct = lambda v: f"{100 * v:.0f}%" if pd.notna(v) else ""  # noqa: E731
brl = lambda v: fmt(v)  # noqa: E731
km = lambda v: fmt(v, 1)  # noqa: E731

# ------------------------------------------------------------------ dados gerais
ops = duckdb.sql(f"SELECT * FROM '{PROC / 'operacoes_go.parquet'}'").df()
fp = pd.read_parquet(PROC / "op_footprint.parquet", columns=K)
n_gl = len(fp)
bb = ops.is_bb
cov = pd.DataFrame({
    "": ["Operações (custeio + investimento)", "Valor (R$ bi)", "Com gleba (polígono)", "Com CAR informado",
         "Com município no complemento"],
    "Total": [fmt(len(ops)), fmt(ops.vl_parc_credito.sum() / 1e9, 1),
              f"{fmt(n_gl)} ({fmt(100 * n_gl / len(ops), 1)}%)",
              f"{fmt(duckdb.sql(f'''SELECT count(DISTINCT (ref_bacen, nu_ordem)) FROM '{PROC / 'propriedades_go.parquet'}' WHERE cd_car IS NOT NULL''').fetchall()[0][0])}",
              fmt(ops.cd_ibge_municipio.notna().sum())],
})
gl_set = set(zip(fp.ref_bacen, fp.nu_ordem))
ops["tem_gleba"] = [(r, n) in gl_set for r, n in zip(ops.ref_bacen, ops.nu_ordem)]
car_set = set(map(tuple, duckdb.sql(f"""SELECT DISTINCT ref_bacen, nu_ordem FROM '{PROC / 'propriedades_go.parquet'}'
                                        WHERE cd_car IS NOT NULL""").fetchall()))
ops["tem_car"] = [(r, n) in car_set for r, n in zip(ops.ref_bacen, ops.nu_ordem)]
cov.loc[3, "Total"] = f"{fmt(ops.tem_car.sum())} ({fmt(100 * ops.tem_car.mean(), 1)}%)"
for nome, m in (("BB", bb), ("Demais", ~bb)):
    o = ops[m]
    cov[nome] = [fmt(len(o)), fmt(o.vl_parc_credito.sum() / 1e9, 1),
                 f"{fmt(o.tem_gleba.sum())} ({fmt(100 * o.tem_gleba.mean(), 1)}%)",
                 f"{fmt(o.tem_car.sum())} ({fmt(100 * o.tem_car.mean(), 1)}%)", fmt(o.cd_ibge_municipio.notna().sum())]
val = pd.read_csv(OUT / "validade_geometrias.csv")

r1, r2, r3, r4, r5 = R(1), R(2), R(3), R(4), R(5)

# ------------------------------------------------------------------ convergência
c1 = pd.read_parquet(PROC / "cruz1_ops.parquet"); c1["C1"] = c1.tipo == "indício"
c2p = pd.read_parquet(PROC / "cruz2_pares.parquet")
forte2 = c2p[(c2p.tipo == "indício") & (~c2p.mesmo_banco | c2p.agricola)]  # exclui pecuária no mesmo banco
s2 = set(zip(forte2.ref_bacen_a, forte2.nu_ordem_a)) | set(zip(forte2.ref_bacen_b, forte2.nu_ordem_b))
c3 = pd.read_parquet(PROC / "cruz3_ops.parquet"); c3["C3"] = c3.sinal
n_longe = int(((c1.tipo == "indício") & (c1.dist_borda_km > 5)).sum())
pec = c2p[c2p.classe.str.startswith("indício: mesmo empreendimento")]
pct_bbbb = 100 * (pec.bancos == "BB×BB").mean()
pct_mesmo_car = 100 * pec.mesmo_car.mean()
c4 = pd.read_parquet(PROC / "cruz4_ops.parquet"); c4["C4"] = c4.tipo == "indício"
c5 = pd.read_parquet(PROC / "cruz5_ops.parquet"); c5["C5"] = c5.tipo == "indício"
cv = ops[K + ["is_bb", "safra", "finalidade", "produto", "vl_parc_credito", "cd_ibge_municipio"]]
for d, c in ((c1, "C1"), (c3, "C3"), (c4, "C4"), (c5, "C5")):
    cv = cv.merge(d[K + [c]], on=K, how="left")
cv["C2"] = [(r, n) in s2 for r, n in zip(cv.ref_bacen, cv.nu_ordem)]
for c in ["C1", "C2", "C3", "C4", "C5"]:
    cv[c] = cv[c].fillna(False).astype(bool)
cv["n_cruzamentos"] = cv[["C1", "C2", "C3", "C4", "C5"]].sum(axis=1)
cv = cv.merge(c1[K + ["categoria", "dist_borda_km"]].rename(columns={"categoria": "c1_categoria"}), on=K, how="left") \
       .merge(c3[K + ["motivos"]].rename(columns={"motivos": "c3_motivos"}), on=K, how="left") \
       .merge(c5[K + ["metrica", "vezes_mediana"]], on=K, how="left")
conv = cv[cv.n_cruzamentos >= 2].sort_values(["n_cruzamentos", "vl_parc_credito"], ascending=False)
conv.assign(banco=conv.is_bb.map({True: "BB", False: "Demais"})).drop(columns="is_bb") \
    .to_csv(RES / "convergencia.csv", index=False)
combos = conv[["C1", "C2", "C3", "C4", "C5"]].apply(lambda r: " + ".join(c for c in r.index if r[c]), axis=1).value_counts()

# ================================================================== RELATÓRIO
P("# Crédito rural em Goiás: triagem por cruzamento de bases públicas\n")
P("*Exploração pessoal de fim de semana (nov/2026). Triagem, não acusação: cada caso listado é uma "
  "inconsistência entre bases públicas, com várias explicações possíveis além de irregularidade. "
  "Sem nomes nem CPF; operações identificadas pelo `REF_BACEN` mascarado do BCB.*\n")

P("## Resumo\n")
P(f"- **Recorte:** {fmt(len(ops))} operações de custeio e investimento em Goiás, safras 2021/22–2024/25, "
  f"R$ {fmt(ops.vl_parc_credito.sum() / 1e9, 1)} bi. BB = {100 * bb.mean():.0f}% das operações.")
P(f"- **Só {100 * n_gl / len(ops):.0f}% das operações têm gleba publicada** "
  f"({100 * ops[ops.tem_gleba].vl_parc_credito.sum() / ops.vl_parc_credito.sum():.0f}% do valor), com viés forte para "
  "pequeno produtor, Pronaf, pecuária e BB. Os cruzamentos geométricos valem para esse subconjunto.")
P(f"- **Sinais que parecem reais:** gleba fora do CAR informado ({fmt(linha(r1, '1. Gleba × CAR — indício').disparam)} "
  f"operações); crédito dentro de UC de proteção integral ({fmt(linha(r3, '3. — UC proteção integral > 10% (indício)').disparam)}, "
  f"concentradas no PE da Serra Dourada) e em área embargada vigente "
  f"({fmt(linha(r3, '3. — embargo IBAMA vigente (polígono > 10%) antes do contrato (indício)').disparam)} por polígono); "
  f"mesma área financiada na mesma safra em bancos diferentes "
  f"({fmt(linha(r2, '2. — indício com bancos diferentes').disparam)}).")
P("- **Ruído ou erro de cadastro:** área incoerente (quase tudo área simbólica de 0,01 ha ou alqueire "
  "digitado como hectare), fora do município (o Sicor já valida), água (aquicultura, arroz de várzea, "
  "lagoa sazonal), sobreposição em pecuária no mesmo banco (a área é reaproveitada; o crédito é por "
  "cabeça) e boa parte do valor/ha (confinamento, teto de R$ 3 mi).")
P(f"- **Convergência:** {fmt(len(conv))} operações acumulam indício em ≥ 2 cruzamentos — é a lista de "
  "triagem mais útil (`cruzamentos/convergencia.csv`).")
P("- **Vale um projeto maior?** Vale um **passo intermediário**, não um projeto grande só com dados "
  "públicos — ver a conclusão.\n")

P("## 1. Recorte e cobertura de localização\n")
P(cov.to_markdown(index=False, disable_numparse=True), "\n")
P("O BCB publica gleba, CAR e município para o mesmo subconjunto de operações (toda operação com gleba tem "
  "CAR e município). A cobertura é de 56% para pequenos produtores e 22–27% para médios e grandes; 20% no "
  "custeio de soja; 10% acima de R$ 5 mi. A família `*_CONTRAT` (lista de pontos) só cobre contratos a "
  "partir de nov/2025. Detalhes em `reconhecimento.md`.\n")
P("**Consequência para BB × demais:** o BB tem 40% das operações com gleba; os demais, 17%. As taxas abaixo "
  "são sempre sobre as operações **elegíveis** de cada grupo, mas os dois grupos têm perfis diferentes "
  "(produto, porte, região), então diferenças pequenas de taxa não devem ser lidas como diferença de "
  "comportamento entre bancos.\n")

P("## 2. Método\n")
P("- Tudo reprojetado para **SIRGAS 2000 / Brazil Polyconic (EPSG:5880)** antes de área e distância.")
P("- Geometrias inválidas corrigidas com `make_valid` (só a parte areal é mantida):\n")
P(val.rename(columns={"camada": "camada", "feicoes": "feições", "nulas_ou_vazias": "nulas/vazias",
                      "invalidas_corrigidas": "inválidas corrigidas", "descartadas": "descartadas",
                      "pct_invalidas": "% inválidas"}).to_markdown(index=False, disable_numparse=True), "\n")
P("- Glebas de uma mesma operação são unidas (polígono da operação). Glebas do Sicor vêm em WKT com Z "
  "implícito; lidas com GEOS. Nenhuma gleba do recorte veio como ponto.")
P("- Cada disparo é classificado em **indício**, **erro de cadastro provável** (ex.: coordenada trocada, "
  "unidade errada, CAR vizinho, área simbólica) ou **ruído provável** (situação legítima comum). "
  "**Coordenada trocada** (lat/lon invertidos ou sinal) foi testada: **0 casos** no recorte — o Sicor "
  "parece rejeitar coordenada fora do município na entrada.")
P("- Limiares: sobreposição com camada restritiva > 10% da gleba; gleba×CAR < 50%; dupla área > 50% da "
  "menor gleba; área fora de [0,5; 2]; valor > mediana + 3·MAD em grupos ≥ 20.")
P("- SICAR é um retrato de nov/2026: CAR retificado, cancelado ou criado depois do contrato pode gerar "
  "divergência sem irregularidade. Embargos IBAMA: só contam se anteriores à emissão, não cancelados e sem "
  "desembargo antes do contrato (nome/CPF descartados na leitura).\n")

# ---------------------------------------------------------------- C1
P("## 3. Cruzamento 1 — Gleba × CAR informado\n")
P(f"Elegíveis: {fmt(r1.elegiveis.iloc[0])} operações com gleba e CAR. Mediana da sobreposição gleba∩CAR: "
  "99,8%; 5% das operações têm sobreposição ~0.\n")
P(tab_resumo(r1), "\n")
P("**10 casos mais fortes** (indício; ordenados por falta de sobreposição × distância × valor):\n")
P(tab_top(RES / "cruz1_top10.csv",
          ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "vl_parc_credito", "area_ha", "sobrep",
           "dist_borda_km", "melhor_car_frac", "categoria"],
          ["REF_BACEN", "ordem", "banco", "safra", "finalidade", "produto", "valor R$", "gleba ha", "gleba∩CAR",
           "dist. CAR km", "coberta por outro CAR", "categoria"],
          {"vl_parc_credito": brl, "area_ha": lambda v: fmt(v), "sobrep": pct, "dist_borda_km": km,
           "melhor_car_frac": pct, "produto": lambda s: s[:28]}), "\n")
P("![Cruzamento 1](maps/mapa1_cruz1_gleba_car.png)\n")
P("**Leitura.** Metade dos disparos é erro de cadastro provável: a gleba cai num CAR **vizinho** ao informado "
  "(mesma fazenda registrada em mais de um CAR, ou CAR errado na hora do cadastro). O núcleo interessante "
  f"são as glebas inteiras dentro de **outro imóvel** e as glebas fora de qualquer CAR; {fmt(n_longe)} delas "
  f"ficam a mais de 5 km do CAR informado (as do topo, a centenas de km). Explicações benignas: produtor que cita o CAR de outra fazenda sua, "
  "arrendamento, CAR retificado depois (52% dos indícios têm CAR atualizado após o contrato, contra 30% "
  "dos casos ok). Ainda assim, é o cruzamento com melhor relação sinal/ruído.\n")

# ---------------------------------------------------------------- C2
P("## 4. Cruzamento 2 — Mesma área financiada duas vezes\n")
P("Pares de operações (REF_BACEN diferentes) na mesma safra e finalidade com sobreposição > 50% da menor "
  "gleba. A regra original foi refinada: **produtos diferentes** (soja → milho safrinha, lavoura + bovinos) "
  "são sucessão/consórcio; **mesmo produto em ciclos que não se sobrepõem** (datas de plantio/colheita) é "
  "provável legítimo; em pecuária/investimento, exige-se o **mesmo código de empreendimento** e contratos "
  "**simultâneos** (um não venceu antes do outro).\n")
P(tab_resumo(r2), "\n")
tb = pd.read_csv(RES / "cruz2_pares_por_classe_banco.csv")
P("Pares por classe e combinação de bancos:\n")
P(tb.rename(columns={"classe": "classe do par"}).to_markdown(index=False, disable_numparse=True), "\n")
P("**10 pares mais fortes** (prioridade: agrícola mesmo ciclo → bancos diferentes → resto):\n")
P(tab_top(RES / "cruz2_top10.csv",
          ["safra", "classe", "bancos", "frac_menor", "excesso_area", "ref_bacen_a", "produto_a", "vl_parc_credito_a",
           "ref_bacen_b", "produto_b", "vl_parc_credito_b"],
          ["safra", "classe", "bancos", "sobrep.", "área decl./real", "op. A", "produto A", "R$ A", "op. B",
           "produto B", "R$ B"],
          {"frac_menor": pct, "excesso_area": lambda v: fmt(v, 2), "vl_parc_credito_a": brl, "vl_parc_credito_b": brl,
           "classe": lambda s: s.split(":")[0] + ":" + s.split(":")[1][:38], "produto_a": lambda s: s[:22],
           "produto_b": lambda s: s[:22]}), "\n")
P("![Cruzamento 2](maps/mapa2_cruz2_dupla_area.png)\n")
P("**Leitura.** Na agricultura, dupla área no mesmo ciclo é **quase inexistente** (5 pares, todos pequenos e "
  f"de hortaliças/milho, que têm vários plantios por ano). O volume vem da **pecuária**: {pct_bbbb:.0f}% desses "
  f"pares são BB × BB e {pct_mesmo_car:.0f}% estão no mesmo CAR: o produtor toma vários custeios de bovinos na mesma safra e repete a gleba do pasto "
  "em todos — o crédito é por cabeça, então isso é estrutural, não dupla área. O subconjunto que vale olhar é "
  f"o de **bancos diferentes** ({fmt(linha(r2, '2. — indício com bancos diferentes').disparam)} operações), "
  "como o pivô de café financiado por dois bancos na mesma safra (mapa). *Atenção à taxa BB × demais nessa "
  "linha:* todo par entre bancos envolve uma operação de outro banco, e o BB tem 77% das operações; a taxa "
  "dos demais sai maior por construção, não por comportamento.\n")

# ---------------------------------------------------------------- C3
P("## 5. Cruzamento 3 — Geometria impossível\n")
P("Sobreposição > 10% da gleba com: massa d'água grande (≥ 100 ha ou natural), terra indígena, UC de "
  "proteção integral ou RPPN (UC criada antes do contrato), embargo IBAMA vigente na data da emissão; e "
  "gleba com < 50% no município declarado.\n")
P(tab_resumo(r3), "\n")
P("Colunas extra no CSV (`cruzamentos/cruz3_resumo.csv`): imóveis (CAR) e áreas distintas — várias "
  "operações repetem a mesma área em safras diferentes.\n")
P("**10 casos mais fortes:**\n")
P(tab_top(RES / "cruz3_top10.csv",
          ["ref_bacen", "nu_ordem", "banco", "safra", "produto", "vl_parc_credito", "area_ha", "motivos", "uc_PI_frac",
           "uc_nome", "aguag_frac", "emb_frac"],
          ["REF_BACEN", "ordem", "banco", "safra", "produto", "valor R$", "gleba ha", "motivo", "% em UC PI", "UC",
           "% água", "% embargo"],
          {"vl_parc_credito": brl, "area_ha": lambda v: fmt(v, 1), "uc_PI_frac": pct, "aguag_frac": pct,
           "emb_frac": pct, "produto": lambda s: s[:22], "uc_nome": lambda s: (s or "").title()[:34]}), "\n")
P("![Cruzamento 3 — UC](maps/mapa3_cruz3_uc.png)\n")
P("![Cruzamento 3 — água](maps/mapa4_cruz3_agua.png)\n")
P("**Leitura.** Dispara pouco (0,15% das operações com gleba). Terra indígena: zero. **UC de proteção "
  "integral** é o sinal mais nítido, mas concentrado: 43 das 63 operações estão no **Parque Estadual da Serra "
  "Dourada**, em 26 imóveis, financiados repetidamente ao longo das safras. Parques com regularização "
  "fundiária pendente ainda têm imóveis privados dentro; a pergunta é se o crédito obedeceu às restrições do "
  "MCR para UC (conferir a redação vigente na data de cada contrato) — e se o limite do CNUC está correto. "
  "**Embargos vigentes** são poucos (9 por polígono, 18 por ponto), mas são o caso mais direto: embargo "
  "anterior ao contrato e sem desembargo. **Água** é quase todo ruído: aquicultura (esperado), arroz de "
  "várzea, lagoas sazonais em pasto e bordas de reservatório (o contorno da ANA pode estar na cota máxima). "
  "**Fora do município**: 53 casos, quase todos em município vizinho (borda) — o Sicor valida isso.\n")

# ---------------------------------------------------------------- C4
P("## 6. Cruzamento 4 — Área incoerente\n")
P("Razão = área calculada da gleba (união) ÷ `VL_AREA_INFORMADA`; sinal se < 0,5 ou > 2. Erro de cadastro "
  "provável quando a razão ≈ fator de unidade (4,84 alqueire goiano; 2,42 alqueire paulista; 10/100/10.000) "
  "ou quando a área informada é simbólica (≤ 0,1 ha).\n")
P(tab_resumo(r4), "\n")
P("**10 casos mais fortes** (indício):\n")
P(tab_top(RES / "cruz4_top10.csv",
          ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "vl_parc_credito", "vl_area_informada",
           "area_ha", "razao"],
          ["REF_BACEN", "ordem", "banco", "safra", "finalidade", "produto", "valor R$", "área informada ha",
           "gleba ha", "razão"],
          {"vl_parc_credito": brl, "vl_area_informada": lambda v: fmt(v, 2), "area_ha": lambda v: fmt(v, 1),
           "razao": lambda v: fmt(v, 1), "produto": lambda s: s[:26]}), "\n")
P("**Leitura.** É controle de qualidade, não detector: a mediana da razão é 1,003 e 98,6% das operações "
  "ficam entre 0,8 e 1,25 — o Sicor parece derivar ou validar a área a partir do polígono. Dos disparos, a "
  "maioria é área simbólica (0,01 ha) ou unidade trocada. Sobram ~290 glebas desenhadas muito maiores que a "
  "área declarada — o caso inverso do que seria vantajoso para o tomador (declarar menos área que a desenhada "
  "não aumenta o crédito), o que reforça a leitura de erro.\n")

# ---------------------------------------------------------------- C5
i5 = r5.iloc[0]
P("## 7. Cruzamento 5 — Valor por unidade fora da curva\n")
P(f"Grupos finalidade × produto × município × safra com ≥ 20 operações; sinal se valor > mediana + 3·MAD "
  f"(MAD sem fator de escala, como pedido). Município disponível para {fmt(i5.com_municipio)} das "
  f"{fmt(i5.elegiveis_base)} operações elegíveis (o CAR não acrescentou nenhuma: quem tem CAR já tem "
  f"complemento). {fmt(i5.grupos_ge20)} grupos avaliáveis, {fmt(i5.ops_avaliaveis)} operações; "
  f"{fmt(i5.grupos_mad_zero)} grupos com MAD = 0 ignorados.\n")
P("**Adaptação:** valor por hectare não serve para pecuária — o crédito pecuário é por animal e um "
  "confinamento tem área pequena e valor/ha altíssimo legitimamente. A análise principal usa **R$/ha para "
  "lavoura e R$/UA (ou R$/cabeça) para pecuária**; a regra literal (R$/ha para tudo) está na última linha.\n")
P(tab_resumo(r5), "\n")
P("**10 casos mais fortes** (indício; ordenados pelo excesso em R$ acima do limiar):\n")
P(tab_top(RES / "cruz5_top10.csv",
          ["ref_bacen", "nu_ordem", "banco", "safra", "finalidade", "produto", "municipio", "vl_parc_credito", "metrica",
           "valor_un", "mediana", "vezes_mediana", "n_grupo"],
          ["REF_BACEN", "ordem", "banco", "safra", "finalidade", "produto", "mun. IBGE", "valor R$", "métrica",
           "valor/unid.", "mediana grupo", "× mediana", "n grupo"],
          {"vl_parc_credito": brl, "valor_un": brl, "mediana": brl, "vezes_mediana": lambda v: fmt(v, 1)}), "\n")
P("![Cruzamento 5](maps/mapa5_cruz5_valor.png)\n")
P("**Leitura.** Mediana + 3·MAD em distribuições de cauda longa marca ~10% das operações — demais para "
  "triagem. Os casos do topo são quase todos custeio pecuário **em torno de R$ 3 mi** (a maioria exatamente "
  "R$ 3.000.000 — parece teto por beneficiário) com poucas UA declaradas: pode ser crédito acima da necessidade, mas também UA mal "
  "informada. A taxa maior dos demais bancos é em parte artefato: a mediana de cada grupo é dominada pelo BB "
  "(77% das operações), e operações de outros bancos, com perfil de cliente diferente, caem fora dessa "
  "curva. Útil só em combinação com outros sinais.\n")

# ---------------------------------------------------------------- convergência
P("## 8. Convergência entre cruzamentos\n")
P(f"Operações com indício em mais de um cruzamento (C2 aqui conta só pares em bancos diferentes ou "
  f"agrícolas): **{fmt(len(conv))}** (BB {fmt(conv.is_bb.sum())}, demais {fmt((~conv.is_bb).sum())}; "
  f"R$ {fmt(conv.vl_parc_credito.sum() / 1e6, 1)} mi).\n")
P(combos.rename_axis("combinação").reset_index(name="operações").to_markdown(index=False, disable_numparse=True), "\n")
P("A combinação mais frequente — **gleba fora do CAR informado + valor por unidade fora da curva** — é a "
  "melhor candidata a revisão manual. Lista completa em `cruzamentos/convergencia.csv`.\n")

# ---------------------------------------------------------------- conclusão
P("## 9. Conclusão honesta\n")
P("**Parece sinal real (vale revisar caso a caso):**")
P("1. **Gleba × CAR, quando a gleba está dentro de outro imóvel distante** ou fora de qualquer CAR "
  "(~3,2 mil operações; ~1,3% do recorte). É o cruzamento mais informativo e o mais barato de verificar.")
P("2. **Crédito em UC de proteção integral e em área embargada vigente** — poucos casos, mas com regra clara "
  "do lado do crédito; o núcleo é um único parque (Serra Dourada), o que sugere um problema localizado de "
  "regularização fundiária mais do que fraude difusa.")
P("3. **Mesma área, mesmo produto, mesma safra, bancos diferentes** (~800 operações) — o desenho clássico de "
  "dupla captação, embora parte possa ser financiamento complementar legítimo.\n")
P("**Parece ruído ou erro de cadastro:** área incoerente (C4), fora do município (C3e), água (C3a), "
  "sobreposição em pecuária no mesmo banco (C2) e a maior parte do valor/ha (C5). O Sicor já valida área e "
  "município contra o polígono na entrada, então inconsistências mecânicas internas quase não sobram; o que "
  "aparece vem do cruzamento com bases **externas** (CAR, UC, embargos, outros bancos).\n")
a1, a3 = linha(r1, "1. Gleba × CAR — indício"), linha(r3, "3. Geometria impossível — qualquer indício")
P(f"**BB × demais:** as diferenças são pequenas e confundidas por perfil. Gleba × CAR: {fmt(a1.bb_pct, 2)}% (BB) × "
  f"{fmt(a1.demais_pct, 2)}% (demais); geometria impossível: {fmt(a3.bb_pct, 2)}% × {fmt(a3.demais_pct, 2)}% "
  f"({fmt(a3.bb_disparam)} × {fmt(a3.demais_disparam)} casos, puxados por um parque onde 95% do crédito é do BB). Onde os demais aparecem bem acima (C2 entre bancos, C5), a diferença sai por construção "
  "(tamanho dos grupos; mediana dominada pelo BB). Não há base, com estes dados, para dizer que um grupo de "
  "bancos é mais permissivo que o outro.\n")
P("**Vale investir num projeto maior?** Com **só dados públicos, não ainda** — o gargalo é a cobertura: 66% "
  "das operações (80% do valor), justamente as maiores, não têm localização pública. Recomendo um passo "
  "intermediário de baixo custo antes de decidir:")
P("1. revisar manualmente 20–30 casos da lista de convergência com imagem de satélite gratuita (fora do "
  "escopo deste fim de semana) para estimar a **precisão** dos sinais;")
P("2. se a precisão for boa (digamos > 30% de casos que resistem à revisão), o projeto maior faz sentido, e "
  "precisaria de: localização completa (pedido via LAI ao BCB ou parceria institucional), séries históricas "
  "do SICAR (status do CAR **na data** do contrato), uso do solo (MapBiomas/PRODES) para checar se havia "
  "lavoura/pasto, e vínculo por beneficiário (tratamento de dado pessoal exige base legal).\n")

# ---------------------------------------------------------------- limitações
P("## 10. Limitações\n")
P("- Localização publicada para 34% das operações, com viés de porte/produto/banco.")
P("- SICAR, CNUC e embargos são retratos atuais; não reconstituem a situação na data do contrato.")
P("- Massas d'água da ANA misturam reservatórios na cota máxima, várzeas e lagoas sazonais; rios como linha "
  "não foram usados (sem área).")
P("- 1.343 embargos do IBAMA em GO têm coordenada de ponto inválida e só entram se tiverem polígono.")
P("- Sem CPF, não é possível saber se dois contratos sobre a mesma área são do mesmo produtor (o CAR "
  "compartilhado é usado como aproximação).")
P("- Limiares (10%, 50%, 3·MAD) são convenções de triagem; as tabelas de sensibilidade mostram o efeito de "
  "alterá-los.\n")

P("## Reprodução\n")
P("`make all` refaz tudo a partir dos downloads (o CAR de GO precisa estar em `data/raw/car/`). Scripts em "
  "`scripts/` (01–12), resultados intermediários em `data/processed/`, tabelas completas em "
  "`outputs/cruzamentos/`, mapas em `outputs/maps/`.\n")

(OUT / "relatorio.md").write_text("\n".join(L) + "\n")
print(f"relatorio.md: {len(L)} blocos; convergência: {len(conv)} operações")
