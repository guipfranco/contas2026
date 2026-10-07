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
