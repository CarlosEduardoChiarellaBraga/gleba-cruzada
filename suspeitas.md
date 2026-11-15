# Suspeitas: como conferir cada caso

Estes são os 5 casos da triagem que mais se parecem com **engano**: alguém declarou algo falso que o banco não teria como perceber sozinho. Isso é diferente de falha de controle, em que a informação estava certa e o banco aprovou mesmo assim.

> **Nada aqui é acusação.** Todos os dados são públicos (Sicor/BCB, SICAR, IBAMA), mas há explicações legítimas para cada padrão, listadas caso a caso. Um caso só vira suspeita séria depois dos passos abaixo. Mesmo assim, saber **quem** são os tomadores (e se houve laranja) depende do CPF, que só o BCB e o banco têm.

## Antes de começar

**Ferramentas, todas gratuitas:**
- **Google Earth Pro** (desktop). Precisa da versão Pro para o ícone de relógio, que mostra imagens antigas.
- **[outputs/revisao/suspeitas.kml](outputs/revisao/suspeitas.kml)**: abra no Google Earth Pro em *Arquivo → Abrir*. Cada caso é uma pasta com:
  - **laranja**: gleba financiada (o polígono que o banco mandou ao BCB);
  - **azul**: CAR informado no contrato;
  - **verde**: CAR que de fato contém a gleba;
  - **vermelho**: embargo do IBAMA, quando houver.

  Clique em cada polígono para ver número da operação, banco, data, valor e área.
- **Consulta pública do CAR**: https://consultapublica.car.gov.br. Busque pelo código **com hífens** (ex.: `GO-5218003-CE4B…`). Ela mostra área, situação e o desenho do imóvel, sem o nome do dono.
- **MapBiomas**: https://plataforma.brasil.mapbiomas.org. Mostra o uso do solo ano a ano (pasto, soja, café, vegetação nativa) no ponto clicado.
- **Consulta pública de áreas embargadas do IBAMA**: busque "IBAMA consulta áreas embargadas" e procure pelo número do TAD.

**Para reproduzir:** `make padroes suspeitas` gera o KML e a lista completa em [outputs/revisao/bb_padroes_engano.csv](outputs/revisao/bb_padroes_engano.csv).

---

## Caso 1: café financiado duas vezes, BB e Rabobank
**Campo Alegre de Goiás, safra 2021/22. Gleba em −17.33625, −47.88455.**

| Contrato | Banco | Data | Valor | Área declarada | CAR informado | CAR contém a gleba? |
|---|---|---|---|---|---|---|
| 512969168 | BB | 21/10/2021 | R$ 1.110.517 | 61,5 ha | GO-5210109-B147BBA555F643CDBAEC854E51F1C448 (200,6 ha) | **sim** (99%) |
| 513267165 | Rabobank | 20/12/2021 | R$ 1.300.000 | 62,6 ha | GO-5204805-5DF1FF916A724CBCA5392301AE19A720 (**42,9 ha**) | **não** (0%, a 14 km) |

**Por que é suspeito:**
- As duas glebas são o mesmo polígono (97% de sobreposição): a mesma lavoura de café de cerca de 62 ha, no mesmo ciclo, financiada duas vezes, com R$ 2,4 mi no total.
- Um banco não vê a gleba do outro.
- O contrato do Rabobank informa um CAR **menor que a área financiada** (42,9 ha contra 62,6 ha), a 14 km da lavoura.

**Hipótese:** o segundo tomador usou um CAR próprio (ou de terceiro) como fachada e desenhou a lavoura que já estava financiada no BB. A suspeita recai sobre o contrato do Rabobank. O do BB parece regular.

**Passo a passo:**
1. No Google Earth, abra a pasta *Caso 1* e confirme que os dois polígonos laranja coincidem.
2. Com o relógio, vá para 2021 e 2022. Café aparece em linhas paralelas bem marcadas, às vezes em pivô circular. Confirme que há cerca de 62 ha de café ali.
3. Confira o mesmo ponto no MapBiomas, nos anos 2021 e 2022: a classe deve ser "Café".
4. Na consulta pública do CAR, busque `GO-5204805-5DF1FF916A724CBCA5392301AE19A720`.
   - Veja onde fica o imóvel (por volta de −17.29728, −47.76025) e o que há nele.
   - Um imóvel de 43 ha não comporta 62,6 ha de café.
5. Busque também `GO-5210109-B147BBA555F643CDBAEC854E51F1C448` e confirme que a lavoura está dentro dele.

**O que derruba a suspeita:**
- O imóvel do CAR do Rabobank tem café próprio e a gleba foi desenhada errada. Seria erro de cadastro, mas aí a área declarada não caberia no CAR.
- O tomador do Rabobank arrenda a lavoura do outro imóvel. O correto seria informar o CAR do imóvel arrendado. É erro, não fraude, mas ainda assim a mesma lavoura teria dois custeios.

---

## Caso 2: gleba desenhada fora do CAR embargado
**Porangatu, safra 2021/22. Gleba em −13.04314, −49.09397.**

