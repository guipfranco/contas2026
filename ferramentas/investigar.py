#!/usr/bin/env python3
"""Responde as perguntas de modelagem que decidem o pipeline, contra o dado real.

A maior delas: um candidato aparece com mais de uma prestacao de contas
(`Parcial`, `Relatorio Financeiro`), cada uma com seu SQ_PRESTADOR_CONTAS.
Somar tudo pode contar a mesma despesa duas vezes. Este script mede se conta.

Tambem extrai uma fatia pequena e real para `tests/fixtures/`, que e o que
permite desenvolver na maquina local: de la o CDN do TSE responde 403 a todo
cliente automatico, so o runner do GitHub passa.

Uso (no runner):
    python -m ferramentas.investigar --uf AC --fixture RR
"""
import argparse
import collections
import csv
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.baixar import baixar_fontes  # noqa: E402

csv.field_size_limit(10 * 1024 * 1024)


def linhas(z, membro):
    """Itera dicts do CSV, tolerando BOM, NUL e latin-1."""
    with io.TextIOWrapper(z.open(membro), encoding='latin-1', newline='') as f:
        leitor = csv.reader((l.replace('\0', '') for l in f), delimiter=';')
        cab = [c.lstrip('﻿').strip('"').strip() for c in next(leitor)]
        for linha in leitor:
            if len(linha) == len(cab):
                yield dict(zip(cab, linha))


def cent(s):
    s = (s or '').strip().replace('.', '').replace(',', '.')
    if not s or s in ('#NULO#', '-1'):
        return 0
    try:
        return int(round(float(s) * 100))
    except ValueError:
        return 0


def titulo(t):
    print('\n' + '=' * 72)
    print(t)
    print('=' * 72)


def secao(t):
    print(f'\n-- {t}')


def conta(it, n=25):
    c = collections.Counter(it)
    for v, q in c.most_common(n):
        print(f'      {q:>9,}  {v!r}')
    if len(c) > n:
        print(f'      ... e mais {len(c) - n} valores distintos')
    return c


def a_estrutura(z, nome):
    titulo(f'A. estrutura de {nome}')
    grupos = collections.defaultdict(list)
    for i in z.infolist():
        base = i.filename.rsplit('.', 1)[0]
        pref = base.rsplit('_', 1)[0] if '_' in base else base
        suf = base.rsplit('_', 1)[1] if '_' in base else ''
        grupos[pref].append((suf, i.file_size))
    for pref, itens in sorted(grupos.items()):
        sufs = sorted(s for s, _ in itens)
        total = sum(t for _, t in itens)
        print(f'   {pref}: {len(itens)} arquivos, {total / 1e6:.0f} MB')
        print(f'      sufixos: {" ".join(sufs)}')
    return grupos


