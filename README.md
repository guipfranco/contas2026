# contas2026

Painel dos gastos de campanha da eleição brasileira de 2026, a partir da prestação de contas que o TSE publica em dados abertos. Feito para abrir no celular.

**O que ele faz que o DivulgaCandContas não faz:** ranking comparável entre candidaturas, corte por tipo de gasto, quanto de cada campanha saiu de dinheiro público, quem são os grandes fornecedores da eleição inteira, e sinais automáticos que apontam números fora do comum.

**O que ele não faz:** acusar ninguém. Um sinal aqui é um número que chamou atenção, com o motivo escrito ao lado e a explicação inocente na mesma linha. Quem conclui é gente, depois de conferir.

## Como está por dentro

```
pipeline/     Python 3.12, só biblioteca padrão. Nenhuma dependência.
  baixar.py       pega os zips do TSE (e diagnostica quando o CDN barra)
  carregar.py     lê os CSV e normaliza, ou falha alto se o layout mudar
  agregar.py      soma por candidato e monta a visão nacional
  enriquecer.py   pergunta o cadastro de cada CNPJ à Receita, com cache
  alarmes/        um arquivo por família de sinal
  escrever.py     gera os JSON que o site lê
  validar.py      confere o que vai ao ar; aponta, nunca conserta
  rodar.py        a rodada inteira
site/index.html   um arquivo, sem CDN e sem biblioteca
dados/            tabelas mantidas à mão (tetos legais, mapa CNAE)
tests/            unittest, contra uma fatia real de Roraima
ferramentas/      inspeção e investigação do dado bruto
```

Duas vezes por dia o GitHub Actions baixa, recalcula e republica no Pages. O estado entre rodadas (cache da Receita, fornecedores já vistos, o total de ontem) vive na branch `dados`.

## O que o dado ensinou, e que não estava no manual

**Somar todas as linhas é o certo, e isso não era óbvio.** `SQ_DESPESA` não identifica uma linha: identifica um grupo, uma nota com vários itens. Em Roraima, 14.292 linhas têm só 12.064 `SQ_DESPESA` distintos, e as repetidas trazem descrição e valor diferentes. Os dois caminhos foram medidos: somando tudo, nenhum candidato aparece com pagamento maior que a despesa contratada; deduplicando por `SQ_DESPESA`, 72 candidatos ficam impossíveis, com R$ 2,6 milhões de excesso. O teste `test_somar_tudo_nunca_deixa_pago_maior_que_contratado` guarda essa decisão.

**Só o arquivo BRASIL é lido.** São 26 arquivos por UF mais o BRASIL, e o Distrito Federal não está entre eles. Ler por UF perderia o DF inteiro e os cargos nacionais. Quem agrupa por UF é o pipeline, pela coluna `SG_UF`.

**O marcador de vazio tem quatro formas.** `#NULO`, `#NULO#`, `-1` e `#NE` convivem no mesmo arquivo, em colunas diferentes. Tratar só uma delas faz a string `#NULO` virar nome de fornecedor no painel.

**As despesas pagas não trazem o candidato.** Ligam pelo `SQ_PRESTADOR_CONTAS`, e 100% delas acham dono. É por aí que se sabe qual fundo pagou cada despesa.

**O CDN do TSE barra cliente automático, mas não o runner do GitHub.** Da máquina local, toda requisição leva 403, com qualquer user-agent, em curl, urllib e PowerShell. No runner do Actions, um user-agent de Chrome com os cabeçalhos de navegação passa. `python -m pipeline.baixar --spike` refaz esse diagnóstico quando algo parar de funcionar.

**A fila de enriquecimento é curta.** São 45.348 CNPJ fornecedores no país, mas 4.817 concentram 80% do valor. Meia hora de consulta resolve o topo, e não precisa do dump de 5 GB da Receita.

## Os sinais

Gravidade é ordem de fila para quem vai conferir, nunca medida de ilegalidade.

| Família | Códigos |
|---|---|
| Fornecedor | CNPJ recém-aberto, CNPJ fora de atividade, fornecedor é candidato, atividade destoa do gasto, gasto concentrado, pessoa física recebeu muito, documento não confere |
| Doador | doador também é fornecedor, doações iguais no mesmo dia, recursos próprios acima do limite, fundo para candidatas abaixo de 30% |
| Candidato | perto do limite de gastos, nada declarado |
| Ritmo | fornecedor novo hoje, salto no gasto declarado, mesma nota em duas contas |

Cada código carrega, no `meta.json`, o que significa **e o que não significa**. A ressalva é parte do produto.

Quatro travas de redação, verificadas por teste a cada rodada: número antes de adjetivo; nenhuma palavra que impute conduta; a explicação inocente junto quando existe uma comum; CPF sempre mascarado. Se um texto violar qualquer uma, a rodada falha e o site de ontem continua no ar.

Os limiares foram calibrados contra a rodada nacional de 17/09/2026, com 721.818 despesas, e três deles mudaram por causa do que o painel devolveu. O histórico está nos comentários de `pipeline/alarmes/fornecedor.py`.

## Rodar na sua máquina

```bash
python -m unittest discover -s tests
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR \
    --sem-receita --site /tmp/site --estado /tmp/estado
python -m pipeline.validar /tmp/site
```

O download direto do TSE não funciona fora do runner do GitHub. Para rodar com dado nacional na máquina, baixe os zips pelo Chrome e aponte `--fonte-local` para a pasta.

## Fonte

TSE, dados abertos, conjunto **Prestação de Contas Eleitorais 2026** (Sistema Conta+JE, área ASEPA), e **Consulta de Candidaturas 2026**. Limites de gastos da Portaria TSE nº 449, de 20 de julho de 2026. Cadastro de CNPJ pelos espelhos públicos dos dados abertos da Receita Federal.

Os dados são republicados sob a mesma licença Creative Commons Atribuição do TSE. Os sinais e a leitura são deste projeto, não do TSE.
