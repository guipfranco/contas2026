# Quem foi eleito antes e quem é eleito agora

Data: 06/10/2026. Decidido com Guilherme entre 05 e 06/10/2026, na conversa que
abriu este trabalho. Branch `eleitos-sankey`, numa worktree própria.

## O que é

Uma entrada nova na barra, **Eleitos** (`v=eleitos`), com um Sankey de duas
colunas: à esquerda, quem foi eleito na eleição anterior, por partido; à direita,
quem é eleito em 2026, por partido. A altura de cada nó é o número de pessoas; a
faixa liga a mesma pessoa nas duas eleições. Lê-se ali o tamanho de cada bancada
nos dois anos, quem se reelegeu, quem mudou de partido, quem chegou sem ter sido
eleito antes e o que aconteceu com quem saiu.

Fora de escopo, de propósito: a eleição municipal de 2024 (o vereador eleito
deputado entra como "não tinha sido eleito"; incluir 2024 é mais um conjunto
inteiro do TSE); qualquer cruzamento com o dinheiro da campanha (gasto de
reeleito contra novato, por exemplo), que precisa de redação própria; mandato em
exercício (ver Redação).

## A eleição de comparação

| cargo em 2026 | comparado com |
|---|---|
| Presidência, governo, Câmara dos Deputados, Assembleia Legislativa, Câmara Legislativa do DF | 2022 |
| Senado | 2018 |

O Senado de 2026 renova as 54 cadeiras eleitas em 2018. Quem se elegeu senador em
2022 tem mandato até 2031 e não está nessa disputa. `[decidido, Guilherme 06/10/2026]`

**"Eleito antes"** é o conjunto de quem foi eleito em 2022 para qualquer um dos
cargos da tabela, mais quem foi eleito senador em 2018. Vice e suplente de senador
não entram nos nós.

## A continuidade

"Segue eleito" vale para **qualquer cargo** `[decidido, Guilherme 06/10/2026]`: a
deputada eleita em 2022 e eleita senadora em 2026 é continuidade, e não novata.

Destino de cada pessoa eleita antes, visto de 2026, nesta ordem de precedência
(a primeira que vale decide; o número é o código gravado no arquivo):

- **1, reeleita no mesmo cargo**: eleita em 2026 para o mesmo cargo e a mesma UF;
- **2, eleita para outro cargo**: eleita em 2026 para outro cargo dos contados, ou
  para o mesmo cargo em outra UF;
- **3, 2º turno**: candidatura de 2026 com desfecho 4;
- **4, concorreu a vice ou suplência**: a candidatura de 2026 dela é a vice ou a
  suplente de senador, qualquer que seja o desfecho;
- **5, concorreu e não se elegeu**: tem candidatura em 2026 nos cargos contados,
  com desfecho 2 (suplente) ou 3 (não eleita);
- **7, sem resultado publicado**: tem candidatura em 2026 nos cargos contados, com
  desfecho 0 (o TSE não publicou resultado para ela: renúncia, candidatura
  indeferida, sub judice, ou totalização que ainda não chegou);
- **6, sem candidatura registrada em 2026**.

O destino 7 existe porque "concorreu e não se elegeu" é uma afirmação sobre uma
pessoa nomeada, e o desfecho 0 não a sustenta: em 05/10 eram 1.095 candidaturas
nos cargos contados sem resultado, muitas delas renúncias e indeferimentos. Ele
leva o número 7, e não entra entre o 5 e o 6, para os números que já existiam não
mudarem de sentido; na tela, o nó dele fica entre "não se elegeram" e "sem
candidatura".

Quem tem mais de uma candidatura em 2026 (caso raro, em geral substituição) é
lido pela de melhor desfecho, na ordem acima; uma candidatura com resultado
publicado vence uma sem.

Quem foi eleito em 2018 e de novo em 2022 (o senador de 2018 que se elegeu
governador em 2022) é lido pelo registro de 2022: uma pessoa aparece uma vez só
em cada lado. A contagem de cadeiras do validador usa o arquivo bruto, sem essa
junção, e por isso bate com o número de cadeiras.

## Partido sucessor