def b_dupla_contagem(z, uf):
    """A pergunta que decide tudo: somar todas as linhas conta duas vezes?"""
    titulo(f'B. dupla contagem em {uf} (despesas contratadas)')
    membro = f'despesas_contratadas_candidatos_2026_{uf}.csv'
    por_cand_prest = collections.defaultdict(set)
    tp_por_prest = {}
    dt_por_prest = {}
    sq_desp = collections.Counter()
    # assinatura economica de uma despesa, para achar repeticao com id diferente
    assinatura = collections.defaultdict(list)
    total_linhas = 0
    total_valor = 0
    for r in linhas(z, membro):
        total_linhas += 1
        v = cent(r['VR_DESPESA_CONTRATADA'])
        total_valor += v
        sqc, sqp = r['SQ_CANDIDATO'], r['SQ_PRESTADOR_CONTAS']
        por_cand_prest[sqc].add(sqp)
        tp_por_prest[sqp] = r['TP_PRESTACAO_CONTAS']
        dt_por_prest[sqp] = r['DT_PRESTACAO_CONTAS']
        sq_desp[r['SQ_DESPESA']] += 1
        chave = (sqc, r['NR_CPF_CNPJ_FORNECEDOR'], r['DT_DESPESA'], v,
                 r.get('NR_DOCUMENTO', ''))
        assinatura[chave].append((sqp, r['SQ_DESPESA']))

    print(f'   {total_linhas:,} linhas, R$ {total_valor / 100:,.2f} somando tudo')
    print(f'   {len(por_cand_prest):,} candidatos, {len(tp_por_prest):,} prestacoes, '
          f'{len(sq_desp):,} SQ_DESPESA distintos')

    secao('SQ_DESPESA se repete?')
    rep = [k for k, v in sq_desp.items() if v > 1]
    print(f'      {len(rep)} SQ_DESPESA aparecem mais de uma vez')

    secao('tipos de prestacao')
    conta(tp_por_prest.values())

    secao('candidatos por numero de prestacoes')
    conta(len(v) for v in por_cand_prest.values())

    multi = {k: v for k, v in por_cand_prest.items() if len(v) > 1}
    print(f'      {len(multi)} candidatos com mais de uma prestacao')

    secao('a mesma despesa aparece em duas prestacoes do mesmo candidato?')
    colisoes = {k: v for k, v in assinatura.items()
                if len({p for p, _ in v}) > 1}
    print(f'      {len(colisoes)} assinaturas (candidato, fornecedor, data, valor, doc) '
          f'em mais de uma prestacao')
    valor_duplicado = sum(k[3] * (len({p for p, _ in v}) - 1) for k, v in colisoes.items())
    print(f'      valor que seria contado a mais: R$ {valor_duplicado / 100:,.2f} '
          f'({valor_duplicado / max(total_valor, 1) * 100:.1f} % do total)')
    for k, v in list(colisoes.items())[:5]:
        print(f'      . cand={k[0]} forn={k[1]} data={k[2]} valor={k[3] / 100:.2f} '
              f'doc={k[4]!r} -> {[(p, tp_por_prest[p], dt_por_prest[p]) for p, _ in v]}')

    secao('por candidato com multiplas prestacoes: total por prestacao')
    for sqc in list(multi)[:5]:
        porp = collections.Counter()
        valp = collections.Counter()
        for r in linhas(z, membro):
            if r['SQ_CANDIDATO'] == sqc:
                porp[r['SQ_PRESTADOR_CONTAS']] += 1
                valp[r['SQ_PRESTADOR_CONTAS']] += cent(r['VR_DESPESA_CONTRATADA'])
        print(f'      candidato {sqc}:')
        for sqp in porp:
            print(f'         {sqp} {tp_por_prest[sqp]:<22} {dt_por_prest[sqp]} '
                  f'{porp[sqp]:>5} linhas  R$ {valp[sqp] / 100:>14,.2f}')
        break_ = True
    return {'linhas': total_linhas, 'valor': total_valor,
            'colisoes': len(colisoes), 'valor_duplicado': valor_duplicado}


def c_pagas(z, uf):
    titulo(f'C. despesas pagas em {uf}: como ligar ao candidato')
    membro = f'despesas_pagas_candidatos_2026_{uf}.csv'
    contr = f'despesas_contratadas_candidatos_2026_{uf}.csv'
    prest_para_cand = {}
    sqdesp_para_cand = {}
    for r in linhas(z, contr):
        prest_para_cand[r['SQ_PRESTADOR_CONTAS']] = r['SQ_CANDIDATO']
        sqdesp_para_cand[r['SQ_DESPESA']] = r['SQ_CANDIDATO']
    n = achou_prest = achou_desp = 0
    total = 0
    for r in linhas(z, membro):
        n += 1
        total += cent(r['VR_PAGTO_DESPESA'])
        if r['SQ_PRESTADOR_CONTAS'] in prest_para_cand:
            achou_prest += 1
        if r.get('SQ_DESPESA') in sqdesp_para_cand:
            achou_desp += 1
    print(f'   {n:,} pagamentos, R$ {total / 100:,.2f}')
    print(f'   por SQ_PRESTADOR_CONTAS: {achou_prest:,} ligam ({achou_prest / max(n, 1) * 100:.1f} %)')
    print(f'   por SQ_DESPESA:          {achou_desp:,} ligam ({achou_desp / max(n, 1) * 100:.1f} %)')


