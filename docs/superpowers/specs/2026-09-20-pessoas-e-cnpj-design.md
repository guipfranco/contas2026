# Quem dá e quem recebe: cobertura de CNPJ, ficha de pessoa e o fluxo longo

Desenho fechado com Guilherme em 20/09/2026. Três entregas, uma sessão de execução.
O rascunho de tela aprovado está em `docs/rascunhos/pessoas.html`, com dado real de
Roraima em `docs/rascunhos/dados.js`.

## Por que, com os números que motivaram

Tudo abaixo foi medido em 20/09/2026 contra o que estava publicado, não estimado.

- São **46.192 CNPJ** fornecedores no país e **23.197** têm cadastro da Receita. Isso
  cobre **97,2 %** do dinheiro pago a empresas (R$ 2,44 bi de R$ 2,51 bi), mas a
  cobertura é de 97 % acima de R$ 10 mil, **27,8 %** entre R$ 1 mil e R$ 10 mil e
  **zero** abaixo de R$ 1 mil. Faltam 22.518 empresas somando R$ 37,9 mi.
- Dessas, **76 estão acima de R$ 10 mil** e somam R$ 2,7 mi. Elas não são cauda: são
  empresas que entraram nos dados do TSE depois de 18/09, quando a fila foi montada.
  Ficar dias com `sem_receita` sempre deixa o topo da fila para trás.
- O teto de 8 sócios por empresa é apertado para **101 empresas** (0,4 % das que têm
  cadastro). Tirar o teto custa poucos KB.
- O agregado nacional de doadores existe hoje em `agregar.py:146` com **52.198**
  doadores, alimenta o sinal B4 e o topo 30 da ficha do candidato, e é **descartado no
  fim da rodada**. Não há ficha, ranking nem arquivo de doador.
- `ident.ident()` é função do documento, não do papel: **o mesmo CPF ou CNPJ que doou e
  forneceu já cai no mesmo identificador hoje**. A ficha única não precisa de tabela de
  ligação nenhuma.
- As duas máscaras coincidem. A Receita publica o sócio como `***903184**` e o TSE
  publica o doador como `***.903.184-**`: **os mesmos seis dígitos, nas mesmas
  posições**. Dá para casar sócio com doador sem que ninguém tenha o CPF inteiro.
  Verificado no CNPJ 06.983.735/0001-69 contra a doação de Roraima.

Referência olhada: Radar do Voto. Eles têm painel de campanhas com aba de doadores e um
painel de doadores à parte, com ficha por entidade e endereço em hash opaco. **Nada liga
o doador ao fornecedor**, e é essa a lacuna que a ficha única preenche.

## Entrega 1: cobertura total de CNPJ e o quadro societário inteiro

`pipeline/enriquecer.py`:

- `enxugar` para de cortar o QSA em 8 e passa a guardar, por sócio, um dicionário com
  `nome`, `qualificacao` e `doc` (o parcial que a Receita devolve, no formato
  `***903184**`, sem reformatar). Hoje a lista é de strings; passa a ser de objetos, e
  `escrever.py:392` e o front precisam acompanhar.
- O cache fica em uns 18,5 MB na branch `dados`, contra 9,33 MB hoje. Não vai ao ar.

**A ordem importa, e errá-la desperdiça horas de coleta.** `fila_prioridade` pula todo
CNPJ que já respondeu, então uma rodada longa feita **antes** desta entrega grava os
22.518 no formato velho e eles nunca mais voltam para a fila: ficariam sem qualificação
e sem documento parcial para sempre. Pelo mesmo motivo, os 23.197 que já estão no cache
também não ganham os campos novos sozinhos.

Por isso a entrega inclui uma **revisita**: `fila_prioridade` passa a devolver também
quem está no cache com sócio gravado no formato antigo, ou seja com `socios` de strings.
Quem nunca teve sócio no QSA não precisa voltar, porque não há campo novo a preencher
para ele. São 16.363 empresas a revisitar mais 22.518 a estrear, e a ordem continua
sendo o valor recebido.

Rodada: **três a quatro execuções** de `gh workflow run diario.yml` **sem**
`sem_receita`. Cada uma consulta ~12 mil (orçamento de 4.800 s a 2,5 req/s). Não
cancelar no meio: o cache só é gravado na branch `dados` no fim.

Testes novos: um QSA com 12 sócios sai com 12; um sócio sem nome não entra; e uma
entrada de cache no formato antigo volta para a fila, enquanto uma no formato novo não
volta.