Tabela à mão, `dados/sucessao-partidos.csv`, com colunas `antigo`, `sucessor`,
`data`, `ato` (a resolução do TSE que aprovou a fusão ou incorporação). Linhas
iniciais, a conferir contra o ato antes do commit: PTB e Patriota para PRD; PSC
para Podemos; PROS para Solidariedade. A sucessão é transitiva (se A virou B e B
virou C, A vira C).

Uma pessoa **mudou de partido** quando o partido de 2026 é diferente do sucessor
do partido de antes. O nó da esquerda mostra o partido **como estava na eleição
de antes** (PSC continua PSC), para a bancada de 2022 sair com o tamanho que teve;
a faixa do PSC para o Podemos não conta como mudança.

**A tabela e a frase do partido somam o lado de antes pelo sucessor; o desenho
mostra a sigla como era.** Sem isso, a coluna "Diferença" mostraria o PRD com
"+N" e o PTB e o Patriota com negativo, só pela fusão, e a frase do Podemos
deixaria de fora quem foi eleito pelo PSC. O pipeline grava em
`eleitos/BRASIL.json` o mapa `sucessor` (id do partido extinto para id do
sucessor, já transitivo), e o front usa esse mapa: na tabela, a linha do PSC some
dentro da do Podemos; com o filtro do Podemos, o nó do PSC de 2022 acende junto.
O pé da tela diz: "Na tabela, o partido extinto entra somado ao sucessor."

## O dado

### A ferramenta que roda uma vez: `ferramentas/anteriores.py`

Os anos de 2018 e 2022 não mudam, então não são baixados a cada rodada. A
ferramenta roda à mão no GitHub Actions (workflow novo, `anteriores.yml`, com
`workflow_dispatch`), porque da máquina local o CDN do TSE devolve 403. Ela baixa
`consulta_cand_2018.zip` e `consulta_cand_2022.zip`, guarda só quem foi eleito
(desfecho 1 por `pipeline.desfecho.codigo`) nos cargos da tabela, e grava
`anteriores.json` na branch `dados`, junto com o resto do estado.

Linha de `anteriores.json`:

```
{"chave": "p…", "chave_nasc": "p…", "ano": 2022, "cargo": "DEPUTADO FEDERAL",
 "uf": "SP", "partido": "PSC", "nome_urna": "…", "genero": "F"}
```

- `chave` é `ident.ident(cpf)`: HMAC com a `CONTAS_SAL`. `chave_nasc` é o mesmo
  HMAC sobre `NOME NORMALIZADO|AAAA-MM-DD` (nome completo sem acento, caixa alta,
  espaço simples, e a data de nascimento). Nem o CPF nem a data vão para o arquivo.
- **Sem `CONTAS_SAL` no ambiente, a ferramenta para sem gravar**: com o sal de
  desenvolvimento a chave seria reversível, e o arquivo mora numa branch pública.
- Se a `CONTAS_SAL` mudar um dia, `anteriores.json` precisa ser refeito; a
  ferramenta grava `sal_marca` (os 8 primeiros hex do HMAC da string fixa
  `"anteriores"`), e a rodada diária confere essa marca antes de usar o arquivo.
- A ferramenta imprime, por ano e cargo, quantas pessoas guardou e quantas
  ficaram com CPF vazio. É o primeiro número a ler.
- **`--congelar UF` grava a fixture já anonimizada**, por
  `ferramentas/anonimizar.py`: CPF falso com dígito verificador válido (o mesmo
  falso para o mesmo CPF, em qualquer campo), título de eleitor e e-mail como
  `#NULO`, nascimento com o ano verdadeiro e dia e mês falsos; marcador de vazio
  fica como está. A chave é aleatória e vive só na memória daquela execução. Com
  `--congelar`, a ferramenta baixa também o `consulta_cand` de 2026 e congela a
  mesma UF com a mesma chave, para a ligação entre os três anos continuar de pé
  na fixture; sem ele, não baixa o 2026. O artefato do workflow vive um dia.

### A rodada diária: `pipeline/eleitos.py`

Lê `anteriores.json` do diretório de estado e as candidaturas de 2026 que
`carregar` já entrega (todas, qualquer situação, porque é preciso saber se um
eleito de antes voltou a concorrer). Liga pela `chave` primeiro, em todos os
registros; só depois, para quem sobrou, pela `chave_nasc`, e só quando um dos dois
lados não tem CPF: com CPF nos dois lados e diferente, são duas pessoas.
`carregar` passa a ler também `DT_NASCIMENTO` e o `CD_CARGO` de vice e suplente, se
ainda não lê.