def d_vocabularios(z, membros):
    titulo('D. vocabularios (para os dicionarios do JSON)')
    campos = {
        'despesas_contratadas': ['DS_CARGO', 'DS_ORIGEM_DESPESA', 'DS_TIPO_FORNECEDOR',
                                 'DS_ESFERA_PART_FORNECEDOR', 'DS_TIPO_DOCUMENTO',
                                 'TP_PRESTACAO_CONTAS'],
        'receitas_candidatos_2026': ['DS_FONTE_RECEITA', 'DS_ORIGEM_RECEITA',
                                     'DS_NATUREZA_RECEITA', 'DS_ESPECIE_RECEITA',
                                     'DS_GENERO', 'DS_COR_RACA'],
        'despesas_pagas': ['DS_FONTE_DESPESA', 'DS_NATUREZA_DESPESA',
                           'DS_ESPECIE_RECURSO'],
    }
    saida = {}
    for membro in membros:
        chave = next((k for k in campos if membro.startswith(k)), None)
        if not chave:
            continue
        print(f'\n   ### {membro}')
        acs = {c: collections.Counter() for c in campos[chave]}
        vals = {c: collections.Counter() for c in campos[chave]}
        vcol = ('VR_DESPESA_CONTRATADA' if 'contratadas' in membro else
                'VR_PAGTO_DESPESA' if 'pagas' in membro else 'VR_RECEITA')
        for r in linhas(z, membro):
            v = cent(r.get(vcol, ''))
            for c in acs:
                if c in r:
                    acs[c][r[c]] += 1
                    vals[c][r[c]] += v
        for c, ac in acs.items():
            print(f'\n      {c}: {len(ac)} valores')
            for val, q in ac.most_common(30):
                print(f'         {q:>9,}  R$ {vals[c][val] / 100:>16,.2f}  {val!r}')
            saida[f'{membro}:{c}'] = [v for v, _ in ac.most_common()]
    return saida


def e_fornecedores(z, membro):
    titulo('E. fornecedores (quantos CNPJ o enriquecimento vai ter de cobrir)')
    por_doc = collections.defaultdict(lambda: [0, 0, set()])  # valor, linhas, candidatos
    tipos = collections.Counter()
    for r in linhas(z, membro):
        doc = (r['NR_CPF_CNPJ_FORNECEDOR'] or '').strip()
        v = cent(r['VR_DESPESA_CONTRATADA'])
        d = por_doc[doc]
        d[0] += v
        d[1] += 1
        d[2].add(r['SQ_CANDIDATO'])
        tipos[len(doc)] += 1
    pj = {k: v for k, v in por_doc.items() if len(k) == 14}
    pf = {k: v for k, v in por_doc.items() if len(k) == 11}
    print(f'   {len(por_doc):,} documentos distintos')
    print(f'   {len(pj):,} CNPJ (14 digitos), R$ {sum(v[0] for v in pj.values()) / 100:,.2f}')
    print(f'   {len(pf):,} CPF  (11 digitos), R$ {sum(v[0] for v in pf.values()) / 100:,.2f}')
    secao('tamanhos de documento encontrados')
    conta(tipos.elements(), 10)
    secao('quantos CNPJ cobrem 80 % do valor (a fila do enriquecimento)')
    ordenado = sorted(pj.items(), key=lambda kv: -kv[1][0])
    tot = sum(v[0] for v in pj.values())
    ac = 0
    for i, (k, v) in enumerate(ordenado, 1):
        ac += v[0]
        if ac >= 0.8 * tot:
            print(f'      {i:,} CNPJ ({i / max(len(pj), 1) * 100:.1f} % deles)')
            break
    secao('fornecedores em mais candidatos')
    for k, v in sorted(pj.items(), key=lambda kv: -len(kv[1][2]))[:10]:
        print(f'      {k}  {len(v[2]):>5} candidatos  R$ {v[0] / 100:>16,.2f}')
    return {'cnpj': len(pj), 'cpf': len(pf)}


