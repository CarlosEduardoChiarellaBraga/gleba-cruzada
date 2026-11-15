"""Etapa 02 — baixa camadas de cruzamento (exceto CAR/SICAR, que é manual).

Uso: python -I scripts/02_download_camadas.py [ibge funai cnuc ibama ana ...]
Sem argumentos baixa todas.
"""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW, UA, download  # noqa: E402

# Envelope de Goiás (com folga) em graus — usado para filtrar serviços nacionais
GO_BBOX = (-53.4, -19.6, -45.8, -12.3)

FONTES = {
    "ibge": [("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
              "malhas_municipais/municipio_2024/UFs/GO/GO_Municipios_2024.zip",
              RAW / "ibge" / "GO_Municipios_2024.zip")],
    "cnuc": [("https://dados.mma.gov.br/dataset/44b6dc8a-dc82-4a84-8d95-1b0da7c85dac/resource/"
              "6ba9a557-87e8-4882-acb7-b3e0f0ea192d/download/shp_cnuc_2025_08.zip",
              RAW / "cnuc" / "shp_cnuc_2025_08.zip")],
    "ibama": [("https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/"
               "TERMOS_DE_EMBARGO/TERMO_EMBARGO/termo_de_embargo.csv",
               RAW / "ibama" / "termo_de_embargo.csv")],
}


def wfs_funai():
    dest = RAW / "funai" / "tis_poligonais_go.geojson"
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"[ok] {dest.name} já baixado"); return
    dest.parent.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = GO_BBOX
    url = ("https://geoserver.funai.gov.br/geoserver/Funai/ows?service=WFS&version=1.0.0"
           "&request=GetFeature&typeName=Funai:tis_poligonais&outputFormat=application/json"
           f"&bbox={x0},{y0},{x1},{y1},EPSG:4674")
    r = requests.get(url, headers=UA, timeout=300); r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"[baixado] {dest.name}: {len(r.json()['features'])} feições")


def arcgis_layer(url_layer: str, dest: Path):
    """Baixa feições de uma camada ArcGIS FeatureServer dentro do envelope de GO."""
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"[ok] {dest.name} já baixado"); return
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Esta camada NÃO suporta paginação (resultOffset é ignorado e devolve sempre os
    # mesmos registros). Estratégia robusta: pedir só os IDs no envelope, depois
    # baixar em lotes por lista de IDs (POST).
    meta = requests.get(url_layer, params={"f": "json"}, headers=UA, timeout=60).json()
    page = min(int(meta.get("maxRecordCount", 1000)), 500)
    x0, y0, x1, y1 = GO_BBOX
    filtro = {"where": "1=1", "geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope",
              "inSR": 4674, "spatialRel": "esriSpatialRelIntersects"}

    def post(params):
        for attempt in range(5):
            try:
                r = requests.post(f"{url_layer}/query", data=params, headers=UA, timeout=300)
                r.raise_for_status()
                js = r.json()
                if "error" in js:
                    raise RuntimeError(js["error"])
                return js
            except Exception as e:  # noqa: BLE001
                print(f"  retry {attempt}: {e}", file=sys.stderr); time.sleep(5 * (attempt + 1))
        raise RuntimeError("falhou ArcGIS")

    ids = sorted(post({**filtro, "returnIdsOnly": "true", "f": "json"})["objectIds"])
    esperado = post({**filtro, "returnCountOnly": "true", "f": "json"})["count"]
    print(f"  {dest.name}: {len(ids):,} IDs no envelope (contagem do servidor: {esperado:,})", flush=True)
    feats = []
    for i in range(0, len(ids), page):
        lote = ids[i:i + page]
        js = post({"objectIds": ",".join(map(str, lote)), "outFields": "*", "outSR": 4674, "f": "geojson"})
        feats += js.get("features", [])
        if (i // page) % 20 == 0:
            print(f"  {dest.name}: {len(feats):,}/{len(ids):,}", flush=True)
    if len(feats) != len(ids):
        raise RuntimeError(f"baixadas {len(feats)} feições, esperadas {len(ids)}")
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"[baixado] {dest.name}: {len(feats):,} feições")


def ana():
    arcgis_layer("https://www.snirh.gov.br/arcgis/rest/services/SPR/Massa_dagua/FeatureServer/0",
                 RAW / "ana" / "massa_dagua_go.geojson")


ALVOS = sys.argv[1:] or ["ibge", "funai", "cnuc", "ibama", "ana"]
falhas = []
for alvo in ALVOS:
    print(f"== {alvo}", flush=True)
    try:
        if alvo in FONTES:
            for url, dest in FONTES[alvo]:
                download(url, dest)
        elif alvo == "funai":
            wfs_funai()
        elif alvo == "ana":
            ana()
        else:
            print(f"alvo desconhecido: {alvo}")
    except Exception as e:  # noqa: BLE001
        print(f"[FALHA] {alvo}: {e}", file=sys.stderr)
        falhas.append(alvo)
if falhas:
    sys.exit(f"camadas com falha: {falhas}")