Quem foi ao 2º turno tem uma linha por turno no `consulta_cand` (`NR_TURNO`), e a
do turno 2 às vezes vem antes da do turno 1. Vale a linha do turno mais alto que já
tem desfecho, aqui e em `agregar.juntar_candidaturas`; senão quem perdeu no dia
25/10 ficaria em "2º turno" para sempre.

Escreve `eleitos/BRASIL.json`:

```
{"anteriores": {"2022": {"6": 513, …}, "2018": {"5": 54}},
 "ligados_por_nome": N, "absorvidos": {"SC": 1, …},
 "fed": {"<id do partido>": <id da federação>},
 "sucessor": {"<id do partido extinto>": <id do sucessor>},
 "c": [[nome_urna, uf_antes, cargo_antes, partido_antes, ano_antes, destino,
        uf_agora, cargo_agora, partido_agora, desfecho_agora, sq_2026, genero,
        mudou], …]}
```

- Uma linha por pessoa. Quem não foi eleito antes tem `cargo_antes`,
  `partido_antes` e `destino` vazios; quem não concorreu em 2026 tem os campos de
  agora vazios e `sq_2026` vazio.
- **`sq_2026` só vai preenchido quando a candidatura tem ficha** (`cand/<sq>.json`,
  que a rodada só escreve para quem tem movimento ou sinal). Vice, suplência e
  candidatura sem movimento saem com `sq_2026` vazio, e o nome fica sem link:
  nome apontando para página que não existe é pior que nome sem link. A rodada
  passa a `escrever_eleitos` o conjunto dos sq que ganharam ficha naquele laço.
- `absorvidos` conta, por UF, os senadores eleitos em 2018 que foram eleitos para
  outro cargo em 2022: a pessoa é lida pelo registro de 2022 e sai da conta do
  Senado. A frase da tela do Senado diz quantos são, senão o número de eleitos em
  2018 sairia menor que o real.
- Entram: todo eleito de antes; toda candidatura de 2026 com desfecho 1 ou 4 nos
  cargos contados. Cerca de 3.500 linhas no país.
- Cargo e partido vão como índice dos dicionários de `meta.json`, como na linha do
  ranking; cargo de antes que não exista no dicionário de 2026 entra nele.
- `destino` é um inteiro de 1 a 7, na ordem da seção "A continuidade"; 0 para
  quem não foi eleito antes. `ano_antes` é 2018, 2022 ou 0.
- `mudou` é 1 quando o partido de agora não é o sucessor do partido de antes. O
  front não conhece a tabela de sucessão: quem decide é o pipeline.
- `fed` liga cada partido de 2026 à sua federação, para o chip de federação.
- `sucessor` liga cada partido de antes que tem sucessor na tabela ao sucessor,
  pela regra transitiva; o validador confere que os dois ids estão no dicionário.
- A UF vai dos dois lados, porque a pessoa pode ter mudado de UF.
- **Enquanto `tem_desfecho` for falso, o arquivo não é gravado** e a aba não
  aparece. Se `anteriores.json` faltar, tiver `sal_marca` diferente ou estiver
  truncado ou fora da forma, a rodada avisa e segue sem o arquivo: o resto do site
  não depende dele. Qualquer outro erro no bloco de eleitos também tira só a aba,
  com um aviso que diz o tipo do erro e nada do conteúdo da linha.

### O validador

- Forma da linha (13 campos, tipos, `destino` em 0..7 e 0 exatamente quando
  `ano_antes` é 0, índices de partido em -1 ou dentro do dicionário), e nenhum
  `sq_2026` repetido. `absorvidos`, quando existe, liga UF de duas letras a
  inteiro positivo.
- Contagem por cargo dos eleitos de antes contra as cadeiras: 513 na Câmara, 27
  governadores, 1 Presidência, 54 senadores de 2018, 1.059 entre Assembleias e
  Câmara Legislativa. A contagem de 2026 não é conferida contra número fixo: o
  tamanho da Câmara a partir de 2027 é o que o TSE publicar. Até 2 % abaixo passa (cassação, eleição anulada);
  mais que isso, ou acima do número de cadeiras, é erro: a ligação ou o filtro de
  cargo quebrou. A conferência só vale na rodada do país inteiro.