## Entrega 2: a ficha de pessoa e a dimensão de doador

### Pipeline

- `agregar.py`: o dicionário nacional de doadores deixa de ser descartado. Ele já traz
  valor, número de doações, nome, origem e quantas candidaturas. Acrescentar o partido e
  o cargo de cada candidatura beneficiada, que é o que a ficha mostra.
- `escrever.py`: as fichas de `forn/` deixam de ser "de fornecedor" e passam a ser de
  quem aparece no dinheiro. A ficha ganha o bloco `doou` (total, número de candidaturas,
  topo delas com partido e cargo) ao lado do `recebeu` que já existe. Para pessoa
  física, ganha `socio_de`: as empresas em que aquele documento parcial mais o nome
  batem com o QSA, cada uma com o que ela recebeu.
- **O piso de pessoa física passa a medir a soma dos papéis.** `PISO_FICHA_PF` continua
  em R$ 10 mil, mas aplicado a recebido mais doado. Sem isso, quem doou R$ 50 mil e não
  forneceu nada continuaria sem página.
- `doador-recorte/<UF>.json`, espelhando `forn-recorte/`: lista geral, por partido, por
  cargo e por célula, com o topo e quantos ficaram de fora somando quanto. O mesmo
  motivo de existir: a linha do ranking não diz quem doou, e 52 mil fichas não cabem no
  aparelho de ninguém.
- `validar.py`: sentinela de tamanho irmã de `LIMITE_RECORTE_MB`, e a conferência da
  forma da linha nova.

O casamento sócio com doador é por **nome normalizado mais os seis dígitos**. Sem os
seis dígitos batendo, não há vínculo: nome igual sozinho não vira a mesma pessoa.

### Front

- Sexta dimensão na barra, `v=doador`, com a mesma mecânica das outras cinco: os filtros
  sobrevivem à troca e o que não recorta fica desligado mostrando o valor guardado.
- Selo de tipo por doador, em quatro cores frias e distintas: pessoa física, empresa,
  partido e outra campanha. **Nenhuma pertence à escala do sinal e nenhuma identifica
  partido.** Na linha da lista o nome vem primeiro, em 16,5 px e peso 700, e o selo
  desce para a linha de baixo, em 10,5 px, ao lado do documento.
- A ficha mostra os papéis lado a lado e, para pessoa física, a seção "onde este nome
  aparece": campanhas, partidos alcançados, cargos em disputa e as empresas em que
  consta como sócio.
- Medido em Roraima: **98,2 %** do valor dos 45 maiores doadores é repasse partidário,
  1,6 % pessoa física, 0,1 % outra campanha. Sem o chip que separa os tipos, a lista é
  só partido e a pessoa física nunca aparece.

### A trava, escrita aqui porque é o ponto mais perto dela

A ficha **descreve**. Ela põe dois fatos de registro público um embaixo do outro, não
soma os valores dos dois papéis num total, não chama a coincidência de padrão e **não
gera sinal**. Nenhum alarme novo cruza sócio com candidato ou doador com fornecedor
nesta entrega. Se um dia for para existir, começa pela redação, não pelo código.

## Entrega 3: a visão geral rearranjada e o fluxo longo

### Ordem nova da tela

Hoje a grade `gradeg` tem cargos e estados na coluna fina, partidos e candidaturas
dividindo as duas linhas, e embaixo a fonte do dinheiro sobre os tipos de despesa com os
maiores fornecedores ao lado; os dois fluxos vêm depois, em `gradefx`.

A ordem passa a ser:

1. cargos, estados, partidos e as maiores candidaturas (como hoje);
2. o fluxo **do partido para as maiores candidaturas**, que sobe para cá;
3. o **fluxo longo** novo;
4. a fonte do dinheiro, os tipos de despesa e os maiores fornecedores, que descem.

Implicação de código: os cartões do bloco 4 saem de `#gradeg` para uma terceira grade, e
`corpoDoCartao` procura por `'#gradeg > ' + sel`. O alinhamento por corte precisa saber
em qual grade cada cartão está, ou o bloco 4 deixa de alinhar em silêncio.

### O fluxo longo

Substitui "Do partido para os maiores fornecedores" por quatro colunas:
**doadores, partidos, candidaturas, fornecedores.**

**O problema que precisa de decisão declarada:** esse fluxo não conserva o dinheiro. A
primeira metade é receita e a segunda é despesa, e elas não são o mesmo número. A regra
da visão geral é "uma medida só na tela inteira", e aqui ela não tem como valer.

