#!/usr/bin/env python3
"""A rodada inteira: baixa, soma, enriquece, avalia, escreve, confere.

Uma passada por arquivo do TSE, tudo do BRASIL, agrupado por UF aqui dentro.
Le so a biblioteca padrao.

Uso:
    python -m pipeline.rodar --site site/dados --estado estado
    python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita
"""
import argparse
import csv
import json
import os
import sys
import time
import zipfile
from datetime import date, timedelta

from . import agregar as A
from . import carregar as C
from . import escrever as E
from . import historico as H
from .alarmes import (CATALOGO, GRAVIDADE, Contexto, avaliar,
                      confere_redacao)
from .alarmes import doador as al_doador
from .alarmes import ritmo as al_ritmo
from .baixar import baixar_fontes


def memoria():
    """MB de residente, quando o sistema souber dizer. Nunca quebra."""
    try:
        import resource
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return v / 1024 if sys.platform != 'darwin' else v / 1e6
    except Exception:  # noqa: BLE001
        return 0.0


def passo(t0, texto):
    print(f'   [{time.time() - t0:6.1f}s {memoria():6.0f} MB] {texto}', flush=True)


def le_csv(caminho, chaves=None):
    if not caminho or not os.path.exists(caminho):
        return []
    with open(caminho, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def carregar_tetos(caminho):
    """(uf, cargo) -> centavos. Tabela mantida a mao, com fonte e data."""
    tetos = {}
    for r in le_csv(caminho):
        try:
            tetos[(r['uf'].strip(), r['cargo'].strip())] = int(r['teto_centavos'])
        except (KeyError, ValueError):
            continue
    return tetos


def carregar_cnae(caminho):
    """tipo de despesa -> divisoes plausiveis. '__curinga__' vale para todos."""
    mapa = {}
    for r in le_csv(caminho):
        tipo = (r.get('tipo_despesa') or '').strip()
        divs = {d.strip().zfill(2) for d in (r.get('divisoes_cnae') or '').split()
                if d.strip()}
        if tipo and divs:
            mapa[tipo] = divs
    return mapa


def carregar_cnae_nome(caminho):
    nomes = {}
    for r in le_csv(caminho):
        cod = (r.get('codigo') or '').strip()
        nome = (r.get('nome') or '').strip()
        if cod and nome:
            nomes[cod] = nome
    return nomes


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--site', default='site/dados')
    p.add_argument('--estado', default='estado')
    p.add_argument('--tmp', default=os.environ.get('RUNNER_TEMP', 'tmp') + '/tse')
    p.add_argument('--dados', default='dados')
    p.add_argument('--fonte-local', default=None)
    p.add_argument('--ufs', default='', help='so estas UFs (teste)')
    p.add_argument('--sem-receita', action='store_true',
                   help='nao consulta a rede; o cache continua valendo')
    p.add_argument('--orcamento-receita', type=int, default=4800)
    p.add_argument('--hoje', default='', help='data da rodada (o padrao e o relogio)')
    p.add_argument('--sem-chave', action='store_true',
                   help='roda sem CONTAS_SAL; a ficha de pessoa fisica fica de fora')
    a = p.parse_args(argv)

    t0 = time.time()
    # A chave que torna o identificador de pessoa fisica irreversivel. Sem ela a
    # rodada para antes de escrever qualquer coisa: publicar um identificador que
    # volta ao CPF e pior do que nao publicar a ficha.
    from .ident import tem_sal_de_verdade
    if not tem_sal_de_verdade() and not a.sem_chave:
        print('CONTAS_SAL nao esta no ambiente.')
        print('Sem ela, o identificador de fornecedor pessoa fisica e reversivel.')
        print('No GitHub Actions, crie o secret. Aqui, rode com --sem-chave e as')
        print('fichas de pessoa fisica ficarao de fora.')
        return 1
    hoje = a.hoje or date.today().isoformat()
    ufs_pedidas = [u.strip().upper() for u in a.ufs.split(',') if u.strip()]
    uma_uf = ufs_pedidas[0] if len(ufs_pedidas) == 1 else None

    print(f'rodada de {hoje}')
    print('1. fontes')
    fontes = baixar_fontes(a.tmp, a.fonte_local, quais=['candidatos', 'consulta_cand'])
    zc = zipfile.ZipFile(fontes['candidatos'][0])
    zk = zipfile.ZipFile(fontes['consulta_cand'][0])
    lm = fontes['candidatos'][1]
    tse_gerado = C.geracao(zc) if not uma_uf else ''
    passo(t0, f'zips abertos, TSE gerou em {tse_gerado or "?"}, last-modified {lm or "?"}')

    print('2. somar')
    aggs, nac = {}, A.Nacional()
    nac.hoje = hoje
    A.agregar_despesas(C.despesas(zc, uma_uf), aggs, nac)
    passo(t0, f'{nac.n_despesas:,} despesas, {len(aggs):,} candidatos, '
              f'{len(nac.fornecedores):,} fornecedores, '
              f'{nac.datas_no_futuro} com data no futuro')

    prestador_para_sq = {}
    for sq, ag in aggs.items():
        for pr in ag.prestadores:
            prestador_para_sq[pr] = sq
    A.agregar_pagas(C.pagas(zc, uma_uf), aggs, nac, prestador_para_sq)
    passo(t0, f'{nac.n_pagas:,} pagamentos ligados')

    doacoes_pf = []
    A.agregar_receitas(C.receitas(zc, uma_uf), aggs, nac)
    for r in C.receitas(zc, uma_uf):
        if r.doc and len(r.doc) == 11 and r.sq:
            doacoes_pf.append((r.sq, r.dt, r.valor, r.doc))
    passo(t0, f'{nac.n_receitas:,} receitas')

    cands = list(C.candidaturas(zk, uma_uf))
    sem_ficha = A.juntar_candidaturas(cands, aggs)
    nac.fecha()
    passo(t0, f'{len(cands):,} candidaturas na lista mestra, {sem_ficha} sem ficha')

    if ufs_pedidas:
        aggs = {k: v for k, v in aggs.items() if v.uf in ufs_pedidas}

    print('3. Receita Federal')
    # O cache SEMPRE e lido, mesmo com --sem-receita. A opcao pula a consulta
    # pela rede, nao o que ja foi consultado: uma rodada rapida, so para
    # republicar a pagina, nao pode apagar do site os sinais de CNPJ que a
    # rodada longa da vespera pagou para descobrir.
    cache = os.path.join(a.estado, 'receita.jsonl')
    from .enriquecer import carregar_cache, enriquecer, fila_prioridade
    dados_receita = carregar_cache(cache)
    if a.sem_receita:
        passo(t0, f'{len(dados_receita):,} no cache; consulta pela rede pulada')
    else:
        fila = fila_prioridade(nac, dados_receita)
        passo(t0, f'{len(dados_receita):,} no cache, {len(fila):,} a consultar')
        if fila:
            n = enriquecer(fila, cache, a.orcamento_receita, hoje=hoje)
            dados_receita = carregar_cache(cache)
            passo(t0, f'{n:,} consultados, cache com {len(dados_receita):,}')

    print('4. sinais')
    tetos = carregar_tetos(os.path.join(a.dados, 'tetos_2026.csv'))
    ctx = Contexto(nac, receita=dados_receita, tetos=tetos,
                   cnae_por_tipo=carregar_cnae(os.path.join(a.dados, 'cnae_por_tipo.csv')),
                   cnae_nome=nac.cnae_nome,
                   hoje=hoje)
    ctx.colisao_por_cand = al_ritmo.indexar_colisoes(nac, aggs)
    ctx.doacoes_por_dia = al_doador.indexar_doacoes(doacoes_pf)
    ctx.primeira_vez, ctx.ontem, dia_anterior = H.carregar(a.estado, hoje)
    passo(t0, f'{len(tetos)} tetos, {len(ctx.colisao_por_cand):,} candidatos com nota '
              f'repetida, historico de {dia_anterior or "nenhum dia"}')

    todos, por_sq = [], {}
    for ag in aggs.values():
        xs = avaliar(ag, ctx)
        if xs:
            por_sq[ag.sq] = xs
            todos.extend(xs)
    cota = al_doador.b4_cota(nac)
    ruins = confere_redacao(todos)
    passo(t0, f'{len(todos):,} sinais em {len(por_sq):,} candidatos, '
              f'{len(cota)} partidos na cota, {len(ruins)} textos reprovados')
    if ruins:
        for r in ruins[:5]:
            print(f'      REDACAO: {r}')
        raise SystemExit('texto de alarme fora das travas: nao publica')

    refs = A.referencias(aggs)
    passo(t0, f'{len(refs)} grupos de comparacao (UF x cargo)')

    print('5. escrever')
    dics = {k: E.Dic() for k in ('tipo', 'partido', 'fed', 'alarme',
                                 'ocupacao')}
    for cod in sorted(CATALOGO):
        dics['alarme'].id(cod)
    os.makedirs(a.site, exist_ok=True)
    ufs_saida, bytes_uf = {}, 0
    for uf, lista in sorted(A.por_uf(aggs).items()):
        n = E.escrever_uf(uf, lista, por_sq, dics, a.site)
        bytes_uf += n
        ufs_saida[uf] = {
            'n': len(lista),
            'com_gasto': sum(1 for x in lista if x.contratado),
            'contratado': sum(x.contratado for x in lista),
            'pago': sum(x.pago for x in lista),
            'receita': sum(x.receita for x in lista),
            'alarmes': sum(len(por_sq.get(x.sq, ())) for x in lista),
            'bytes': n,
            'pares': {c: refs[(uf, c)] for c in A.CARGOS_PAINEL
                      if (uf, c) in refs},
        }
    passo(t0, f'{len(ufs_saida)} UFs, {bytes_uf / 1e6:.1f} MB')

    n_ficha = bytes_ficha = 0
    for ag in aggs.values():
        if not ag.movimento and ag.sq not in por_sq:
            continue
        bytes_ficha += E.escrever_ficha(ag, por_sq.get(ag.sq, []), dics,
                                        ctx.cnae_nome, a.site,
                                        pares=A.posicao(ag, refs))
        n_ficha += 1
    passo(t0, f'{n_ficha:,} fichas, {bytes_ficha / 1e6:.1f} MB')

    b_br = E.escrever_brasil(list(aggs.values()), por_sq, dics, a.site)
    passo(t0, f'Brasil inteiro: {b_br / 1e6:.2f} MB')
    b_tip = E.escrever_tipos_brasil(list(aggs.values()), dics, a.site)
    passo(t0, f'tipo por candidatura no pais: {b_tip / 1e6:.2f} MB')
    b_ind = E.escrever_indice(list(aggs.values()), dics, a.site)
    b_al = E.escrever_alarmes(todos, aggs, dics, a.site)
    fichas_forn = E.escrever_fornecedores_fichas(nac, aggs, dados_receita,
                                                 nac.cnae_nome, todos, a.site)
    passo(t0, f'{fichas_forn["fornecedores"]:,} fichas de fornecedor em '
              f'{fichas_forn["arquivos"]:,} arquivos, '
              f'{fichas_forn["bytes"] / 1e6:.1f} MB')
    if fichas_forn.get('colisoes'):
        passo(t0, f'   ATENCAO: {fichas_forn["colisoes"]:,} fichas de fornecedor '
                  f'nao foram escritas, o que indica identificador repetido')
    if fichas_forn['pessoas_fora']:
        passo(t0, f'   ATENCAO: {fichas_forn["pessoas_fora"]:,} fichas de pessoa '
                  f'fisica NAO foram escritas, porque CONTAS_SAL nao esta no '
                  f'ambiente e sem ela o identificador volta ao CPF')
    recortes = A.recorte_fornecedores(aggs)
    b_rec = sum(E.escrever_forn_recorte(unidade, recorte, nac, dics, a.site)
                for unidade, recorte in sorted(recortes.items()))
    passo(t0, f'recorte de fornecedor em {len(recortes)} arquivos, '
              f'{b_rec / 1e6:.2f} MB')
    cruzados = A.recorte_forn_cruzado(aggs)
    b_cru = sum(E.escrever_forn_cruzado(unidade, cruzado, nac, dics, a.site)
                for unidade, cruzado in sorted(cruzados.items()))
    passo(t0, f'fornecedor cruzado em {len(cruzados)} arquivos, '
              f'{b_cru / 1e6:.2f} MB')
    # o panorama e a lista nacional de fornecedores sairam em 18/09: a tela passou
    # a agrupar por partido, estado e cargo no proprio front, sobre as linhas que
    # ja estao filtradas, e quem recebeu vem do recorte por unidade
    E.grava(os.path.join(a.site, 'cota.json'), {'n': len(cota), 'p': cota})

    contagens = {
        'candidaturas': len(aggs),
        'com_movimento': sum(1 for x in aggs.values() if x.movimento),
        'despesas': nac.n_despesas, 'pagamentos': nac.n_pagas,
        'receitas': nac.n_receitas,
        'fornecedores': len(nac.fornecedores), 'doadores': len(nac.doadores),
        'contratado': nac.total_contratado, 'pago': nac.total_pago,
        'receita': nac.total_receita,
        'sinais': len(todos), 'candidatos_com_sinal': len(por_sq),
        'fichas': n_ficha,
        'cnpj_com_receita': len(dados_receita),
        'despesas_com_data_no_futuro': nac.datas_no_futuro,
    }
    E.escrever_meta(dics, contagens, ufs_saida, sorted(A.CARGOS_PAINEL),
                    hoje, {'gerado': tse_gerado, 'last_modified': lm,
                           'data_max_despesa': nac.data_max},
                    a.site, catalogo=CATALOGO, gravidades=GRAVIDADE,
                    forn={'blocos': fichas_forn['blocos'],
                          'n': fichas_forn['fornecedores'],
                          'pessoas_fora': fichas_forn['pessoas_fora'],
                          'pessoas_pequenas': fichas_forn['pessoas_pequenas'],
                          'piso_pf': fichas_forn['piso_pf'],
                          'com_cadastro': sum(1 for d in nac.fornecedores
                                              if len(d) == 14
                                              and d in dados_receita)})
    passo(t0, f'indice {b_ind / 1e6:.2f} MB, alarmes {b_al / 1e3:.0f} KB, '
              f'recorte de fornecedor {b_rec / 1e6:.2f} MB')

    print('6. estado')
    H.gravar(a.estado, hoje, nac, aggs)
    passo(t0, 'historico gravado')

    print('\nresumo')
    print(f'   R$ {nac.total_contratado / 100:,.2f} contratados, '
          f'R$ {nac.total_pago / 100:,.2f} pagos, '
          f'R$ {nac.total_receita / 100:,.2f} recebidos')
    print(f'   {contagens["com_movimento"]:,} candidaturas com movimento de '
          f'{contagens["candidaturas"]:,}')
    print(f'   {len(todos):,} sinais')
    maiores = sorted(ufs_saida.items(), key=lambda kv: -kv[1]['bytes'])[:3]
    for uf, d in maiores:
        print(f'   maior arquivo: {uf} com {d["bytes"] / 1e6:.2f} MB '
              f'({d["n"]:,} candidatos)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