- A mesma conta (`validar.confere_cadeiras`) roda antes, em dois lugares, para um
  `anteriores.json` errado nunca congelar o site: a ferramenta, sem `--uf`, não
  grava o arquivo e sai com erro; a rodada do país não grava `eleitos/BRASIL.json`,
  avisa, e segue sem a aba.
- `ligados_por_nome` acima de 5 % dos eleitos de antes é aviso da rodada (o
  validador não tem aviso, só erro).

## A tela

### Lugar e filtros

Botão **Eleitos** no fim da barra (no fim, e não depois de Visão geral, para o
botão escondido não desalinhar a grade de quatro colunas do celular). Ele é um cruzamento, não
uma dimensão: não entra em `DIMS` como lista.

- **Cargo**: um por vez, e a aba abre na Câmara dos Deputados. Misturar cargos
  somaria deputado e senador no mesmo nó. Sem cargo no endereço, vale a Câmara;
  o chip mostra isso.
- **Estado**: recorta pela UF da cadeira (a de antes à esquerda, a de agora à
  direita). Numa tela de UF, o arquivo lido continua sendo o do país, filtrado no
  front: é pequeno, e a pessoa que mudou de UF precisa aparecer.
- **Partido**: **destaca** as faixas que tocam o partido, nos dois lados, e não
  esconde as outras. A frase de números passa a falar do partido.
- **Federação**: destaca as faixas dos partidos da federação, como o partido.
  É o mesmo sentido do chip no resto do site, que escolhe uma federação.
- Sinal, tipo de despesa, desfecho e os demais: desligados, mostrando o valor
  guardado. Entra em `foraDaDimensao()`.

### O desenho

- **Coluna da esquerda**: os partidos de antes, e dois nós: "já eleitos em outra
  disputa" (a deputada de 2022 que agora é eleita senadora, com o filtro do
  Senado) e "não tinham sido eleitos em 2022" (ou "em 2018", no Senado).
- **Coluna da direita**: os partidos de agora, e os destinos de quem saiu:
  "eleitos para outro cargo", "2º turno, a decidir em 25/10", "concorreram a vice
  ou suplência", "concorreram e não se elegeram", "sem resultado publicado", "sem
  candidatura em 2026". Os
  destinos ficam embaixo dos partidos, separados por um respiro.
- Os 10 maiores partidos de cada lado e um nó "outros N partidos", de conta exata.
  Os destinos nunca entram no "outros".
- Escala única para as duas colunas: aqui a medida é gente, e os dois lados somam
  perto do mesmo número. Altura de 520 px, como os fluxos da visão geral, e o
  desenho reaproveita o código desses fluxos.
- **Nenhuma cor por partido.** Faixas neutras; passam a cor de destaque ao passar
  por cima, ao tocar ou com o filtro de partido.
- **Tocar numa faixa** abre, embaixo do desenho, a lista das pessoas dela: nome de
  urna, UF, cargo e partido nos dois anos, desfecho de agora. Quem tem `sq_2026`
  ganha link para a ficha da candidatura.
- O nó de partido liga o filtro de partido só quando aquele partido aparece em
  2026 em alguma linha do arquivo. A sigla que só existe antes (PSC, PTB) não vira
  filtro: ele esvaziaria as outras abas.

### A frase de números

Acima do desenho, só números:

> Dos 513 eleitos para a Câmara em 2022, 280 foram eleitos de novo para a Câmara,
> 30 para outro cargo, 120 concorreram e não se elegeram e 83 não registraram
> candidatura. Dos N eleitos agora, 233 não tinham sido eleitos em 2022.

(Números de exemplo; o tamanho da Câmara eleita agora sai do dado.)