| Contrato | Banco | Data | Valor | O que financiou | Área declarada |
|---|---|---|---|---|---|
| 512628425 | BB | 26/08/2021 | R$ 473.100 | 120 UA (matrizes de corte) | 801,2 ha |
| 514044225 | BB | 23/06/2022 | R$ 855.000 | 200 UA (matrizes de corte) | 801,2 ha |

- **CAR informado nos dois contratos:** `GO-5218003-CE4BE8FCD7304EFF9CA5F1D9325D8279`.
  - Tem 821,8 ha, quase exatamente a área declarada.
  - Fica a **17 km** da gleba, por volta de −13.19482, −49.09891.
  - **Tem embargo do IBAMA vigente:** TAD 367004, de 16/10/2006, com cerca de 6 ha, não cancelado e sem desembargo registrado.
- **CAR que contém a gleba:** `GO-5218003-D1CB441EBE0E4283B766EB983BDC6D46` (1.088 ha), um imóvel diferente e sem embargo.

**Por que é suspeito:** os bancos checam se a gleba toca área embargada. Aqui o tomador declarou a área do próprio imóvel (801 ha, compatível com o CAR dele), mas o polígono enviado é de **outra fazenda**, longe do embargo. É exatamente o que alguém faria para passar pela checagem. Há também um terceiro contrato (512582781, R$ 100.500, 32 UA) com outra gleba dentro do mesmo imóvel D1CB e outro CAR informado.

**Passo a passo:**
1. No Google Earth, abra *Caso 2*. Você verá a gleba laranja dentro do CAR verde, o CAR azul 17 km ao sul e o embargo em vermelho dentro dele.
2. Na consulta de áreas embargadas do IBAMA, busque o **TAD 367004**.
   - Confirme que o embargo continua ativo e veja o motivo (normalmente desmatamento sem autorização).
   - Se tiver sido desembargado e isso não estiver nos dados abertos, o caso perde força.
3. Com o relógio, olhe a área do embargo. Se continuar aberta ou em uso (pasto, lavoura), é **descumprimento do embargo**, um agravante.
4. Busque os dois CARs na consulta pública. Veja se o D1CB (o que contém a gleba) tem desenho e área compatíveis com uma fazenda de outra pessoa (é o que o cadastro indica).
5. Veja se a gleba tem pasto capaz de receber o rebanho: são 320 UA em 863 ha, o que é plausível.

**O que derruba a suspeita:**
- O tomador arrenda ou usa a outra fazenda de fato e o gado está lá. Ainda seria CAR errado, mas sem o motivo do embargo.
- O embargo foi levantado.
- O polígono foi desenhado errado pela agência, por engano. Possível, mas é coincidência que ele caia justo fora do imóvel embargado.

---

## Caso 3: a mesma terra, o segundo contrato com o CAR de outro município
**Mineiros, safra 2021/22. Gleba em −17.52907, −52.41931.**

| Contrato | Banco | Data | Valor | O que financiou | Área declarada | CAR informado | CAR contém a gleba? |
|---|---|---|---|---|---|---|---|
| 513159196 | BB | 29/11/2021 | R$ 600.000 | 150 UA | 249,4 ha | GO-5213103-28B92120D0274806A9030E2AE0809ABB (332 ha, Mineiros) | **sim** (98%) |
| 513918443 | BB | 31/05/2022 | R$ 300.000 | 75 UA | 249,4 ha | GO-5218102-D423C00CCEDF4334A0CEB9078836133C (**33,7 ha**, Portelândia) | **não** (a 40 km) |

**Por que é suspeito:** é o mesmo polígono (100%). O segundo contrato declara 249 ha usando um CAR de **33,7 ha** em outro município, a 40 km. É o mesmo desenho do caso 1, só que dentro do BB, que tinha os dois contratos e poderia ter visto.

**Passo a passo:**
1. No Google Earth, abra *Caso 3* e compare a gleba (laranja) com os dois CARs.
2. Na consulta pública, busque o CAR de Portelândia (por volta de −17.34051, −52.73451). Veja se 33,7 ha comportam 75 UA. Em pasto comum, o normal fica em torno de 1 UA/ha.
3. Veja se a gleba, com o relógio em 2021 e 2022, é pasto em uso (gado, aguadas, cercas).
4. Rebanho total na terra: 225 UA em 249 ha, o que é plausível. Então a dúvida não é se o gado cabe, e sim **quem** pegou o segundo crédito usando a terra do primeiro.

**O que derruba a suspeita:** os dois tomadores são da mesma família e exploram juntos a fazenda de Mineiros. O CAR informado no segundo contrato estaria errado, mas sem dano. Isso só se confirma com CPF ou matrícula.

---

## Caso 4: correção de solo financiada duas vezes, BB e Sicredi
**Palestina de Goiás, safra 2023/24. Gleba em −16.75907, −51.25065.**

| Contrato | Banco | Data | Valor | Área declarada | R$/ha |
|---|---|---|---|---|---|
| 516330397 | BB | 09/08/2023 | R$ 1.575.474 | 238,9 ha | 6.595 |
| 517600549 | Sicredi | 15/03/2024 | R$ 499.027 | 237,2 ha | 2.104 |

