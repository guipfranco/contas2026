#!/usr/bin/env python3
"""Sinais sobre quem recebeu o dinheiro da campanha."""
from . import Alarme, moeda, pct

MIN_A1 = 500000          # R$ 5 mil: abaixo disso, CNPJ novo nao diz nada
DIAS_A1 = 180
DIAS_A1_GRAVE = 60
MIN_A1_GRAVE = 2000000   # R$ 20 mil
MIN_A2 = 200000
MIN_A4 = 500000
MIN_A4_GRAVE = 5000000
A5_FATIA = 70
A5_MIN = 3000000         # R$ 30 mil
A5_MIN_FORN = 3
A6_UM = 5000000          # R$ 50 mil de um so candidato
A6_GRAVE = 15000000

SITUACAO_GRAVE = ('BAIXADA', 'INAPTA', 'NULA')


def _dias(d1, d2):
    """Dias entre duas datas ISO. None quando falta alguma."""
    if not d1 or not d2 or len(d1) != 10 or len(d2) != 10:
        return None
    from datetime import date
    try:
        a = date(int(d1[:4]), int(d1[5:7]), int(d1[8:]))
        b = date(int(d2[:4]), int(d2[5:7]), int(d2[8:]))
    except ValueError:
        return None
    return (b - a).days


def a1_a2_receita(a, ctx):
    """CNPJ recem-aberto e CNPJ fora de atividade. Dependem da Receita."""
    for doc, e in a.por_forn.items():
        if len(doc) != 14:
            continue
        dados = ctx.receita.get(doc)
        if not dados:
            continue
        valor, nome = e[0], (e[2] or 'o fornecedor')[:34]
        abertura = dados.get('data_inicio_atividade') or ''
        if valor >= MIN_A1 and abertura:
            dias = _dias(abertura, a.primeira or ctx.hoje)
            if dias is not None and 0 <= dias <= DIAS_A1:
                grave = dias <= DIAS_A1_GRAVE and valor >= MIN_A1_GRAVE
                yield Alarme('A1', 3 if grave else 2, a.sq, doc, valor,
                             f'{nome} recebeu {moeda(valor)}. O CNPJ foi aberto '
                             f'{dias} dias antes da primeira despesa '
                             f'({abertura[8:]}/{abertura[5:7]}/{abertura[:4]}).')
        sit = (dados.get('situacao_cadastral') or '').upper()
        if valor >= MIN_A2 and sit and not sit.startswith('ATIVA'):
            grave = any(s in sit for s in SITUACAO_GRAVE)
            quando = dados.get('data_situacao_cadastral') or ''
            desde = (f' desde {quando[8:]}/{quando[5:7]}/{quando[:4]}'
                     if len(quando) == 10 else '')
            yield Alarme('A2', 3 if grave else 2, a.sq, doc, valor,
                         f'{nome} recebeu {moeda(valor)}. A Receita registra a '
                         f'empresa como {sit.lower()}{desde}.')


def a3_fornecedor_candidato(a, ctx):
    """O TSE ja marca quando o fornecedor e candidato: a coluna vem preenchida."""
    for doc, e in a.por_forn.items():
        sq_forn = e[5]
        if not sq_forn:
            continue
        valor, nome = e[0], (e[2] or 'o fornecedor')[:34]
        if sq_forn == a.sq:
            yield Alarme('A3', 3, a.sq, doc, valor,
                         f'{moeda(valor)} foram pagos ao próprio candidato, '
                         f'registrado como fornecedor de si mesmo.')
        else:
            yield Alarme('A3', 2, a.sq, doc, valor,
                         f'{nome} recebeu {moeda(valor)} e também é candidato '
                         f'nesta eleição. Ceder bem ou serviço a outra '
                         f'candidatura é permitido e precisa ser declarado.')


def a4_cnae(a, ctx):
    """Atividade do fornecedor que destoa do tipo de gasto.

    So dispara quando ha mapa para aquele tipo. Na duvida, nao dispara: aqui
    um falso positivo aponta uma empresa real que nao fez nada de errado.
    """
    if not ctx.cnae_por_tipo:
        return
    curinga = ctx.cnae_por_tipo.get('__curinga__', set())
    for doc, e in a.por_forn.items():
        if len(doc) != 14 or e[0] < MIN_A4:
            continue
        tipo = e[6] if len(e) > 6 else ''
        plausiveis = ctx.cnae_por_tipo.get(tipo)
        if not plausiveis:
            continue
        cnae = (e[4] or '').zfill(7)
        div = cnae[:2]
        if not div or div == '00' or div in curinga or div in plausiveis:
            continue
        nome_cnae = ctx.cnae_nome.get(e[4]) or ctx.cnae_nome.get(cnae) or ''
        if not nome_cnae:
            continue
        yield Alarme('A4', 2 if e[0] >= MIN_A4_GRAVE else 1, a.sq, doc, e[0],
                     f'{(e[2] or "O fornecedor")[:30]} recebeu {moeda(e[0])} em '
                     f'"{tipo[:32]}". A atividade registrada da empresa e '
                     f'"{nome_cnae[:38]}".')


def a5_concentracao(a, ctx):
    if a.contratado < A5_MIN or len(a.por_forn) < A5_MIN_FORN:
        return
    doc, e = max(a.por_forn.items(), key=lambda kv: kv[1][0])
    fatia = pct(e[0], a.contratado)
    if fatia < A5_FATIA:
        return
    yield Alarme('A5', 2 if fatia >= 90 else 1, a.sq, doc, e[0],
                 f'{fatia} % do gasto declarado ({moeda(e[0])} de '
                 f'{moeda(a.contratado)}) foi para um só fornecedor, '
                 f'{(e[2] or "não informado")[:30]}.')


def a6_pessoa_fisica(a, ctx):
    for doc, e in a.por_forn.items():
        if len(doc) != 11 or e[0] < A6_UM:
            continue
        lanc = f'{e[1]} lancamento' + ('s' if e[1] > 1 else '')
        nac = ctx.nac.fornecedores.get(doc)
        alem = ''
        if nac and nac[5] > 1:
            alem = (f' A mesma pessoa aparece como fornecedora de '
                    f'{nac[5]} candidaturas, somando {moeda(nac[0])}.')
        yield Alarme('A6', 2 if e[0] >= A6_GRAVE else 1, a.sq, doc, e[0],
                     f'{(e[2] or "Uma pessoa fisica")[:32]} recebeu '
                     f'{moeda(e[0])} em {lanc}, como pessoa fisica.{alem}')


def avaliar(a, ctx):
    if not a.por_forn:
        return []
    saida = []
    saida.extend(a1_a2_receita(a, ctx))
    saida.extend(a3_fornecedor_candidato(a, ctx))
    saida.extend(a4_cnae(a, ctx))
    saida.extend(a5_concentracao(a, ctx))
    saida.extend(a6_pessoa_fisica(a, ctx))
    return saida
