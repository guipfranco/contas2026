#!/usr/bin/env python3
"""Tira do consulta_cand o que identifica a pessoa, antes de ele virar fixture.

O TSE publica o CPF inteiro, o titulo de eleitor e a data de nascimento de quem
se candidata. A fixture mora num repositorio publico, e o artefato do workflow
tambem e publico enquanto existe. O que sai daqui:

- CPF: um CPF falso, com digito verificador valido, deterministico pela chave.
  O mesmo CPF vira o mesmo falso em todo texto anonimizado com a mesma chave, e
  por isso a ligacao entre 2018, 2022 e 2026 continua de pe na fixture. O CPF
  que aparece colado em outro campo vira o mesmo falso.
- Titulo de eleitor e toda coluna com EMAIL no nome: '#NULO'.
- Data de nascimento: o ano fica, dia (01 a 28) e mes saem do hash do nome
  normalizado com a data, para a mesma pessoa ter a mesma data falsa nos tres
  anos, com ou sem CPF.
- Marcador de vazio fica como esta. Todo o resto do arquivo e o mesmo.

A chave e aleatoria e vive so na memoria de uma execucao: nunca e gravada, e sem
ela o falso nao volta para o verdadeiro.
"""
import csv
import hashlib
import hmac
import io
import re

from pipeline.carregar import VAZIO
from pipeline.eleitos import normaliza_nome

COL_CPF = 'NR_CPF_CANDIDATO'
COL_TITULO = 'NR_TITULO_ELEITORAL_CANDIDATO'
COL_NASC = 'DT_NASCIMENTO'
ONZE = re.compile(r'(?<!\d)\d{11}(?!\d)')
BOM = '﻿'


def _numero(chave, texto, volta):
    d = hmac.new(chave, f'{texto}|{volta}'.encode('utf-8'), hashlib.sha256).digest()
    return int.from_bytes(d[:8], 'big')


def _digitos(base):
    """Os dois digitos verificadores de um CPF de nove digitos."""
    doc = base
    for n in (9, 10):
        soma = sum(int(doc[i]) * (n + 1 - i) for i in range(n))
        doc += str((soma * 10) % 11 % 10)
    return doc


def cpf_falso(cpf, chave):
    volta = 0
    while True:
        falso = _digitos(f'{_numero(chave, "cpf|" + cpf, volta) % 10 ** 9:09d}')
        if falso != cpf and falso != falso[0] * 11:
            return falso
        volta += 1


def data_falsa(data, nome, chave):
    """'17/03/1970' -> outro dia e mes de 1970. O que nao for data fica."""
    m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', data.strip())
    if not m:
        return data
    volta = 0
    while True:
        h = _numero(chave, 'nasc|' + normaliza_nome(nome) + '|' + data.strip(), volta)
        falsa = f'{1 + h % 28:02d}/{1 + (h // 28) % 12:02d}/{m.group(3)}'
        if falsa != data.strip():
            return falsa
        volta += 1


def anonimizar_csv(texto, chave):
    """O texto de um consulta_cand, anonimizado. Mesma forma do TSE: ponto e
    virgula, tudo entre aspas, o mesmo fim de linha, o BOM se havia."""
    bom = texto.startswith(BOM)
    corpo = texto[1:] if bom else texto
    primeira = corpo.split('\n', 1)[0]
    fim = '\r\n' if primeira.endswith('\r') else '\n'
    linhas = list(csv.reader(io.StringIO(corpo, newline=''), delimiter=';'))
    if not linhas:
        return texto
    cab = linhas[0]
    i_cpf = cab.index(COL_CPF) if COL_CPF in cab else -1
    i_tit = cab.index(COL_TITULO) if COL_TITULO in cab else -1
    i_nasc = cab.index(COL_NASC) if COL_NASC in cab else -1
    i_nome = cab.index('NM_CANDIDATO') if 'NM_CANDIDATO' in cab else -1
    i_email = [i for i, c in enumerate(cab) if 'EMAIL' in c.upper()]

    # primeira passada: todo CPF da coluna de CPF, para achar o mesmo numero
    # colado em qualquer outro campo
    mapa = {}
    if i_cpf >= 0:
        for l in linhas[1:]:
            if i_cpf < len(l) and ONZE.fullmatch(l[i_cpf].strip()):
                cpf = l[i_cpf].strip()
                mapa.setdefault(cpf, cpf_falso(cpf, chave))

    def troca(m):
        return mapa.get(m.group(0), m.group(0))

    saida = [cab]
    for l in linhas[1:]:
        l = list(l)
        for i, v in enumerate(l):
            if v.strip() in VAZIO:
                continue
            if i == i_tit or i in i_email:
                l[i] = '#NULO'
            elif i == i_nasc:
                l[i] = data_falsa(v, l[i_nome] if 0 <= i_nome < len(l) else '', chave)
            elif mapa:
                l[i] = ONZE.sub(troca, v)
        saida.append(l)
    buf = io.StringIO()
    csv.writer(buf, delimiter=';', quoting=csv.QUOTE_ALL, lineterminator=fim).writerows(saida)
    return (BOM if bom else '') + buf.getvalue()
