#!/usr/bin/env python3
"""Sinais que so existem porque o painel olha o mesmo dado todo dia.

Sem ontem nao ha "novo". Na primeira rodada estes sinais ficam mudos de
proposito: marcar tudo como novo no primeiro dia seria ruido pelo desenho.
"""
from . import Alarme, moeda

D1_MIN = 2000000        # R$ 20 mil
D2_MIN = 10000000       # R$ 100 mil de diferenca
D2_FATIA = 50           # e pelo menos metade do que ja havia
D2_DO_ZERO = 20000000
D3_MIN = 100000


def d1_fornecedor_novo(a, ctx):
    if not ctx.primeira_vez:
        return
    for doc, e in a.por_forn.items():
        if e[0] < D1_MIN or doc in ctx.primeira_vez:
            continue
        yield Alarme('D1', 1, a.sq, doc, e[0],
                     f'{(e[2] or "Um fornecedor")[:32]} aparece pela primeira '
                     f'vez na base hoje, com {moeda(e[0])} declarados.')


def d2_salto(a, ctx):
    if not ctx.ontem:
        return
    antes = ctx.ontem.get(a.sq)
    if antes is None:
        return
    delta = a.contratado - antes
    if delta < D2_MIN:
        return
    if antes == 0:
        if delta < D2_DO_ZERO:
            return
        yield Alarme('D2', 2, a.sq, '', delta,
                     f'A primeira declaracao de gasto do candidato entrou hoje, '
                     f'com {moeda(delta)} de uma vez.')
        return
    if delta * 100 < antes * D2_FATIA:
        return
    yield Alarme('D2', 2, a.sq, '', delta,
                 f'O gasto declarado subiu {moeda(delta)} desde ontem, de '
                 f'{moeda(antes)} para {moeda(a.contratado)}. Entrega de lote '
                 f'de notas costuma produzir esse salto.')


def d3_nota_repetida(a, ctx):
    """A mesma nota do mesmo fornecedor na conta de dois candidatos.

    Rateio de material conjunto e legal e produz exatamente este padrao, e o
    texto diz isso. O sinal serve para quem quiser conferir se o rateio bate.
    """
    por_cand = getattr(ctx, 'colisao_por_cand', None)
    if not por_cand:
        return
    for doc, (num, outros, valor) in por_cand.get(a.sq, {}).items():
        if valor < D3_MIN:
            continue
        e = a.por_forn.get(doc)
        nome = (e[2] if e else '') or 'um fornecedor'
        n = len(outros)
        plural = 's' if n > 1 else ''
        yield Alarme('D3', 2 if n >= 3 else 1, a.sq, doc, valor,
                     f'O documento {num} de {nome[:28]} aparece tambem na conta '
                     f'de {n} outro{plural} candidato{plural}. Rateio de '
                     f'material conjunto e legal e gera esse padrao.')


def indexar_colisoes(nac, aggs):
    """Prepara o D3: de "nota vista em N candidatos" para "por candidato"."""
    por_cand = {}
    for chave, sqs in nac.docs_colisao.items():
        doc, num = chave.split('|', 1)
        for sq in sqs:
            a = aggs.get(sq)
            if not a:
                continue
            e = a.por_forn.get(doc)
            por_cand.setdefault(sq, {})[doc] = (num, sqs - {sq}, e[0] if e else 0)
    return por_cand


def avaliar(a, ctx):
    saida = []
    saida.extend(d1_fornecedor_novo(a, ctx))
    saida.extend(d2_salto(a, ctx))
    saida.extend(d3_nota_repetida(a, ctx))
    return saida
