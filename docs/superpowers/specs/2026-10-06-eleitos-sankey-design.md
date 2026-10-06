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
(a primeira que vale decide):

1. **reeleita no mesmo cargo**: eleita em 2026 para o mesmo cargo e a mesma UF;
2. **eleita para outro cargo**: eleita em 2026 para outro cargo dos contados, ou
   para o mesmo cargo em outra UF;
3. **2º turno**: candidatura de 2026 com desfecho 4;
4. **concorreu a vice ou suplência**: a candidatura de 2026 dela é a vice ou a
   suplente de senador, qualquer que seja o desfecho;
5. **concorreu e não se elegeu**: tem candidatura em 2026 nos cargos contados, com
   desfecho 2 (suplente), 3 (não eleita) ou 0 (sem desfecho, o que inclui
   candidatura indeferida, cassada ou renunciada);
6. **sem candidatura registrada em 2026**.

Quem tem mais de uma candidatura em 2026 (caso raro, em geral substituição) é
lido pela de melhor desfecho, na ordem acima.

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

### A rodada diária: `pipeline/eleitos.py`

Lê `anteriores.json` do diretório de estado e as candidaturas de 2026 que
`carregar` já entrega (todas, qualquer situação, porque é preciso saber se um
eleito de antes voltou a concorrer). Liga pela `chave`; quando a pessoa de antes
não tem CPF, pela `chave_nasc`. `carregar` passa a ler também `DT_NASCIMENTO` e o
`CD_CARGO` de vice e suplente, se ainda não lê.

Escreve `eleitos/BRASIL.json`:

```
{"anteriores": {"2022": N, "2018": N}, "ligados_por_nome": N,
 "linhas": [[nome_urna, uf, cargo_antes, partido_antes, destino,
             cargo_agora, partido_agora, desfecho_agora, sq_2026, genero], …]}
```

- Uma linha por pessoa. Quem não foi eleito antes tem `cargo_antes`,
  `partido_antes` e `destino` vazios; quem não concorreu em 2026 tem os campos de
  agora vazios e `sq_2026` vazio.
- Entram: todo eleito de antes; toda candidatura de 2026 com desfecho 1 ou 4 nos
  cargos contados. Cerca de 3.500 linhas no país.
- Cargo e partido vão como índice dos dicionários de `meta.json`, como na linha do
  ranking; cargo de antes que não exista no dicionário de 2026 entra nele.
- `destino` é um inteiro de 1 a 6, na ordem da seção "A continuidade".
- **Enquanto `tem_desfecho` for falso, o arquivo não é gravado** e a aba não
  aparece. Se `anteriores.json` faltar ou tiver `sal_marca` diferente, a rodada
  avisa e segue sem o arquivo: o resto do site não depende dele.

### O validador

- Forma da linha (10 campos, tipos, `destino` em 1..6 ou vazio, índices dentro dos
  dicionários), e nenhum `sq_2026` repetido.
- Contagem por cargo dos eleitos de antes contra as cadeiras: 513 na Câmara, 27
  governadores, 1 Presidência, 54 senadores de 2018, 1.059 entre Assembleias e
  Câmara Legislativa. A contagem de 2026 não é conferida contra número fixo: o
  tamanho da Câmara a partir de 2027 é o que o TSE publicar. Diferença de até 2 % é aviso; acima disso, erro (a
  ligação ou o filtro de cargo quebrou).
- `ligados_por_nome` acima de 5 % dos eleitos de antes é aviso.

## A tela

### Lugar e filtros

Botão **Eleitos** na barra, depois de **Visão geral**. Ele é um cruzamento, não
uma dimensão: não entra em `DIMS` como lista.

- **Cargo**: um por vez, e a aba abre na Câmara dos Deputados. Misturar cargos
  somaria deputado e senador no mesmo nó. Sem cargo no endereço, vale a Câmara;
  o chip mostra isso.
- **Estado**: recorta pela UF da cadeira (a de antes à esquerda, a de agora à
  direita). Numa tela de UF, o arquivo lido continua sendo o do país, filtrado no
  front: é pequeno, e a pessoa que mudou de UF precisa aparecer.
- **Partido**: **destaca** as faixas que tocam o partido, nos dois lados, e não
  esconde as outras. A frase de números passa a falar do partido.
- **Federação**: agrupa os partidos de cada federação de 2026 nos dois lados.
- Sinal, tipo de despesa, desfecho e os demais: desligados, mostrando o valor
  guardado. Entra em `foraDaDimensao()`.

### O desenho

- **Coluna da esquerda**: os partidos de antes, e um nó "não tinham sido eleitos
  em 2022" (ou "em 2018", no Senado).
- **Coluna da direita**: os partidos de agora, e os destinos de quem saiu:
  "eleitos para outro cargo", "2º turno, a decidir em 25/10", "concorreram a vice
  ou suplência", "concorreram e não se elegeram", "sem candidatura em 2026". Os
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

### A frase de números

Acima do desenho, só números:

> Dos 513 eleitos para a Câmara em 2022, 280 foram eleitos de novo para a Câmara,
> 30 para outro cargo, 120 concorreram e não se elegeram e 83 não registraram
> candidatura. Dos N eleitos agora, 233 não tinham sido eleitos em 2022.

(Números de exemplo; o tamanho da Câmara eleita agora sai do dado.)

Com 2º turno pendente, entra "N disputam o 2º turno em 25/10". Com ligações pelo
nome, uma nota no pé: "N pessoas de 2022 não têm CPF no arquivo do TSE e foram
ligadas pelo nome completo e pela data de nascimento."

### A tabela irmã

Embaixo do desenho, uma linha por partido: eleitos antes, eleitos agora,
diferença, reeleitos (destinos 1 e 2 que ficaram no mesmo partido ou no
sucessor). Ordenável, como as outras tabelas. **No celular a tabela vem antes do
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
- Um teste por destino (1 a 6), um para a mudança de partido por sucessão (não
  conta) e sem sucessão (conta), um para a sucessão transitiva, um para a ligação
  pela `chave_nasc`, um para a candidatura dupla.
- `anteriores` sem `CONTAS_SAL` para sem gravar; `sal_marca` diferente faz a
  rodada seguir sem o arquivo.
- Rodada da fixture com `tem_desfecho` falso: `eleitos/` não existe e o validador
  passa.
- Validador: linha com 9 campos, `destino` 7 e `sq` repetido reprovam; contagem
  fora da margem reprova.
- O front não tem teste de JS; a conferência é visual, com `python -m http.server`
  sobre a saída da fixture e um `eleitos/BRASIL.json` montado à mão com os seis
  destinos.

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
