# contas2026, instruções do project

Painel público dos gastos de campanha da eleição de 2026, a partir da prestação de contas que o TSE publica em dados abertos. No ar em `https://guipfranco.github.io/contas2026/`, com a URL ainda não divulgada e `noindex` na página.

**Este repositório é neutro e não tem ligação com nenhuma campanha** `[decidido, Guilherme 17/09/2026]`. Nada de marca, de partido ou de candidato aqui dentro. O repositório é público; nunca entre com segredo, e-mail pessoal ou dado que não seja do TSE.

## A trava que vale mais que qualquer funcionalidade

**Um sinal não é uma acusação, e o índice de conferência também não é.** O painel aponta, pelo nome, fornecedores e candidatos reais. Uma pessoa apontada injustamente precisa poder olhar a tela e reconhecer que ela não a acusou de nada.

Quatro regras de redação, verificadas por teste a cada rodada:

1. **Número antes de adjetivo.** "Fornecedor aberto há 47 dias" é um fato. "Fornecedor de fachada" é uma afirmação sobre gente que este painel não sustenta.
2. **Nenhuma palavra que impute conduta.** A lista está em `PROIBIDAS`, em `pipeline/alarmes/__init__.py`, e o teste reprova a rodada inteira se uma delas aparecer. Fora da lista mas igualmente barrados na interface: "risco", "suspeição", "score de irregularidade".
3. **A explicação inocente vem junto**, quando existe uma comum. Rateio de material entre candidatos é legal e produz o mesmo padrão de nota repetida; quem lê precisa saber disso na mesma linha.
4. **CPF sempre mascarado, e em todo campo.** O TSE publica o número inteiro; repetir isso num painel fácil de varrer é outra coisa. **A máscara do campo do documento não basta:** a razão social de MEI é o nome da pessoa com o CPF colado, e o número inteiro ia ao ar no campo mais visível da ficha. Quem limpa é `carregar.limpar_nome`, e só quando o dígito verificador fecha. **Isso vale também para o que não é tela**: até 17/09 o arquivo de estado `fornecedores-vistos.txt`, na branch pública `dados`, guardava 419.531 documentos em texto puro, e uma lista pronta é mais fácil de varrer que o painel. Hoje ele guarda o que `pipeline/ident.py` devolve.

**A cor do sinal sobe de intensidade, e para antes do vermelho** `[decidido, Guilherme 17/09/2026]`. A escala é amarelo, âmbar e laranja queimado, com o fundo virando cor no grau 3 e a espessura do fio da esquerda crescendo junto, para quem não separa as cores. Vermelho fica de fora por decisão: num painel que aponta gente pelo nome, ele lê como veredito, não como "confira".

**Português do Brasil com acentuação correta em todo texto de interface.** Há um teste que reprova f-string de mensagem sem acento. **Nunca use travessão.**

**Os testes de redação passaram três meses sem testar nada, e isso pode acontecer de novo.** Um heredoc de shell decodificou `\b` e gravou um caractere de backspace (0x08) dentro das expressões regulares de `tests/test_pipeline.py`: os três testes aprovavam qualquer conteúdo, e 46 sinais foram ao ar sem acento. Corrigido em 17/09, com `TestHigieneDoFonte` varrendo o repositório atrás de caractere de controle. **Nunca grave código com barra invertida por heredoc**: escreva o arquivo com a ferramenta de edição.

## O que o dado ensinou, e que não está no manual do TSE

**Somar todas as linhas de despesa é o certo.** `SQ_DESPESA` não identifica uma linha: identifica um grupo, uma nota com vários itens. Medido nos dois caminhos: somando tudo, nenhum candidato aparece com pagamento maior que a despesa contratada; deduplicando por `SQ_DESPESA`, 72 candidatos de Roraima ficam impossíveis, com R$ 2,6 milhões de excesso. O teste `test_somar_tudo_nunca_deixa_pago_maior_que_contratado` guarda a decisão. **Não tente deduplicar.**

**Só o arquivo BRASIL é lido.** São 26 arquivos por UF mais o BRASIL, e o Distrito Federal não está entre eles. Ler por UF perderia o DF inteiro e os cargos nacionais. Quem agrupa por UF é o pipeline, pela coluna `SG_UF`. A unidade eleitoral `BR` é a Presidência.

