# contas2026, instruções do project

Painel público dos gastos de campanha da eleição de 2026, a partir da prestação de contas que o TSE publica em dados abertos. No ar em `https://guipfranco.github.io/contas2026/`, com a URL ainda não divulgada e `noindex` na página.

**Este repositório é neutro e não tem ligação com nenhuma campanha** `[decidido, Guilherme 17/09/2026]`. Nada de marca, de partido ou de candidato aqui dentro. O repositório é público; nunca entre com segredo, e-mail pessoal ou dado que não seja do TSE.

## A trava que vale mais que qualquer funcionalidade

**Um sinal não é uma acusação, e o índice de conferência também não é.** O painel aponta, pelo nome, fornecedores e candidatos reais. Uma pessoa apontada injustamente precisa poder olhar a tela e reconhecer que ela não a acusou de nada.

Quatro regras de redação, verificadas por teste a cada rodada:

1. **Número antes de adjetivo.** "Fornecedor aberto há 47 dias" é um fato. "Fornecedor de fachada" é uma afirmação sobre gente que este painel não sustenta.
2. **Nenhuma palavra que impute conduta.** A lista está em `PROIBIDAS`, em `pipeline/alarmes/__init__.py`, e o teste reprova a rodada inteira se uma delas aparecer. Fora da lista mas igualmente barrados na interface: "risco", "suspeição", "score de irregularidade".
3. **A explicação inocente vem junto**, quando existe uma comum. Rateio de material entre candidatos é legal e produz o mesmo padrão de nota repetida; quem lê precisa saber disso na mesma linha.
4. **CPF sempre mascarado.** O TSE publica o número inteiro; repetir isso num painel fácil de varrer é outra coisa.

**Português do Brasil com acentuação correta em todo texto de interface.** Há um teste que reprova f-string de mensagem sem acento. **Nunca use travessão.**

## O que o dado ensinou, e que não está no manual do TSE

**Somar todas as linhas de despesa é o certo.** `SQ_DESPESA` não identifica uma linha: identifica um grupo, uma nota com vários itens. Medido nos dois caminhos: somando tudo, nenhum candidato aparece com pagamento maior que a despesa contratada; deduplicando por `SQ_DESPESA`, 72 candidatos de Roraima ficam impossíveis, com R$ 2,6 milhões de excesso. O teste `test_somar_tudo_nunca_deixa_pago_maior_que_contratado` guarda a decisão. **Não tente deduplicar.**

**Só o arquivo BRASIL é lido.** São 26 arquivos por UF mais o BRASIL, e o Distrito Federal não está entre eles. Ler por UF perderia o DF inteiro e os cargos nacionais. Quem agrupa por UF é o pipeline, pela coluna `SG_UF`. A unidade eleitoral `BR` é a Presidência.

**O marcador de vazio tem quatro formas:** `#NULO`, `#NULO#`, `-1` e `#NE`, no mesmo arquivo, em colunas diferentes.

**As despesas pagas não trazem o candidato.** Ligam pelo `SQ_PRESTADOR_CONTAS`, e 100% delas acham dono.

**O CDN do TSE devolve 403 a qualquer cliente automático da máquina local**, com qualquer user-agent, em curl, urllib e PowerShell. Só o Chrome passa. No runner do GitHub Actions, um user-agent de Chrome com os cabeçalhos de navegação passa. Por isso o pipeline roda lá e não aqui. `python -m pipeline.baixar --spike` refaz o diagnóstico. Para trabalhar com dado nacional na máquina, baixe os zips pelo Chrome e use `--fonte-local`.

**Limiar de sinal se calibra contra o dado, não contra a teoria.** Três limiares mudaram depois da primeira rodada nacional, e o histórico está nos comentários de `pipeline/alarmes/fornecedor.py`. Antes de criar ou mexer em sinal, rode e leia o que ele devolve: um sinal que aponta o ordinário não é sinal.

## Como está por dentro

| Onde | O que vive lá |
|---|---|
| `pipeline/` | Python, só biblioteca padrão. `baixar` pega os zips do TSE, `carregar` lê e normaliza ou falha alto, `agregar` soma por candidato e monta a visão nacional, `enriquecer` consulta o cadastro de CNPJ na Receita com cache, `alarmes/` tem um arquivo por família de sinal, `escrever` gera os JSON, `validar` confere o que vai ao ar, `rodar` orquestra |
| `site/index.html` | A tela inteira, um arquivo. **Sem CDN, sem biblioteca, sem fonte externa** |
| `site/dados/` | Gerado, fora do git. É o retrato local para desenvolver |
| `dados/` | Tabelas mantidas à mão: tetos legais da Portaria TSE 449/2026 e o mapa de CNAE por tipo de despesa |
| `tests/` | `unittest`, contra uma fatia real de Roraima congelada em `tests/fixtures/` |
| `ferramentas/` | `inspecionar` descreve o layout dos zips, `investigar` responde pergunta de modelagem contra o dado real |
| `.github/workflows/` | `diario` roda duas vezes por dia e publica; `spike` diagnostica o acesso ao TSE; `inspecionar` e `investigar` rodam à mão |

O estado entre rodadas (cache da Receita, fornecedores já vistos, o total de ontem) vive na branch `dados`, não em `main`.

## Regras de trabalho

- **O validador é a porta.** `python -m pipeline.validar site/dados` roda antes de publicar, e a rodada falha se ele apontar qualquer coisa. Melhor o site de ontem no ar do que número errado.
- **Teste antes de mexer em número.** `python -m unittest discover -s tests`. A fixture é dado real, então um teste que quebra costuma ser um fato sobre o TSE, não um bug seu.
- **Mudou a forma da linha do ranking?** Mude `validar.py` junto, e o front. A linha da UF tem 15 campos e a do Brasil tem 16.
- **Layout do TSE muda sem aviso.** `carregar.py` falha alto listando as colunas que sumiram. Quando isso acontecer, rode `python -m ferramentas.inspecionar` no Actions antes de adivinhar.
- **Não commite `site/dados/`.** É gerado.

## Para rodar

```bash
python -m unittest discover -s tests
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita \
    --site site/dados --estado /tmp/estado
python -m pipeline.validar site/dados
cd site && python -m http.server 8777     # e abrir http://localhost:8777/
```

Para publicar com dado nacional: `gh workflow run diario.yml`. Com `sem_receita=true` a rodada leva dois minutos e usa o cache de CNPJ já coletado; sem a opção, ela gasta 80 minutos consultando a Receita e só então publica.

## Fonte

TSE, dados abertos, conjunto **Prestação de Contas Eleitorais 2026** (sistema Conta+JE, área ASEPA) e **Consulta de Candidaturas 2026**. Limites de gastos da Portaria TSE nº 449, de 20 de julho de 2026. Cadastro de CNPJ pelos espelhos públicos dos dados abertos da Receita Federal.