Recomendação: a candidatura é o funil, e o desenho **declara a quebra no meio**, como o
Polimoney japonês faz (receita, total, despesa). A legenda embaixo diz, com número: de
um lado entra o declarado como receita, do outro sai o contratado, e os dois não
fecham. As alternativas descartadas são normalizar as larguras, que inventa uma medida
que não existe, e partir em dois desenhos, que é o que já temos hoje.

A regra de escala de 19/09 se generaliza: uma escala para todas as colunas enquanto o
menor nó listado ainda ganhar 13 px nela; quando não ganha, cada coluna passa a ter a
sua, e a legenda diz qual dos dois casos vale. O nó "outros" de cada coluna entra fora
de escala, com teto de 32 % e o rótulo dizendo isso.

Abaixo de 1000 px de largura, quatro colunas não cabem com nome legível. Proposta: o
fluxo longo cai para o desenho de duas colunas que já existe, mais a tabela irmã.
**Confirmar no wireframe antes de codar.**

### O dado que o fluxo longo precisa

O front não tem como refazer essa conta: ele não conhece doador nem fornecedor por
candidatura. Então nasce `fluxo/<UF>.json`, irmão de `forn-cruzado/`, com, para cada
recorte, o topo de cada uma das quatro colunas e as ligações exatas entre colunas
vizinhas, mais o nó "outros" de conta exata em cada uma.

**Começar só pelos recortes geral, partido e cargo, sem a célula.** `forn-cruzado` já
ensina que o arquivo cresce pelo produto dos eixos, e aqui são quatro. Medir e só então
decidir se a célula entra. Sentinela nova no validador, irmã de
`LIMITE_FORN_CRUZADO_MB`.

## Testes

- A suíte roda contra a fixture de Roraima, como sempre: `python -m unittest discover -s tests`.
- Somar as quatro colunas do fluxo longo pelas ligações tem de dar o total de cada nó,
  inclusive o "outros".
- O casamento sócio com doador não pode ligar dois nomes iguais com documentos parciais
  diferentes.
- A ficha de pessoa física só existe acima do piso, agora medido sobre os dois papéis.
- `TestHigieneDoFonte` continua varrendo caractere de controle. Nenhum arquivo novo deste
  plano pode ser gravado por heredoc de shell.
- O validador roda antes de publicar e a rodada falha se ele apontar qualquer coisa.

## Riscos conhecidos

- **Tamanho.** As fichas vão de 25,8 MB para uns 31 MB com a cobertura total de
  cadastro, mais o recorte de doador e o arquivo de fluxo. O visitante continua baixando
  um bloco de 6 KB, mas o artifact do Pages cresce.
- **Documento parcial em branch pública.** O campo novo do sócio vai para a branch
  `dados`, que é pública. É decisão tomada por Guilherme em 20/09, pelo ganho de
  desambiguar homônimo, e o formato é o que a Receita já publica.
- **A leitura da ficha de pessoa física.** É a tela do projeto que mais se aproxima de
  parecer acusação, mesmo sem nenhuma palavra proibida. O wireframe existe para essa
  decisão ser tomada olhando a tela pronta.
- **`CONTAS_SAL`.** Rodada de produção sem ele não publica ficha de pessoa física, e
  agora isso vale também para a ficha de doador pessoa física.

## Como executar

**Não executar nesta sessão.** Abrir uma sessão nova, com **Opus 5 e esforço médio**, e
fazer as três entregas de uma vez, nesta ordem:

1. Entrega 1 inteira, com o teste, e disparar a primeira rodada longa em segundo plano.
2. **Wireframe navegável primeiro**, com a fixture de Roraima, para Guilherme aprovar a
   tela antes de qualquer linha em `site/index.html`. O de `docs/rascunhos/pessoas.html`
   já cobre a lista de doadores e a ficha de pessoa; falta o fluxo longo e a ordem nova
   da visão geral.
3. Entrega 2, pipeline antes do front.
4. Entrega 3.

Rodada de conferência local, que não exercita o tamanho nacional:

```bash
python -m unittest discover -s tests
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita \
    --site site/dados --estado /tmp/estado
python -m pipeline.validar site/dados
cd site && python -m http.server 8777
```

Publicação: `git push` do `main` primeiro, e só então `gh workflow run diario.yml`. O
agendamento segue pausado, com os dois `cron` comentados.
