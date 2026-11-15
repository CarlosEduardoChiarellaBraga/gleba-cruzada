"""Etapa 03 — ingestão do Sicor para Parquet/GeoParquet (recorte GO, safras 2021/22–2024/25).

Saídas em data/processed/:
  operacoes_go.parquet    1 linha por operação (REF_BACEN, NU_ORDEM), custeio+investimento
  glebas_go.parquet       GeoParquet, 1 linha por gleba (REF_BACEN, NU_ORDEM, NU_INDICE), EPSG:4674
  propriedades_go.parquet CAR/SNCR por operação (SEM CPF/CNPJ do proprietário)

Safra = 1º de julho a 30 de junho (Plano Safra), derivada de DT_EMISSAO.
"""
import sys
import time
from pathlib import Path

import duckdb
import geopandas as gpd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ANOS_ARQUIVO, CNPJ_BB, CRS_GEO, PROC, RAW, SAFRAS, UF  # noqa: E402

S = RAW / "sicor"
PROC.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(PROC / "work.duckdb"))
con.sql("SET memory_limit='8GB'; SET threads=8; SET preserve_insertion_order=false;")
con.sql("INSTALL spatial; LOAD spatial;")


def t(msg, t0=[time.time()]):  # noqa: B006
    print(f"[{time.time()-t0[0]:6.0f}s] {msg}", flush=True)


def csv(path: Path, extra: str = "") -> str:
    """Leitura padrão do Sicor: ';', cabeçalho com '#', latin-1, tudo texto.

    Os dicionários têm aspas mal-formadas em algumas linhas (o sniffer do DuckDB
    falha); como nenhum campo contém ';', lemos sem aspas e removemos '"' depois.
    """
    return (f"(SELECT trim(trim(trim(COLUMNS(*)), '\"')) FROM read_csv('{path}', delim=';', header=true, "
            f"all_varchar=true, quote='', escape='', encoding='latin-1'{extra}))")


# ---------------------------------------------------------------- dicionários
con.sql(f"""
CREATE OR REPLACE TABLE dim_empreendimento AS
SELECT "#CODIGO" AS cd_empreendimento, FINALIDADE AS finalidade, ATIVIDADE AS atividade,
       MODALIDADE AS modalidade, PRODUTO AS produto, VARIEDADE AS variedade,
       UNIDADE_MEDIDA AS unidade_medida
FROM {csv(S / 'Empreendimento.csv')}
""")
dup = con.sql("SELECT count(*) - count(DISTINCT cd_empreendimento) FROM dim_empreendimento").fetchall()[0][0]
t(f"dim_empreendimento: {con.sql('select count(*) from dim_empreendimento').fetchall()[0][0]} códigos ({dup} duplicados)")

con.sql(f"""
CREATE OR REPLACE TABLE dim_if AS
SELECT "#CNPJ_IF" AS cnpj_if, NOME_IF AS nome_if, SEGMENTO_IF AS segmento_if
FROM {csv(S / 'SICOR_LISTA_IFS.csv')}
""")
con.sql(f"""
CREATE OR REPLACE TABLE dim_programa AS
SELECT "#CODIGO" AS cd_programa, DESCRICAO AS programa FROM {csv(S / 'Programa.csv')}
""")

# ---------------------------------------------------------------- operações
arqs_op = [str(S / f"SICOR_OPERACAO_BASICA_ESTADO_{a}.gz") for a in ANOS_ARQUIVO]
safras_sql = ", ".join(f"'{s}'" for s in SAFRAS)
con.sql(f"""
CREATE OR REPLACE TABLE op_raw AS
SELECT * EXCLUDE ("#REF_BACEN"), "#REF_BACEN" AS REF_BACEN,
       regexp_extract(filename, '(\\d{{4}})\\.gz$', 1) AS ano_arquivo
FROM read_csv({arqs_op}, delim=';', header=true, all_varchar=true, encoding='latin-1',
              filename=true, union_by_name=true, quote='', escape='')
WHERE CD_ESTADO = '{UF}'
""")
t(f"op_raw (GO, arquivos {ANOS_ARQUIVO}): {con.sql('select count(*) from op_raw').fetchall()[0][0]:,} linhas")