Os dois contratos são de investimento em "correção intensiva do solo" e informam **os mesmos dois CARs**: `GO-5215652-544BC96957D84BD49A41E085FEE2AF49` (281 ha) e `GO-5215652-A2EDC31D3A794C8F934F3169B8352535` (27 ha).

**Por que é suspeito:**
- O mesmo polígono (97%) recebeu, em 7 meses, dois financiamentos para o mesmo serviço, em bancos diferentes. São R$ 2,07 mi, cerca de **R$ 8.700/ha**, enquanto correção de solo costuma custar bem menos.
- O primeiro contrato sozinho já está alto.
- O contrato do Sicredi fica no teto de R$ 500 mil.

**Passo a passo:**
1. No Google Earth, abra *Caso 4* e use o relógio entre 2022 e 2025. Correção de solo não aparece na imagem, mas costuma acompanhar uma **mudança de uso**: pasto degradado virando lavoura, área recém-aberta ou reforma de pastagem. Veja se houve mudança e quando.
2. No MapBiomas, veja a classe de uso do ponto em 2022, 2023 e 2024.
3. Se a área não mudou nada (o mesmo pasto antes e depois), R$ 2 mi em correção de solo fica difícil de explicar.
4. Na consulta pública, confira os dois CARs. Ambos os contratos usam os mesmos, então o tomador provavelmente é a mesma pessoa ou família.

**O que derruba a suspeita:**
- São etapas diferentes (calagem num ano, fosfatagem ou gessagem no outro) e a classificação do Sicor agrupa tudo como "correção intensiva".
- A área vira lavoura nas imagens.

Mesmo assim, o valor por hectare é alto e merece ser comparado com orçamentos da região.

---

## Caso 5: três contratos no teto de R$ 500 mil na mesma terra
**Trombas, safra 2024/25. Gleba em −13.39609, −48.72266.**

| Contrato | Banco | Data | Valor | O que financiou |
|---|---|---|---|---|
| 518924190 | BB | 16/10/2024 | R$ 497.000 | 142 UA (matrizes de corte) |
| 519479638 | BB | 10/02/2025 | R$ 499.850 | 130 UA |
| 519626683 | BB | 18/03/2025 | R$ 499.850 | 130 UA |

Os três contratos usam o mesmo polígono de 125 ha e o mesmo CAR, `GO-5221452-CF80B0A14B0C453196B6D5D2012C1425` (632 ha).

**Por que é suspeito:**
- Há um pico enorme de contratos de investimento logo abaixo de R$ 500 mil (no BB, 2.097 contratos entre R$ 490 e 500 mil contra 150 entre R$ 480 e 490 mil), sinal de um teto por tomador.
- Três contratos no teto em 5 meses, sobre a mesma terra e para o mesmo fim, é o desenho de **fatiamento**: dividir um crédito de R$ 1,5 mi entre várias pessoas (parentes ou laranjas) para escapar do limite.

**Passo a passo:**
1. No Google Earth, abra *Caso 5*. Veja se a gleba e o CAR de 632 ha são pasto em uso. São 402 matrizes; o CAR inteiro comporta isso.
2. Confira se a fazenda tem estrutura para mais 400 vacas: currais, aguadas, divisão de pastos. Compare imagens de 2024 e 2025.
3. Este é o caso **mais fraco em dados públicos**. A pergunta decisiva é se os três tomadores são a mesma pessoa (violaria o teto) ou pessoas diferentes que de fato produzem ali (legítimo). Laranjas só aparecem com o CPF.

**O que derruba a suspeita:** três membros da família, cada um produtor de verdade, com atividade própria na mesma fazenda. Isso é comum e permitido.

---

## Se algum caso se confirmar
- Anote o que viu: datas das imagens, prints, o que a consulta do CAR mostra.
- Os canais são o **Banco Central** (canal de denúncias/reclamações no site do BCB, citando os números de operação do Sicor), a **ouvidoria do banco** envolvido ou o **Ministério Público Federal** (crédito rural com recurso público).
- Os números de operação (`REF_BACEN`) bastam para o BCB e o banco localizarem os contratos. Você não precisa saber quem são os tomadores.

## O que mudou em relação à primeira lista
Revisando os casos, corrigi dois erros do método:
- **Catalão (4 contratos de R$ 500 mil em 3 dias) era falso positivo.** As quatro glebas não se sobrepõem. O agrupamento as ligou porque todas estavam dentro de uma gleba maior da mesma fazenda. O critério passou a exigir glebas quase idênticas (interseção acima de 80% da **maior**).
- **A comparação de CARs olhava só o primeiro da lista.** Agora compara o conjunto.
- **Silvânia (cerca de 200 animais em 20 ha) perdeu força.** Parte é gado leiteiro, que pode ser intensivo, e os dois CARs juntos somam 55 ha.
- Entraram os casos de **Porangatu** (o embargo no CAR informado só apareceu nesta revisão) e de **Palestina de Goiás**.
