# gleba-cruzada

Exploração de triagem do crédito rural em Goiás. Cruza as glebas georreferenciadas do Sicor (Banco Central) com o CAR e com camadas públicas (água, terras indígenas, unidades de conservação, embargos do IBAMA, malha municipal) para levantar **indícios** de irregularidade.

**É triagem, não acusação.** Um disparo aqui não significa fraude. A maior parte dos disparos é erro de cadastro ou ruído, e todo caso precisa de verificação manual.

## Recorte
- Goiás, safras 2021/22 a 2024/25, custeio e investimento.
- Banco do Brasil comparado aos demais bancos.
- Só cerca de 34% das operações (20% do valor) têm gleba publicada. A amostra é enviesada para pequeno produtor, Pronaf, pecuária e BB.

## Os cinco cruzamentos
1. **Gleba × CAR informado:** sobreposição baixa ou distância grande.
2. **Mesma área financiada duas vezes:** mesma safra, mesmo produto e mesmo ciclo.
3. **Geometria impossível:** água, terra indígena, unidade de conservação, embargo anterior ao contrato, fora do município.
4. **Área declarada × área da gleba.**
5. **Valor por hectare ou por UA acima de mediana + 3·MAD**, dentro de produto × município × safra (grupos com n ≥ 20).

## Como rodar
Requer [uv](https://docs.astral.sh/uv/), cerca de 30 GB livres e conexão.

```sh
make passo0   # ambiente, download do Sicor e das camadas, ingestão, reconhecimento
# baixe o CAR de GO (área do imóvel) manualmente no SICAR (tem captcha):
#   https://consultapublica.car.gov.br/publico/estados/downloads
# e salve em data/raw/car/AREA_IMOVEL.zip
make all      # cruzamentos, mapas e outputs/relatorio.md
make revisao  # pacote KML/CSV para revisão manual no Google Earth
```

Os resultados vão para `outputs/`, que fica fora do repositório de propósito: eles contêm números de operação, códigos de CAR e coordenadas.

## Estrutura
- `scripts/01–02`: downloads.
- `scripts/03`: ingestão em DuckDB e GeoParquet.
- `scripts/04`: reconhecimento (Passo 0).
- `scripts/05`: preparação das camadas (EPSG:5880, make_valid).
- `scripts/06–10`: os cinco cruzamentos.
- `scripts/11–13`: mapas, relatório e pacote de revisão.

## Fontes
Todos os dados são públicos:
- BCB: microdados do Sicor;
- SICAR: CAR;
- ANA: massas d'água;
- FUNAI: terras indígenas;
- MMA: CNUC (unidades de conservação);
- IBAMA: termos de embargo;
- IBGE: malha municipal.