con.sql(f"""
CREATE OR REPLACE TABLE operacoes AS
WITH o AS (
  SELECT
    REF_BACEN::BIGINT AS ref_bacen, NU_ORDEM::INT AS nu_ordem, ano_arquivo::INT AS ano_arquivo,
    CNPJ_IF AS cnpj_if, strptime(DT_EMISSAO, '%d/%m/%Y')::DATE AS dt_emissao,
    strptime(DT_VENCIMENTO, '%d/%m/%Y')::DATE AS dt_vencimento,
    CD_EMPREENDIMENTO AS cd_empreendimento, CD_PROGRAMA AS cd_programa,
    CD_SUBPROGRAMA AS cd_subprograma, CD_FONTE_RECURSO AS cd_fonte_recurso,
    CD_INST_CREDITO AS cd_inst_credito, CD_CATEG_EMITENTE AS cd_categ_emitente,
    CD_TIPO_IRRIGACAO AS cd_tipo_irrigacao, CD_TIPO_CULTIVO AS cd_tipo_cultivo,
    TRY_CAST(VL_PARC_CREDITO AS DOUBLE) AS vl_parc_credito,
    TRY_CAST(VL_REC_PROPRIO AS DOUBLE) AS vl_rec_proprio,
    TRY_CAST(VL_AREA_FINANC AS DOUBLE) AS vl_area_financ,
    TRY_CAST(VL_AREA_INFORMADA AS DOUBLE) AS vl_area_informada,
    TRY_CAST(VL_QUANTIDADE AS DOUBLE) AS vl_quantidade,
    TRY_CAST(VL_PREV_PROD AS DOUBLE) AS vl_prev_prod,
    TRY_CAST(VL_RECEITA_BRUTA_ESPERADA AS DOUBLE) AS vl_receita_bruta_esperada,
    TRY_CAST(VL_JUROS AS DOUBLE) AS vl_juros,
    TRY_STRPTIME(DT_INIC_PLANTIO, '%d/%m/%Y')::DATE AS dt_inic_plantio,
    TRY_STRPTIME(DT_FIM_PLANTIO, '%d/%m/%Y')::DATE AS dt_fim_plantio,
    TRY_STRPTIME(DT_INIC_COLHEITA, '%d/%m/%Y')::DATE AS dt_inic_colheita,
    TRY_STRPTIME(DT_FIM_COLHEITA, '%d/%m/%Y')::DATE AS dt_fim_colheita,
    CD_FASE_CICLO_PRODUCAO AS cd_fase_ciclo, CD_TIPO_AGRICULTURA AS cd_tipo_agricultura,
    PC_BONUS_CAR AS pc_bonus_car
  FROM op_raw
)
SELECT o.*,
  CASE WHEN month(dt_emissao) >= 7
       THEN year(dt_emissao)::VARCHAR || '/' || lpad(((year(dt_emissao)+1) % 100)::VARCHAR, 2, '0')
       ELSE (year(dt_emissao)-1)::VARCHAR || '/' || lpad((year(dt_emissao) % 100)::VARCHAR, 2, '0')
  END AS safra,
  e.finalidade, e.atividade, e.modalidade, e.produto, e.variedade, e.unidade_medida,
  i.nome_if, i.segmento_if, (o.cnpj_if = '{CNPJ_BB}') AS is_bb,
  p.programa
FROM o
LEFT JOIN dim_empreendimento e USING (cd_empreendimento)
LEFT JOIN dim_if i USING (cnpj_if)
LEFT JOIN dim_programa p USING (cd_programa)
""")
t("operacoes GO (todas finalidades/datas dos arquivos) — distribuição:")
print(con.sql("""SELECT safra, finalidade, count(*) n FROM operacoes
                 GROUP BY ALL ORDER BY safra, finalidade""").df().to_string(index=False))

con.sql(f"""
CREATE OR REPLACE TABLE ops AS
SELECT * FROM operacoes
WHERE safra IN ({safras_sql}) AND finalidade IN ('Custeio', 'Investimento')
""")
n_ops = con.sql("select count(*) from ops").fetchall()[0][0]
dupk = con.sql("select count(*) - count(distinct (ref_bacen, nu_ordem)) from ops").fetchall()[0][0]
t(f"ops no recorte: {n_ops:,} (chaves duplicadas: {dupk})")