**O marcador de vazio tem quatro formas:** `#NULO`, `#NULO#`, `-1` e `#NE`, no mesmo arquivo, em colunas diferentes.

**As despesas pagas não trazem o candidato.** Ligam pelo `SQ_PRESTADOR_CONTAS`, e 100% delas acham dono.

**O CDN do TSE devolve 403 a qualquer cliente automático da máquina local**, com qualquer user-agent, em curl, urllib e PowerShell. Só o Chrome passa. No runner do GitHub Actions, um user-agent de Chrome com os cabeçalhos de navegação passa. Por isso o pipeline roda lá e não aqui. `python -m pipeline.baixar --spike` refaz o diagnóstico. Para trabalhar com dado nacional na máquina, baixe os zips pelo Chrome e use `--fonte-local`.

**Origem de receita e fonte de receita são colunas diferentes, e confundi-las inverte o sentido da tela.** `DS_ORIGEM_RECEITA` diz como o partido classificou o repasse ("Recursos de partido político", em 73 % das candidaturas de SP); `DS_FONTE_RECEITA` diz de que caixa o dinheiro saiu, e é ela que define o **dinheiro público**, o número de capa da página. Havia um filtro chamado "Fonte do dinheiro" rodando sobre a coluna de origem: escolher "Fundo Especial" devolvia 16 candidaturas no país inteiro, enquanto a mesma tela dizia que 91 % do pago era dinheiro público. O filtro saiu em 17/09, e a ficha mostra as duas colunas lado a lado, cada uma com o nome que o TSE usa.

**Limiar de sinal se calibra contra o dado, não contra a teoria.** Três limiares mudaram depois da primeira rodada nacional, e o histórico está nos comentários de `pipeline/alarmes/fornecedor.py`. Antes de criar ou mexer em sinal, rode e leia o que ele devolve: um sinal que aponta o ordinário não é sinal.

## Como está por dentro

| Onde | O que vive lá |
|---|---|
| `pipeline/` | Python, só biblioteca padrão. `baixar` pega os zips do TSE, `carregar` lê e normaliza ou falha alto, `agregar` soma por candidato e monta a visão nacional, `enriquecer` consulta o cadastro de CNPJ na Receita com cache, `alarmes/` tem um arquivo por família de sinal, `ident` dá endereço público a cada fornecedor, `escrever` gera os JSON, `validar` confere o que vai ao ar, `rodar` orquestra |
| `site/index.html` | A tela inteira, um arquivo. **Sem CDN, sem biblioteca, sem fonte externa** |
| `site/dados/` | Gerado, fora do git. É o retrato local para desenvolver. Dentro dele: `uf/`, `cand/` (uma ficha por candidatura), `forn/` (as fichas de fornecedor, em blocos), `panorama.json`, `indice.json`, `alarmes.json`, `fornecedores.json`, `cota.json`, `meta.json` |
| `dados/` | Tabelas mantidas à mão: tetos legais da Portaria TSE 449/2026 e o mapa de CNAE por tipo de despesa |
| `tests/` | `unittest`, contra uma fatia real de Roraima congelada em `tests/fixtures/` |
| `ferramentas/` | `inspecionar` descreve o layout dos zips, `investigar` responde pergunta de modelagem contra o dado real |
| `.github/workflows/` | `diario` roda duas vezes por dia e publica; `spike` diagnostica o acesso ao TSE; `inspecionar` e `investigar` rodam à mão |

O estado entre rodadas (cache da Receita, fornecedores já vistos, o total de ontem) vive na branch `dados`, não em `main`.

## Regras de trabalho

