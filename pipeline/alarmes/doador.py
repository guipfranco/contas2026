#!/usr/bin/env python3
"""Sinais sobre de onde veio o dinheiro.

**O B3 estava com a base de calculo invertida, e a pesquisa juridica de 17/09
corrigiu.** Autofinanciamento nao e 10 % do rendimento do candidato: e **10 %
do teto de gastos do cargo**, pela Lei 9.504/1997, art. 23, § 2º-A, incluido
pela Lei 13.878/2019 e regulamentado no art. 27, § 1º da Resolucao TSE
23.607/2019. Os 10 % do rendimento bruto do ano anterior existem, mas sao o
limite de DOACAO DE TERCEIRO (art. 23, § 1º), nao do proprio candidato. A
confusao vem do art. 23, § 1º-A da Lei 13.165/2015, que deixava o candidato
bancar ate 100 % do teto e foi revogado em 2017.

Consequencia pratica: o limite e **publico e calculavel**, entao o sinal
deixa de ser "a fatia parece alta" e passa a ser "passou do limite legal".
Para deputado federal em 2026 sao R$ 317.657,25 (10 % de R$ 3.176.572,53).

**O B4 e alarme de partido e so de partido.** A cota de genero esta no art. 17,
§ 8º da Constituicao (Emenda 117/2022): no minimo 30 % do FEFC e da parcela do
fundo partidario destinada a campanha vao para candidaturas femininas. A conta
e do partido, nunca de um candidato, e e aferida ao fim da campanha.
"""
import collections

from . import Alarme, moeda, pct

B1_MIN = 2000000         # R$ 20 mil, dos dois lados
B1_GRAVE = 5000000
B2_MIN_DOACOES = 10
B2_MIN_VALOR = 100000    # R$ 1 mil cada
B2_GRAVE = 25
B3_MIN = 3000000         # R$ 30 mil de recursos proprios
B3_FATIA_SEM_TETO = 50   # sem teto cadastrado, so a fatia da receita
FATIA_AUTOFINANCIAMENTO = 10   # % do teto do cargo, art. 23, § 2º-A
B4_MINIMO_LEGAL = 30     # % do fundo publico para candidaturas femininas
B4_MIN_TOTAL = 100000000


def _proprio(a):
    for origem, v in a.por_origem.items():
        if 'propri' in origem.lower() or 'própri' in origem.lower():
            return v
    return 0


def b1_doador_fornecedor(a, ctx):
    """Quem doou para a campanha e recebeu dela como fornecedor.

    So pessoa fisica. Doacao de CNPJ nao existe desde 2015: o que aparece como
    PJ aqui e repasse de partido ou de outra candidatura, e o partido tambem
    fornecer material conjunto e o normal, nao um sinal.
    """
    for doc, d in a.por_doador.items():
        if len(doc) != 11:
            continue
        f = a.por_forn.get(doc)
        if not f or d[0] < B1_MIN or f[0] < B1_MIN:
            continue
        nome = (d[2] or f[2] or 'A mesma pessoa')[:32]
        grave = d[0] >= B1_GRAVE and f[0] >= B1_GRAVE
        yield Alarme('B1', 2 if grave else 1, a.sq, doc, max(d[0], f[0]),
                     f'{nome} doou {moeda(d[0])} para a campanha e recebeu '
                     f'{moeda(f[0])} dela como fornecedor. Doar e prestar '
                     f'servico sao atos distintos, ambos permitidos.')


def b3_recursos_proprios(a, ctx):
    """Recursos proprios acima de 10 % do teto do cargo.

    Com o teto cadastrado o sinal e objetivo. Sem ele, cai para a leitura
    fraca (fatia da receita), que nao afirma nada sobre o limite.
    """
    proprio = _proprio(a)
    if proprio < B3_MIN:
        return
    teto = ctx.teto(a.uf, a.cargo)
    if teto:
        limite = teto * FATIA_AUTOFINANCIAMENTO // 100
        if proprio <= limite:
            return
        fatia = pct(proprio, teto)
        yield Alarme('B3', 3, a.sq, '', proprio,
                     f'Recursos próprios somam {moeda(proprio)}, {fatia} % do '
                     f'teto de gastos do cargo. A lei permite até 10 %, ou '
                     f'{moeda(limite)}. A conta só fecha na prestação final.')
        return
    total = a.receita + a.estimavel
    fatia = pct(proprio, total)
    if fatia < B3_FATIA_SEM_TETO:
        return
    yield Alarme('B3', 1, a.sq, '', proprio,
                 f'{fatia} % da receita ({moeda(proprio)}) veio do próprio '
                 f'candidato. O limite legal é 10 % do teto de gastos do cargo, '
                 f'que não está cadastrado aqui para este cargo.')


def b2_pulverizacao(a, ctx):
    """Muitas doacoes de valor identico no mesmo dia.

    Atipico, nunca irregular: arrecadacao com valor sugerido produz o mesmo
    padrao, e o texto diz isso.
    """
    idx = getattr(ctx, 'doacoes_por_dia', None)
    if not idx:
        return
    for (dia, valor), pessoas in idx.get(a.sq, {}).items():
        if len(pessoas) < B2_MIN_DOACOES or valor < B2_MIN_VALOR:
            continue
        yield Alarme('B2', 2 if len(pessoas) >= B2_GRAVE else 1, a.sq, '',
                     valor * len(pessoas),
                     f'{len(pessoas)} pessoas diferentes doaram exatamente '
                     f'{moeda(valor)} no mesmo dia ({dia[8:]}/{dia[5:7]}), '
                     f'somando {moeda(valor * len(pessoas))}. Arrecadacao com '
                     f'valor sugerido gera esse padrao.')


def indexar_doacoes(linhas):
    """(sq, dia, valor, doc) -> {sq: {(dia, valor): conjunto de doadores}}."""
    idx = collections.defaultdict(lambda: collections.defaultdict(set))
    for sq, dia, valor, doc in linhas:
        if dia and valor:
            idx[sq][(dia, valor)].add(doc)
    return idx


def b4_cota(nac):
    """Cota de genero e de raca no dinheiro publico, por partido e UF.

    Alarme de partido, nunca de candidato: a regra constitucional e sobre o
    montante que o partido destina, e e aferida ao fim da campanha.
    """
    saida = []
    for (partido, uf), (total, mulheres, negros) in nac.fundo_partido.items():
        if total < B4_MIN_TOTAL or not partido:
            continue
        fatia = pct(mulheres, total)
        fatia_negros = pct(negros, total)
        if fatia >= B4_MINIMO_LEGAL:
            continue
        saida.append({
            'partido': partido, 'uf': uf, 'total': total,
            'fatia_mulheres': fatia, 'fatia_negros': fatia_negros,
            'grav': 2 if fatia < 20 else 1,
            'texto': f'Candidatas do {partido} em {uf} receberam {fatia} % do '
                     f'dinheiro público declarado até agora ({moeda(mulheres)} '
                     f'de {moeda(total)}). A Constituição, no artigo 17, '
                     f'parágrafo 8, garante no mínimo 30 %, e a conta e '
                     f'fechada ao fim da campanha.',
        })
    saida.sort(key=lambda x: (x['fatia_mulheres'], -x['total']))
    return saida


def avaliar(a, ctx):
    saida = []
    saida.extend(b1_doador_fornecedor(a, ctx))
    saida.extend(b3_recursos_proprios(a, ctx))
    saida.extend(b2_pulverizacao(a, ctx))
    return saida
