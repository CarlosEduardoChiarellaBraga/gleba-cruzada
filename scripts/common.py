"""Caminhos e utilitários compartilhados pelos scripts do projeto."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests
import truststore

# Usa o repositório de certificados do sistema (macOS Keychain): alguns servidores
# governamentais (ex.: FUNAI) não enviam a cadeia intermediária completa.
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

# Recorte do estudo
UF = "GO"
UF_IBGE = "52"
ANOS_ARQUIVO = [2021, 2022, 2023, 2024, 2025]  # anos de emissão que cobrem as safras
SAFRAS = ["2021/22", "2022/23", "2023/24", "2024/25"]  # safra = 1/jul a 30/jun
CNPJ_BB = "00000000"

# CRS métrico para área/distância: SIRGAS 2000 / Brazil Polyconic
CRS_METRICO = "EPSG:5880"
CRS_GEO = "EPSG:4674"  # SIRGAS 2000 geográfico

UA = {"User-Agent": "Mozilla/5.0 (research-client)"}


def download(url: str, dest: Path, retries: int = 3, chunk: int = 1 << 20) -> Path:
    """Baixa url -> dest. Pula se já existe com o mesmo tamanho do servidor."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        try:
            h = requests.head(url, headers=UA, timeout=60, allow_redirects=True)
            if h.status_code != 200:
                raise RuntimeError(f"HTTP {h.status_code} em {url}")
            size = int(h.headers.get("content-length", -1))
            if dest.exists() and size > 0 and dest.stat().st_size == size:
                print(f"[ok] {dest.name} já baixado ({size/1e6:.1f} MB)")
                return dest
            tmp = dest.with_suffix(dest.suffix + ".part")
            t0 = time.time()
            with requests.get(url, headers=UA, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for b in r.iter_content(chunk):
                        f.write(b)
            if size > 0 and tmp.stat().st_size != size:
                raise RuntimeError(f"tamanho incompleto {tmp.stat().st_size} != {size}")
            tmp.rename(dest)
            print(f"[baixado] {dest.name} {dest.stat().st_size/1e6:.1f} MB em {time.time()-t0:.0f}s")
            return dest
        except Exception as e:  # noqa: BLE001
            print(f"[tentativa {attempt}/{retries}] {url}: {e}", file=sys.stderr)
            time.sleep(5 * attempt)
    raise RuntimeError(f"falhou: {url}")