- **O validador é a porta.** `python -m pipeline.validar site/dados` roda antes de publicar, e a rodada falha se ele apontar qualquer coisa. Melhor o site de ontem no ar do que número errado.
- **Teste antes de mexer em número.** `python -m unittest discover -s tests`. A fixture é dado real, então um teste que quebra costuma ser um fato sobre o TSE, não um bug seu.
- **Mudou a forma da linha do ranking?** Mude `validar.py` junto, e o front. A linha da UF tem 16 campos e a do Brasil tem 17.
- **Layout do TSE muda sem aviso.** `carregar.py` falha alto listando as colunas que sumiram. Quando isso acontecer, rode `python -m ferramentas.inspecionar` no Actions antes de adivinhar.
- **Não commite `site/dados/`.** É gerado.
- **A ficha de fornecedor mora em blocos, e o endereço dela não é o documento.** São 419.531 fornecedores no país, 92 % deles com um único lançamento: um arquivo para cada derrubaria a publicação do Pages. Eles vão em blocos de cerca de 120 fichas, e o front acha o bloco refazendo a conta de `ident.bloco` em JavaScript. **Se mexer numa das duas contas, mexa na outra**, e confira com 200 identificadores reais.
- **Ficha de pessoa física tem piso, e ele é calibrado contra o dado** `[decidido, Guilherme 17/09/2026]`. Empresa sempre tem ficha, porque CNPJ é público por natureza. Pessoa física só a partir de **R$ 10 mil** recebidos na eleição inteira (`PISO_FICHA_PF`, em `escrever.py`): em Roraima isso deixa 455 de 9.082 (5 %) e ainda cobre 37,5 % de tudo que foi pago a pessoa física. Quem fica de fora continua nas listas, com o documento mascarado, e **não ganha link**: nome apontando para página que não existe é pior que nome sem link.
- **`CONTAS_SAL` é a chave que protege o CPF.** O identificador de pessoa física é um HMAC com essa chave, que vem do ambiente e nunca do repositório. No GitHub Actions ela é um secret; sem ela, `ident.py` usa um sal declarado no código e o identificador vira reversível por força bruta. **Rodada de produção sem `CONTAS_SAL` não deve publicar ficha de pessoa física.**

## O estado da publicacao, em 18/09/2026

**A rodada diaria esta no ar de novo** (`gh workflow list --all` mostra `active`) e o
painel nacional foi publicado em 18/09 com o codigo novo. O secret `CONTAS_SAL` existe
no repositorio desde 18/09.

Ela passou a madrugada desabilitada a mao, por um motivo que vale guardar: a branch
`dados` ja havia sido recriada no formato novo, sem CPF em texto puro, e uma rodada com
o codigo antigo leria aquele arquivo como documento cru, regravaria os CPF e dispararia
"fornecedor novo" para centenas de milhares de pessoas. **A ordem que desfaz isso e
sempre a mesma:** `git push` do `main` com o codigo novo, e so entao
`gh workflow enable diario.yml`.

**A ordem padrao do ranking e a receita declarada** `[decidido, Guilherme 18/09/2026]`,
e nao o gasto contratado. Ela troca quem ocupa a primeira linha da tela que abre: no
pais, Lula (o maior gasto contratado) sai e Flavio Bolsonaro (a maior receita) entra, e
17 das 60 primeiras linhas trocam. Num repositorio cuja primeira regra e neutralidade,
isso e escolha declarada do dono, e nao efeito colateral de uma decisao de desenho.

## Para rodar

```bash
python -m unittest discover -s tests
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita \
    --site site/dados --estado /tmp/estado
python -m pipeline.validar site/dados
cd site && python -m http.server 8777     # e abrir http://localhost:8777/
```

O que a rodada da fixture não exercita: o tamanho nacional. No país são 419.531 fichas de fornecedor, cerca de 100 MB crus e 24 MB comprimidos, em uns 4.096 arquivos.

Para publicar com dado nacional: `gh workflow run diario.yml`. Com `sem_receita=true` a rodada leva dois minutos e usa o cache de CNPJ já coletado; sem a opção, ela gasta 80 minutos consultando a Receita e só então publica.

## Fonte

TSE, dados abertos, conjunto **Prestação de Contas Eleitorais 2026** (sistema Conta+JE, área ASEPA) e **Consulta de Candidaturas 2026**. Limites de gastos da Portaria TSE nº 449, de 20 de julho de 2026. Cadastro de CNPJ pelos espelhos públicos dos dados abertos da Receita Federal.
