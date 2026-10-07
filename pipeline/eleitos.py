#!/usr/bin/env python3
"""Quem foi eleito antes e quem e eleito agora, ligando a mesma pessoa.

**A eleicao de comparacao.** O Senado de 2026 renova as cadeiras eleitas em
2018; os outros cargos comparam com 2022. "Eleito antes" e quem foi eleito em
2022 para um dos cargos contados, mais quem foi eleito senador em 2018.

**A ligacao e pelo CPF, que nunca sai daqui.** O SQ_CANDIDATO muda a cada
eleicao. O CPF vira HMAC com a CONTAS_SAL, como em ident.py. Quando o CPF falta
no arquivo antigo, a ligacao usa o nome completo normalizado e a data de
nascimento, tambem por HMAC. Nem CPF nem data vao para arquivo nenhum.

**anteriores.json mora na branch dados.** E feito uma vez, por
ferramentas/anteriores.py no Actions, e carrega a marca do sal com que foi
feito: se a CONTAS_SAL mudar, a rodada recusa o arquivo em vez de ligar
ninguem a ninguem.
"""
import csv
import hashlib
import hmac
import json
import os
import re
import unicodedata

from . import desfecho as D
from .ident import ident, sal

CARGOS_CONTADOS = ('1', '3', '5', '6', '7', '8')
CARGOS_VICE = ('2', '4', '9', '10')
SENADO = '5'
ARQUIVO = 'anteriores.json'


def normaliza_nome(nome):
    s = unicodedata.normalize('NFKD', nome or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).strip().upper()


def _hmac(texto):
    return 'p' + hmac.new(sal(), texto.encode('utf-8'),
                          hashlib.sha256).hexdigest()[:16]


def chave_cpf(cpf):
    return ident(cpf) if cpf and len(cpf) == 11 else ''


def chave_nasc(nome, nascimento):
    n = normaliza_nome(nome)
    if not n or not nascimento:
        return ''
    return _hmac(n + '|' + nascimento)


def sal_marca():
    """Oito hex que mudam quando a CONTAS_SAL muda, e nao a revelam."""
    return _hmac('anteriores')[1:9]


def genero(ds):
    s = normaliza_nome(ds)
    if s.startswith('FEM'):
        return 'F'
    return 'M' if s.startswith('MASC') else ''


def linhas_anteriores(cands, ano):
    """Os eleitos de um ano anterior nos cargos contados. Em 2018, so o Senado."""
    out = []
    for c in cands:
        if D.codigo(c.sit_turno) != D.ELEITA or c.cargo not in CARGOS_CONTADOS:
            continue
        if ano == 2018 and c.cargo != SENADO:
            continue
        out.append({'chave': chave_cpf(c.cpf),
                    'chave_nasc': chave_nasc(c.nome, c.nascimento),
                    'ano': ano, 'cargo': c.cargo, 'uf': c.uf,
                    'partido': c.partido, 'nome_urna': c.urna,
                    'genero': genero(c.genero)})
    return out


def gravar_anteriores(estado, linhas):
    os.makedirs(estado, exist_ok=True)
    caminho = os.path.join(estado, ARQUIVO)
    with open(caminho + '.tmp', 'w', encoding='utf-8') as f:
        json.dump({'sal_marca': sal_marca(), 'linhas': linhas}, f,
                  ensure_ascii=False, separators=(',', ':'))
    os.replace(caminho + '.tmp', caminho)
    return caminho


def ler_anteriores(estado):
    """(linhas, motivo). Motivo '' quando serve, 'falta' ou 'sal' quando nao."""
    caminho = os.path.join(estado, ARQUIVO)
    if not os.path.exists(caminho):
        return [], 'falta'
    with open(caminho, encoding='utf-8') as f:
        d = json.load(f)
    if d.get('sal_marca') != sal_marca():
        return [], 'sal'
    return d.get('linhas', []), ''


MESMO_CARGO, OUTRO_CARGO, SEGUNDO_TURNO, VICE, NAO_ELEITA, SEM_CANDIDATURA = range(1, 7)


def carregar_sucessao(caminho):
    """Partido antigo -> sucessor, de dados/sucessao-partidos.csv. Sem o
    arquivo, ninguem tem sucessor, e a rodada avisa as siglas sem par."""
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding='utf-8', newline='') as f:
        return {r['antigo'].strip(): r['sucessor'].strip()
                for r in csv.DictReader(f) if (r.get('antigo') or '').strip()}


def sucessor(sigla, tabela):
    """Transitivo: se A virou B e B virou C, A vira C."""
    vistos = set()
    while sigla in tabela and sigla not in vistos:
        vistos.add(sigla)
        sigla = tabela[sigla]
    return sigla


def _prioridade(c):
    """Qual das candidaturas de 2026 de uma pessoa decide o destino dela."""
    d = D.codigo(c.sit_turno)
    if c.cargo in CARGOS_CONTADOS and d == D.ELEITA:
        return 0
    if c.cargo in CARGOS_CONTADOS and d == D.SEGUNDO_TURNO:
        return 1
    if c.cargo in CARGOS_VICE:
        return 2
    return 3


