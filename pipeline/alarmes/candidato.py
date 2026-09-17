#!/usr/bin/env python3
"""Sinais sobre a candidatura inteira, nao sobre um fornecedor."""
from . import Alarme, moeda, pct

C1_AVISO = 90        # % do teto a partir do qual vale avisar
C2_DEPOIS_DE = '2026-09-15'


def c1_teto(a, ctx):
    teto = ctx.teto(a.uf, a.cargo)
    if not teto or not a.contratado:
        return
    fatia = pct(a.contratado, teto)
    if fatia < C1_AVISO:
        return
    if fatia > 100:
        yield Alarme('C1', 3, a.sq, '', a.contratado,
                     f'O gasto contratado esta em {fatia} % do limite do cargo '
                     f'({moeda(a.contratado)} de {moeda(teto)}). A conta so '
                     f'fecha na prestacao final.')
    else:
        yield Alarme('C1', 2, a.sq, '', a.contratado,
                     f'O gasto contratado esta em {fatia} % do limite do cargo '
                     f'({moeda(a.contratado)} de {moeda(teto)}).')


def c2_nada_declarado(a, ctx):
    if a.movimento or not ctx.hoje or ctx.hoje < C2_DEPOIS_DE:
        return
    d = ctx.hoje
    yield Alarme('C2', 1, a.sq, '', 0,
                 f'Nenhuma receita e nenhuma despesa declaradas ate '
                 f'{d[8:]}/{d[5:7]}. Quem nao movimenta dinheiro presta contas '
                 f'ao final sem nada a declarar.')


def avaliar(a, ctx):
    saida = []
    saida.extend(c1_teto(a, ctx))
    saida.extend(c2_nada_declarado(a, ctx))
    return saida
