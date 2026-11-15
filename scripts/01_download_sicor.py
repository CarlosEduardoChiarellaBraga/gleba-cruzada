"""Etapa 01 — baixa microdados do Sicor (BCB) necessários ao recorte.

Fonte: https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ANOS_ARQUIVO, RAW, download  # noqa: E402

BASE = "https://www.bcb.gov.br/htms/sicor"
DB = f"{BASE}/DadosBrutos"
DEST = RAW / "sicor"

arquivos = []
for ano in ANOS_ARQUIVO:
    arquivos.append(f"{DB}/SICOR_OPERACAO_BASICA_ESTADO_{ano}.gz")
    arquivos.append(f"{DB}/sicor_glebas_wkt_{ano}.gz")
arquivos += [
    f"{DB}/SICOR_PROPRIEDADES.gz",                # CAR/SNCR por operação
    f"{DB}/SICOR_COMPLEMENTO_OPERACAO_BASICA.gz",  # município IBGE, agência
    f"{DB}/SICOR_LISTA_IFS.csv",
    f"{BASE}/manualDadosSicorCompleto.pdf",
]
# dicionários (tabelas de domínio)
for t in ["Empreendimento", "Produto", "Programa", "Subprogramas", "Modalidade",
          "Atividade", "Finalidade", "MunicipiosSicor", "CategoriaEmitente",
          "InstrumentoCredito", "FonteRecursos", "SituacaoOperacao"]:
    arquivos.append(f"{BASE}/{t}.csv")

# menores primeiro, para o reconhecimento poder começar cedo
ordem = sorted(arquivos, key=lambda u: (not u.endswith((".csv", ".pdf")), "glebas" in u, u))
for url in ordem:
    download(url, DEST / url.rsplit("/", 1)[1])
print("download Sicor concluído")