def _destino(a, c):
    if c is None:
        return SEM_CANDIDATURA
    d = D.codigo(c.sit_turno)
    if c.cargo in CARGOS_CONTADOS and d == D.ELEITA:
        mesmo = c.cargo == a['cargo'] and c.uf == a['uf']
        return MESMO_CARGO if mesmo else OUTRO_CARGO
    if c.cargo in CARGOS_CONTADOS and d == D.SEGUNDO_TURNO:
        return SEGUNDO_TURNO
    if c.cargo in CARGOS_VICE:
        return VICE
    return NAO_ELEITA


def _pessoa(a, c, suc):
    return {
        'nome': (c.urna if c else '') or (a or {}).get('nome_urna', ''),
        'uf_antes': a['uf'] if a else '',
        'cargo_antes': a['cargo'] if a else '',
        'partido_antes': a['partido'] if a else '',
        'ano_antes': a['ano'] if a else 0,
        'destino': _destino(a, c) if a else 0,
        'uf_agora': c.uf if c else '',
        'cargo_agora': c.cargo if c else '',
        'partido_agora': c.partido if c else '',
        'desfecho': D.codigo(c.sit_turno) if c else 0,
        'sq': c.sq if c else '',
        'genero': genero(c.genero) if c else (a or {}).get('genero', ''),
        'mudou': int(bool(a and c and a['partido'] and c.partido
                          and sucessor(a['partido'], suc) != c.partido)),
    }


def cruzar(anteriores, cands, suc, ufs=None):
    """Uma linha por pessoa: todo eleito de antes, e toda candidatura de 2026
    eleita ou no 2o turno nos cargos contados. Devolve (pessoas, estatisticas)."""
    ufs = set(ufs or ())
    brutas, antes, nasc_para_chave = {}, {}, {}

    def guarda(k, a):
        # quem foi eleito em 2018 e de novo em 2022 e lido pelo registro de 2022
        if k not in antes or a['ano'] > antes[k]['ano']:
            antes[k] = a

    selecionados = [a for a in anteriores if not ufs or a['uf'] in ufs]
    for a in selecionados:
        doano = brutas.setdefault(str(a['ano']), {})
        doano[a['cargo']] = doano.get(a['cargo'], 0) + 1
        if a['chave']:
            guarda(a['chave'], a)
            if a['chave_nasc']:
                nasc_para_chave.setdefault(a['chave_nasc'], a['chave'])
    # sem CPF: junta com o registro que tem CPF e o mesmo nome e nascimento
    for a in selecionados:
        if a['chave']:
            continue
        guarda(nasc_para_chave.get(a['chave_nasc']) or a['chave_nasc']
               or 'sem:' + a['nome_urna'] + a['uf'], a)

    agora, fed = {}, {}
    for c in cands:
        if ufs and c.uf not in ufs:
            continue
        if c.cargo not in CARGOS_CONTADOS and c.cargo not in CARGOS_VICE:
            continue
        if c.partido and c.fed:
            fed[c.partido] = c.fed
        k = chave_cpf(c.cpf) or chave_nasc(c.nome, c.nascimento) or 'sq:' + c.sq
        if k not in agora or _prioridade(c) < _prioridade(agora[k]):
            agora[k] = c
    por_nasc = {}
    for k, c in agora.items():
        kn = chave_nasc(c.nome, c.nascimento)
        if kn:
            por_nasc.setdefault(kn, k)

    pessoas, usados, por_nome = [], set(), 0
    for a in antes.values():
        ka, pelo_nome = None, False
        if a['chave'] and a['chave'] in agora:
            ka = a['chave']
        elif a['chave_nasc'] and a['chave_nasc'] in por_nasc:
            ka, pelo_nome = por_nasc[a['chave_nasc']], True
        # uma pessoa de 2026 liga a uma pessoa de antes so: nunca dois sq iguais
        if ka in usados:
            ka, pelo_nome = None, False
        if ka:
            usados.add(ka)
            por_nome += pelo_nome
        pessoas.append(_pessoa(a, agora.get(ka) if ka else None, suc))
    for k, c in agora.items():
        if k in usados or c.cargo not in CARGOS_CONTADOS:
            continue
        if D.codigo(c.sit_turno) in (D.ELEITA, D.SEGUNDO_TURNO):
            pessoas.append(_pessoa(None, c, suc))

    siglas_agora = {c.partido for c in cands if c.partido}
    sem_par = sorted({a['partido'] for a in antes.values()
                      if a['partido'] and a['partido'] not in siglas_agora
                      and a['partido'] not in suc})
    return pessoas, {'anteriores': brutas, 'ligados_por_nome': por_nome,
                     'siglas_sem_par': sem_par, 'fed': fed}