Com 2º turno pendente, entra "N disputam o 2º turno em 25/10", e as candidaturas no
2º turno que não estão do lado de antes entram também ("Outras N candidaturas
disputam o 2º turno em 25/10"), para a frase somar o mesmo que o nó. No Senado, os
`absorvidos` da UF da tela (ou do país) entram como "Outros N eleitos senadores em
2018 foram eleitos para outro cargo em 2022 e entram na comparação daquele cargo";
com o lado de antes vazio, só essa frase fica. Com ligações pelo
nome, uma nota no pé: "N pessoas de 2022 não têm CPF no arquivo do TSE e foram
ligadas pelo nome completo e pela data de nascimento."

### A tabela irmã

Embaixo do desenho, uma linha por partido: eleitos antes, eleitos agora,
diferença, e "já eleitos antes, sem mudar de partido" (quem está do lado de agora
naquele partido, foi eleito antes e tem `mudou` 0). Ordenada pelos eleitos de
agora. O lado de antes soma pelo sucessor (seção "Partido sucessor"). **No celular a tabela vem antes do
desenho.**

## Redação

- **"Eleita em 2022", nunca "deputada atual" ou "no mandato".** Suplente assumiu,
  houve cassação e morte; o TSE só sustenta a eleição.
- **"Mudou de partido"** só quando o partido novo não é o sucessor do antigo, e sem
  adjetivo.
- **"Sem candidatura registrada em 2026"**, e não "desistiu" ou "abandonou".
- No Senado, a frase e o rótulo da coluna dizem que a comparação é com 2018.
- Gênero pelo campo `genero` da linha nos rótulos de pessoa; plural dos nós no
  masculino genérico do TSE ("eleitos"), como já faz o desfecho no chip.
- Acento correto em toda string; nada de travessão; nenhuma palavra de
  `PROIBIDAS`. O teste de higiene do fonte continua valendo.

## CLAUDE.md

- "Como está por dentro": `eleitos/BRASIL.json` em `site/dados/`; `anteriores` em
  `ferramentas/`; `sucessao-partidos.csv` em `dados/`; `anteriores.json` no estado
  da branch `dados`.
- "Regras de trabalho": a comparação do Senado com 2018; continuidade em qualquer
  cargo; a regra do sucessor; que `anteriores.json` é feito uma vez, com a
  `CONTAS_SAL`, e precisa ser refeito se ela mudar.
- "O que o dado ensinou": o que a ferramenta mostrar sobre o CPF de 2018 e 2022.

## Testes

- Fixture nova: uma fatia de `consulta_cand_2022` e `consulta_cand_2018` de
  Roraima (eleitos e alguns não eleitos), congelada em `tests/fixtures/`, gerada
  por `ferramentas/investigar.py` no Actions. Como a fixture de 2026 é de antes da
  eleição, os desfechos de 2026 dos casos de teste são escritos no teste.
- Um teste por destino (1 a 7), um para a mudança de partido por sucessão (não
  conta) e sem sucessão (conta), um para a sucessão transitiva, um para a ligação
  pela `chave_nasc`, um para a candidatura dupla.
- `anteriores` sem `CONTAS_SAL` para sem gravar; `sal_marca` diferente faz a
  rodada seguir sem o arquivo.
- Rodada da fixture com `tem_desfecho` falso: `eleitos/` não existe e o validador
  passa.
- Validador: linha com 9 campos, `destino` 8 e `sq` repetido reprovam; contagem
  fora da margem reprova.
- O front não tem teste de JS; a conferência é visual, com `python -m http.server`
  sobre a saída da fixture e um `eleitos/BRASIL.json` montado à mão com os seis
  sete destinos.

## Ordem de execução

1. **Antes de escrever código**, no Actions: `inspecionar` sobre
   `consulta_cand_2018` e `consulta_cand_2022` para conferir as colunas,
   o vocabulário de `DS_SIT_TOT_TURNO` naqueles anos, e se o CPF vem preenchido.
   Se o CPF vier vazio em massa, a ligação pela data de nascimento deixa de ser
   reserva e a spec volta para conversa.
2. `dados/sucessao-partidos.csv`, conferido contra os atos do TSE.
3. `ferramentas/anteriores.py` e o workflow, com testes; rodar uma vez no Actions.
4. `pipeline/eleitos.py`, `escrever`, `validar`, `rodar`, com testes antes.
5. Front: botão, `foraDaDimensao`, desenho, frase, tabela, lista da faixa.
6. `CLAUDE.md`.
7. Rodada da fixture, validador, conferência visual, e só então merge.
