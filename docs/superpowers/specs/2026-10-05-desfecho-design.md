# O desfecho da urna na lista

Data: 05/10/2026. Decidido com Guilherme nesta data, com o rascunho em
https://claude.ai/artifact/JwroewfM6p6iULqKgKB6HF (versão 5, bloco V2).

## O que é

O primeiro turno aconteceu em 04/10/2026. A lista de candidaturas passa a dizer,
em cada linha, o desfecho da urna (eleita, suplente, não eleita, segundo turno),
e ganha um filtro por desfecho. Nada mais muda de lugar: nem cartão novo na banda,
nem frase de subcabeçalho, nem cartão na visão geral. O chip de filtro, com a
contagem de cada opção, é o que resume o recorte.

Fora de escopo, de propósito: reais por voto (pede o conjunto de votação nominal
do TSE, outra fonte); qualquer conta que junte sinal e desfecho ("entre os eleitos,
N têm sinal", que lê como acusação e precisa de redação própria); cartão de
desfecho na visão geral.

## O dado

O desfecho vem de `DS_SIT_TOT_TURNO`, no arquivo `consulta_cand` da Consulta de
Candidaturas, que `carregar.py` já lê como `Cand.sit_turno`. Até a eleição ele
vinha `#NULO` em 100 % das linhas; o TSE o preenche depois da totalização.

**Verificação obrigatória, antes de confiar no mapeamento:** rodar
`python -m ferramentas.inspecionar` no GitHub Actions (da máquina local o CDN do
TSE devolve 403) e anotar as grafias reais que o campo traz em 2026. O vocabulário
abaixo é o histórico do TSE e pode ter mudado.

### Código do desfecho

`agregar.Agg` ganha `sit_turno` (texto do TSE, como veio). `escrever` o traduz
para um inteiro pequeno, por função `codigo_desfecho(texto)`:

| código | significado | textos do TSE (comparação sem acento, caixa alta, sem espaço duplo) |
|---|---|---|
| 0 | sem desfecho | `#NULO`, `#NULO#`, `-1`, `#NE`, vazio, e qualquer texto não reconhecido |
| 1 | eleita | `ELEITO`, `ELEITO POR QP`, `ELEITO POR MEDIA` |
| 2 | suplente | `SUPLENTE` |
| 3 | não eleita | `NAO ELEITO` |
| 4 | segundo turno | `2º TURNO`, `2O TURNO`, `SEGUNDO TURNO` |

Texto não reconhecido vira 0 **e** conta num aviso do validador (não erro): a
rodada publica, e o aviso diz quais textos ficaram de fora, para o mapa ser
corrigido na rodada seguinte sem derrubar o site.

### A linha do ranking

A linha da UF passa de 16 para 17 campos; a do Brasil, de 17 para 18. O campo novo
é o último, `desfecho`, inteiro em 0..4. Na linha do Brasil a UF continua no índice
16 e o desfecho vai para o 17. A linha enxuta (candidatura sem movimento e sem
sinal) também carrega o campo, porque uma candidatura sem gasto pode ter sido
eleita e o filtro precisa achá-la.

`validar.py`: confere 17 e 18 campos, e `0 <= desfecho <= 4`. A mensagem de erro
existente ("linha com N campos, esperado 16") muda os números.

### A ficha

`cand/<sq>.json` ganha `desfecho` (o código) e `desfecho_tse` (o texto literal do
TSE, limpo de marcador de vazio, ou `null`). A tela escreve o texto como o TSE
escreve, só ajustando caixa: "Eleita por quociente partidário" sai de `ELEITO POR
QP` pela tabela de rótulos do front, com o gênero da candidatura.

### O meta

`meta.json` ganha `tem_desfecho` (booleano: alguma linha do país tem código
diferente de 0) e `desfecho_em` (data da rodada em que `tem_desfecho` ficou
verdadeiro pela primeira vez, ou `null`; é a data que a ficha cita como "TSE,
dd/mm/aaaa"). Com `tem_desfecho` falso o front não desenha chip nem pastilha:
a tela fica exatamente como hoje.

`desfecho_em` precisa sobreviver entre rodadas, então vai no estado da branch
`dados` junto com o total de ontem.

## O front

### O chip

Chip `Desfecho`, depois de `Partido` na barra. Opções e ordem: Eleitas, Suplentes,
Não eleitas, 2º turno, Todas. Cada opção mostra a contagem no recorte atual,
calculada no front sobre `passa()` ignorando o próprio filtro de desfecho. A opção
"2º turno" só aparece se a contagem dela é maior que zero. Estado `S.desf`
(`''`, `'1'`, `'2'`, `'3'`, `'4'`), no endereço como `d=`, e sobrevive à troca de
dimensão como os outros filtros.

Em `fornecedor`, `doador` e `geral` o chip fica **desligado**, mostrando o valor
guardado, pelo mesmo motivo de sinal e federação: `forn-recorte/`,
`doador-recorte/` e `forn-cruzado/` são somados no pipeline por partido e cargo e
não sabem honrar o desfecho. Entra em `foraDaDimensao()`.

Rótulos no plural feminino ("Eleitas", "Não eleitas") porque o substantivo
subentendido é "candidaturas", que é quem presta contas.

### A linha

Pastilha de atributo nova, **a primeira da fileira** `.chips-attr`, só quando
`tem_desfecho` e o código é diferente de 0. Rótulo no gênero da candidatura (campo
13 da linha): "Eleita"/"Eleito", "Suplente", "Não eleita"/"Não eleito",
"2º turno".

**Cor por desfecho, a única exceção à regra "nenhuma cor depende do dado"**
`[decidido, Guilherme 05/10/2026]`. É a versão V2 do rascunho:

| desfecho | claro (fundo / fio / tinta) | escuro (fundo / fio / tinta) |
|---|---|---|
| eleita | `#DDF3E4` / `#1E7A46` / `#0F4A2A` | `#123A24` / `#3FA96A` / `#BFEBCF` |
| não eleita | `#FBE3E1` / `#B3261E` / `#7A1A14` | `#3E1613` / `#D9534A` / `#F5C4BF` |
| suplente | `#DCE8F5` / `#2F5F8F` / `#1B3A58` | `#14283D` / `#6FA3D8` / `#C6DCF2` |
| 2º turno | igual a suplente | igual a suplente |

Fio de 2 px. Tokens novos no `:root` (`--des1`, `--des1b`, `--des1tx`, e assim por
diante), definidos no claro e redefinidos no escuro.

Por que assim: o desfecho é fato da urna, não leitura do painel, então colorir não
imputa nada. O suplente é azul, e não amarelo nem laranja, porque a escala de
sinal inteira é quente (amarelo, âmbar, laranja queimado) e uma pastilha quente
ao lado do selo de sinal leria como sinal. O vermelho da não eleita é exceção
declarada à decisão de 17/09 que o tirou do painel: ali ele leria como veredito
sobre conduta; aqui ele diz um resultado que o TSE publicou.

### A ficha

Primeiro par da grade de contas: em cima o rótulo do TSE com gênero ("Eleita por
quociente partidário", "Eleito por média", "Suplente", "Não eleita", "2º turno"),
embaixo "Desfecho do 1º turno, TSE, dd/mm/aaaa" com `meta.desfecho_em`. Se o
código é 0 e `tem_desfecho` é verdadeiro, o par diz "Sem desfecho publicado". Se
`tem_desfecho` é falso, o par não existe.

Tabela de rótulos da ficha, por texto do TSE normalizado: `ELEITO` → "Eleita/o";
`ELEITO POR QP` → "Eleita/o por quociente partidário"; `ELEITO POR MEDIA` →
"Eleita/o por média"; `SUPLENTE` → "Suplente"; `NAO ELEITO` → "Não eleita/o";
segundo turno → "2º turno". Texto fora da tabela sai como veio, em caixa baixa com
a primeira letra maiúscula.

## Redação

Toda string nova de interface com acento correto; nada de travessão. Nenhuma das
palavras de `PROIBIDAS`. O teste de higiene do fonte continua valendo.

## CLAUDE.md

Entra um item em "Regras de trabalho": a exceção de cor, com a tabela de motivos
acima resumida, o vocabulário do código 0..4, e a troca "16 e 17 campos" por "17 e
18 campos" no item da forma da linha. Entra também, em "O que o dado ensinou", que
`DS_SIT_TOT_TURNO` mora no `consulta_cand` e muda depois da totalização.

## Testes

- `codigo_desfecho`: uma asserção por texto da tabela, mais acento e caixa
  variados, mais os quatro marcadores de vazio, mais texto desconhecido.
- A fixture de Roraima é de antes da eleição: a rodada completa sobre ela deve
  produzir `tem_desfecho = false`, todas as linhas com 0, e o front sem chip.
- Linha com 17 e 18 campos: o teste que hoje conta campos muda, e `validar` reprova
  linha com 16.
- Validador aceita 0..4 e reprova 5.
- Teste do rótulo com gênero não existe no front (não há teste de JS no
  repositório); a conferência é visual, com `python -m http.server` sobre a saída
  da fixture mais um `uf/RR.json` editado à mão com os quatro códigos.

## Ordem de execução

1. Em paralelo com tudo: disparar `inspecionar` no Actions e ler as grafias de
   `DS_SIT_TOT_TURNO`. Se o campo ainda vier `#NULO` em tudo, o trabalho segue e a
   tela só muda quando o TSE publicar.
2. Pipeline: `agregar` → `escrever` (linha, ficha, meta, estado) → `validar`, com
   os testes antes de cada um.
3. Front: tokens e CSS, chip e `passa()`, pastilha, ficha, `foraDaDimensao`.
4. `CLAUDE.md`.
5. Rodada da fixture, validador, conferência visual, e só então merge.

## Desvios registrados na implementação

- "Aviso do validador" virou `meta.desfecho_desconhecidos` mais uma linha de aviso na saída de `rodar`: o validador não tem canal de aviso, só de erro, e abrir um só para isso era mais código que a informação vale.
- Na ficha, o desfecho não é um par da grade de contas: a ficha não tem grade de pares no cabeçalho, tem a fileira de pastilhas da linha e uma linha de texto embaixo. A pastilha colorida vai na fileira, como primeira, para quem chega da lista reconhecer o que viu; e a linha de texto embaixo escreve o texto do TSE e a data.
