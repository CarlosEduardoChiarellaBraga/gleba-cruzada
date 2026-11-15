# Exploração de triagem: crédito rural (Sicor) × CAR × camadas públicas — Goiás
# Uso: make all       (tudo; o CAR de GO precisa estar em data/raw/car/AREA_IMOVEL.zip)
#      make passo0    (download + ingestão + reconhecimento)
#      make cruzamentos / make relatorio
PY := .venv/bin/python -I -u
D := data/processed

.PHONY: all env download ingest passo0 car camadas cruzamentos mapas relatorio clean-processed revisao padroes suspeitas

all: passo0 relatorio

env:
	uv sync

download: env
	$(PY) scripts/01_download_sicor.py
	$(PY) scripts/02_download_camadas.py

$(D)/operacoes_go.parquet $(D)/glebas_go.parquet: scripts/03_ingest_sicor.py scripts/common.py
	$(PY) scripts/03_ingest_sicor.py
ingest: $(D)/operacoes_go.parquet

outputs/reconhecimento.md: $(D)/glebas_go.parquet scripts/04_reconhecimento.py
	$(PY) scripts/04_reconhecimento.py
passo0: download ingest outputs/reconhecimento.md

# CAR: download manual (captcha) — ver outputs/reconhecimento.md, seção 6
data/raw/car/AREA_IMOVEL/AREA_IMOVEL_1.shp: data/raw/car/AREA_IMOVEL.zip
	mkdir -p data/raw/car/AREA_IMOVEL && unzip -o -q $< -d data/raw/car/AREA_IMOVEL && touch $@
car: data/raw/car/AREA_IMOVEL/AREA_IMOVEL_1.shp

$(D)/op_footprint.parquet: data/raw/car/AREA_IMOVEL/AREA_IMOVEL_1.shp $(D)/glebas_go.parquet scripts/05_prep_camadas.py
	$(PY) scripts/05_prep_camadas.py
camadas: $(D)/op_footprint.parquet

$(D)/cruz1_ops.parquet: $(D)/op_footprint.parquet scripts/06_cruz1_gleba_car.py scripts/cruz_common.py
	$(PY) scripts/06_cruz1_gleba_car.py
$(D)/cruz2_pares.parquet: $(D)/op_footprint.parquet scripts/07_cruz2_dupla_area.py scripts/cruz_common.py
	$(PY) scripts/07_cruz2_dupla_area.py
$(D)/cruz3_ops.parquet: $(D)/op_footprint.parquet scripts/08_cruz3_geometria.py scripts/cruz_common.py
	$(PY) scripts/08_cruz3_geometria.py
$(D)/cruz4_ops.parquet: $(D)/op_footprint.parquet scripts/09_cruz4_area.py scripts/cruz_common.py
	$(PY) scripts/09_cruz4_area.py
$(D)/cruz5_ops.parquet: $(D)/operacoes_go.parquet scripts/10_cruz5_valor_ha.py scripts/cruz_common.py
	$(PY) scripts/10_cruz5_valor_ha.py
cruzamentos: $(D)/cruz1_ops.parquet $(D)/cruz2_pares.parquet $(D)/cruz3_ops.parquet $(D)/cruz4_ops.parquet $(D)/cruz5_ops.parquet

mapas: cruzamentos scripts/11_mapas.py
	$(PY) scripts/11_mapas.py

relatorio: mapas scripts/12_relatorio.py
	$(PY) scripts/12_relatorio.py

clean-processed:
	rm -rf data/processed/* outputs/*.md outputs/*.csv outputs/*.json outputs/cruzamentos outputs/maps/*.png

revisao: $(D)/cruz3_ops.parquet scripts/13_revisao_serra_dourada.py
	$(PY) scripts/13_revisao_serra_dourada.py

padroes: $(D)/cruz1_ops.parquet scripts/14_padroes_engano.py
	$(PY) scripts/14_padroes_engano.py

suspeitas: padroes scripts/15_suspeitas.py
	$(PY) scripts/15_suspeitas.py
