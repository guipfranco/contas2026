#!/usr/bin/env python3
"""Sinais sobre de onde veio o dinheiro."""
import collections

from . import Alarme, moeda, pct

B1_MIN = 500000          # R$ 5 mil, dos dois lados
B1_GRAVE = 1000000
B2_MIN_DOACOES = 10
B2_MIN_VALOR = 50000     # R$ 500 cada
B2_GRAVE = 20
B3_FATIA = 50            # % da receita vinda do proprio bolso
B3_MIN = 5000000
B4_MINIMO_LEGAL = 30     # % do fundo publico para candidaturas femininas
B4_MIN_TOTAL = 100000000

ORIGEM_PROPRIA = 'Recursos proprios'


def b1_doador_fornecedor(a, ctx):
    for doc, d in a.por_doador.items():
        # So pessoa fisica. Doacao de CNPJ nao existe desde 2015: o que aparece
        # como PJ aqui e repasse de partido ou de outra candidatura, e o
        # partido ser tambem fornecedor (material conjunto) e o normal.
        if len(doc) != 11:
            continue
        f = a.por_forn.get(doc)
        if not f or d[0] < B1_MIN or f[0] < B1_MIN:
            continue
        nome = (d[2] or f[2] or 'A mesma pessoa')[:32]
        grave = d[0] >= B1_GRAVE and f[0] >= B1_GRAVE
        yield Alarme('B1', 3 if grave else 2, a.sq, doc, max(d[0], f[0]),
                     f'{nome} doou {moeda(d[0])} para a campanha e recebeu '
                     f'{moeda(f[0])} dela como fornecedor. Doar e prestar '
                     f'servico sao atos distintos, ambos permitidos.')


def b3_recursos_proprios(a, ctx):
    proprio = 0
    for origem, v in a.por_origem.items():
        if 'proprio' in origem.lower() or 'próprio' in origem.lower():
            proprio += v
    if proprio < B3_MIN:
        return
    total = a.receita + a.estimavel
    fatia = pct(proprio, total)
    if fatia < B3_FATIA:
        return
    yield Alarme('B3', 2, a.sq, '', proprio,
                 f'{fatia} % da receita ({moeda(proprio)}) veio do proprio '
                 f'candidato. O limite legal e sobre o rendimento dele, que '
                 f'nao e publico.')


def b2_pulverizacao(a, ctx):
    idx = getattr(ctx, 'doacoes_por_dia', None)
    if not idx:
        return
    for (dia, valor), pessoas in idx.get(a.sq, {}).items():
        if len(pessoas) < B2_MIN_DOACOES or valor < B2_MIN_VALOR:
            continue
        yield Alarme('B2', 2 if len(pessoas) >= B2_GRAVE else 1, a.sq, '',
                     valor * len(pessoas),
                     f'{len(pessoas)} pessoas diferentes doaram exatamente '
                     f'{moeda(valor)} no mesmo dia ({dia[8:]}/{dia[5:7]}). '
                     f'Arrecadacao com valor sugerido gera esse padrao.')


def indexar_doacoes(linhas):
    """(sq, dia, valor, doc) -> {sq: {(dia, valor): conjunto de doadores}}."""
    idx = collections.defaultdict(lambda: collections.defaultdict(set))
    for sq, dia, valor, doc in linhas:
        idx[sq][(dia, valor)].add(doc)
    return idx


def b4_cota(nac):
    """Alarme de partido, nao de candidato. Sai em lista propria."""
    saida = []
    for (partido, uf), (total, mulheres, negros) in nac.fundo_partido.items():
        if total < B4_MIN_TOTAL or not partido:
            continue
        fatia = pct(mulheres, total)
        if fatia >= B4_MINIMO_LEGAL:
            continue
        saida.append({
            'partido': partido, 'uf': uf, 'total': total,
            'fatia_mulheres': fatia, 'fatia_negros': pct(negros, total),
            'grav': 1,
            'texto': f'Candidatas do {partido} em {uf} receberam {fatia} % do '
                     f'dinheiro publico declarado ate agora ({moeda(mulheres)} '
                     f'de {moeda(total)}). O minimo de 30 % e aferido ao fim '
                     f'da campanha.',
        })
    saida.sort(key=lambda x: x['fatia_mulheres'])
    return saida


def avaliar(a, ctx):
    saida = []
    saida.extend(b1_doador_fornecedor(a, ctx))
    saida.extend(b3_recursos_proprios(a, ctx))
    saida.extend(b2_pulverizacao(a, ctx))
    return saida