# ------------------------------------------------- complemento (município IBGE)
con.sql(f"""
CREATE OR REPLACE TABLE compl AS
SELECT c."#REF_BACEN"::BIGINT AS ref_bacen, c.NU_ORDEM::INT AS nu_ordem,
       c.CD_IBGE_MUNICIPIO AS cd_ibge_municipio, c.AGENCIA_IF AS agencia_if,
       c.REF_BACEN_EFETIVO AS ref_bacen_efetivo
FROM {csv(S / 'SICOR_COMPLEMENTO_OPERACAO_BASICA.gz')} c
SEMI JOIN ops ON c."#REF_BACEN"::BIGINT = ops.ref_bacen AND c.NU_ORDEM::INT = ops.nu_ordem
""")
t(f"complemento casado: {con.sql('select count(*) from compl').fetchall()[0][0]:,}")

con.sql("""
CREATE OR REPLACE TABLE ops_final AS
SELECT o.*, c.cd_ibge_municipio, c.agencia_if, c.ref_bacen_efetivo
FROM ops o LEFT JOIN (SELECT DISTINCT ON (ref_bacen, nu_ordem) * FROM compl) c
USING (ref_bacen, nu_ordem)
""")
con.sql(f"COPY ops_final TO '{PROC / 'operacoes_go.parquet'}' (FORMAT parquet, COMPRESSION zstd)")
t("gravado operacoes_go.parquet")

# ---------------------------------------------------------------- propriedades
con.sql(f"""
CREATE OR REPLACE TABLE prop AS
SELECT p."#REF_BACEN"::BIGINT AS ref_bacen, p.NU_ORDEM::INT AS nu_ordem,
       nullif(p.CD_SNCR, '-1') AS cd_sncr, nullif(p.CD_CIB, '-1') AS cd_cib,
       nullif(p.CD_CAR, '-1') AS cd_car
       -- CD_CNPJ_CPF descartado de propósito (dado pessoal, desnecessário)
FROM {csv(S / 'SICOR_PROPRIEDADES.gz')} p
SEMI JOIN ops ON p."#REF_BACEN"::BIGINT = ops.ref_bacen AND p.NU_ORDEM::INT = ops.nu_ordem
""")
con.sql(f"COPY prop TO '{PROC / 'propriedades_go.parquet'}' (FORMAT parquet, COMPRESSION zstd)")
t(f"propriedades casadas: {con.sql('select count(*) from prop').fetchall()[0][0]:,}")

# ---------------------------------------------------------------- glebas
# Um arquivo por vez e menos threads: com linhas longas (WKT) o leitor CSV reserva
# buffers grandes por thread e estoura a memória lendo os 5 anos juntos.
con.sql("SET threads=4")
con.sql("""CREATE OR REPLACE TABLE glebas_txt (ref_bacen BIGINT, nu_ordem INT, nu_indice INT,
           wkt VARCHAR, ano_arquivo_gleba INT)""")
for ano in ANOS_ARQUIVO:
    con.sql(f"""
    INSERT INTO glebas_txt
    SELECT g."#REF_BACEN"::BIGINT, g.NU_ORDEM::INT, g.NU_INDICE::INT, g.GT_GEOMETRIA, {ano}
    FROM read_csv('{S / f"sicor_glebas_wkt_{ano}.gz"}', delim=';', header=true, all_varchar=true,
                  encoding='latin-1', quote='', escape='', max_line_size=16000000) g
    SEMI JOIN ops ON g."#REF_BACEN"::BIGINT = ops.ref_bacen AND g.NU_ORDEM::INT = ops.nu_ordem
    """)
    t(f"  glebas {ano}: acumulado {con.sql('select count(*) from glebas_txt').fetchall()[0][0]:,}")
t(f"glebas (texto) casadas: {con.sql('select count(*) from glebas_txt').fetchall()[0][0]:,}")

# O WKT do Sicor traz Z implícito ("x y 0" sem a tag Z), que o parser do DuckDB
# rejeita; GEOS (shapely) aceita. Convertemos em Python e gravamos GeoParquet.
gtx = con.sql("""SELECT ref_bacen, nu_ordem, nu_indice, ano_arquivo_gleba,
                        upper(split_part(trim(wkt), ' ', 1)) AS wkt_tipo, length(wkt) AS wkt_len, wkt
                 FROM glebas_txt""").df()
con.close()
geom = shapely.from_wkt(gtx.pop("wkt").values, on_invalid="ignore")
n_falha = int(shapely.is_missing(geom).sum())
geom = shapely.force_2d(geom)
gdf = gpd.GeoDataFrame(gtx, geometry=geom, crs=CRS_GEO)
gdf.to_parquet(PROC / "glebas_go.parquet", compression="zstd", geometry_encoding="WKB")
t(f"gravado glebas_go.parquet ({len(gdf):,} glebas; WKT ilegível: {n_falha:,})")