def f_consulta_cand(z, uf):
    titulo(f'F. consulta_cand {uf}: o que da para juntar')
    membro = f'consulta_cand_2026_{uf}.csv'
    cab = None
    n = 0
    fed = collections.Counter()
    sit = collections.Counter()
    cargo = collections.Counter()
    for r in linhas(z, membro):
        if cab is None:
            cab = list(r)
            print(f'   {len(cab)} colunas:')
            for i in range(0, len(cab), 4):
                print('      ' + ' | '.join(cab[i:i + 4]))
        n += 1
        for c in ('NM_FEDERACAO', 'SG_FEDERACAO', 'DS_COMPOSICAO_FEDERACAO'):
            if c in r:
                fed[(c, r[c][:40])] += 1
        for c in ('DS_SITUACAO_CANDIDATURA', 'DS_DETALHE_SITUACAO_CAND'):
            if c in r:
                sit[(c, r[c])] += 1
        cargo[r.get('DS_CARGO', '')] += 1
    print(f'   {n:,} linhas')
    secao('cargos')
    conta(cargo.elements(), 15)
    secao('federacao')
    conta(fed.elements(), 12)
    secao('situacao')
    conta(sit.elements(), 12)


def g_doador_originario(z, uf):
    titulo(f'G. doador originario {uf}: quem esta atras do repasse')
    m_rec = f'receitas_candidatos_2026_{uf}.csv'
    m_ori = f'receitas_candidatos_doador_originario_2026_{uf}.csv'
    if m_ori not in z.namelist():
        print('   (nao existe para esta UF)')
        return
    receitas = {}
    for r in linhas(z, m_rec):
        receitas[r['SQ_RECEITA']] = (r['SQ_CANDIDATO'], cent(r['VR_RECEITA']),
                                     r['DS_ORIGEM_RECEITA'])
    n = liga = 0
    tp = collections.Counter()
    for r in linhas(z, m_ori):
        n += 1
        if r['SQ_RECEITA'] in receitas:
            liga += 1
        tp[r.get('TP_DOADOR_ORIGINARIO', '')] += 1
    print(f'   {n:,} linhas de doador originario, {liga:,} ligam por SQ_RECEITA '
          f'({liga / max(n, 1) * 100:.1f} %)')
    secao('tipo de doador originario')
    conta(tp.elements(), 10)


def h_fixture(z, uf, destino):
    """Grava uma fatia real e pequena, para teste local."""
    titulo(f'H. fixture de {uf} para tests/fixtures/')
    os.makedirs(destino, exist_ok=True)
    alvo = os.path.join(destino, 'candidatos.zip')
    membros = [m for m in z.namelist() if m.endswith(f'_{uf}.csv')]
    with zipfile.ZipFile(alvo, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for m in membros:
            dados = z.read(m)
            out.writestr(m, dados)
            print(f'   {m}: {len(dados) / 1e6:.2f} MB')
    print(f'   -> {alvo}: {os.path.getsize(alvo) / 1e6:.2f} MB')
    return alvo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uf', default='AC', help='UF para as medicoes detalhadas')
    p.add_argument('--fixture', default='RR', help='UF a congelar como fixture')
    p.add_argument('--destino', default=os.environ.get('RUNNER_TEMP', 'tmp') + '/tse')
    p.add_argument('--saida-fixture', default='fixture')
    p.add_argument('--fonte-local', default=None)
    a = p.parse_args(argv)

    fontes = baixar_fontes(a.destino, a.fonte_local,
                           quais=['candidatos', 'consulta_cand'])
    zc = zipfile.ZipFile(fontes['candidatos'][0])
    zk = zipfile.ZipFile(fontes['consulta_cand'][0])

    a_estrutura(zc, 'candidatos')
    a_estrutura(zk, 'consulta_cand')
    b_dupla_contagem(zc, a.uf)
    c_pagas(zc, a.uf)
    d_vocabularios(zc, [f'despesas_contratadas_candidatos_2026_{a.uf}.csv',
                        f'receitas_candidatos_2026_{a.uf}.csv',
                        f'despesas_pagas_candidatos_2026_{a.uf}.csv'])
    e_fornecedores(zc, 'despesas_contratadas_candidatos_2026_BRASIL.csv')
    f_consulta_cand(zk, a.uf)
    g_doador_originario(zc, a.uf)

    h_fixture(zc, a.fixture, a.saida_fixture)
    # o consulta_cand da mesma UF vai junto
    with zipfile.ZipFile(os.path.join(a.saida_fixture, 'consulta_cand.zip'), 'w',
                         zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        m = f'consulta_cand_2026_{a.fixture}.csv'
        out.writestr(m, zk.read(m))
    print(f'   consulta_cand.zip gravado')
    return 0


if __name__ == '__main__':
    sys.exit(main())
