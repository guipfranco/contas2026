#!/usr/bin/env python3
"""Le os CSV do TSE e devolve linhas normalizadas, ou falha alto.

Tres decisoes deste modulo, todas medidas contra o dado real em 17/09/2026:

**Encoding e latin-1.** Confirmado abrindo os arquivos: acento sai certo.

**O marcador de vazio tem quatro formas.** `#NULO`, `#NULO#`, `-1` e `#NE`
convivem no mesmo arquivo, em colunas diferentes. Tratar so uma delas deixa
literalmente a string '#NULO' virar nome de fornecedor no painel.

**Somar todas as linhas e o certo, e isso nao era obvio.** `SQ_DESPESA` nao
identifica uma linha: identifica um grupo (uma nota com varios itens). Em RR,
14.292 linhas tem so 12.064 SQ_DESPESA distintos, e as linhas repetidas trazem
descricao e valor diferentes. Medido nos dois caminhos: somando tudo, nenhum
candidato aparece com pagamento maior que a despesa contratada; deduplicando
por SQ_DESPESA, 72 candidatos ficam impossiveis, com R$ 2,6 mi de excesso.
Logo: soma tudo, nunca deduplica.

**So o arquivo BRASIL e lido.** Ele traz DF e os cargos nacionais, que nao tem
arquivo por UF proprio: sao 26 arquivos por UF mais o BRASIL, e DF nao esta
entre eles. Quem agrupa por UF e este pipeline, pela coluna SG_UF.
"""
import csv
import io
import sys
import zipfile
from collections import namedtuple

csv.field_size_limit(16 * 1024 * 1024)

VAZIO = frozenset(('', '#NULO', '#NULO#', '-1', '#NE', '#NE#', 'NULO'))

# Os cabecalhos que o pipeline espera. Falta de coluna e erro alto: melhor a
# rodada quebrar e o site de ontem ficar no ar do que publicar numero errado.
COLUNAS_DESPESA = [
    'SG_UF', 'CD_CARGO', 'DS_CARGO', 'SQ_CANDIDATO', 'NR_CANDIDATO',
    'NM_CANDIDATO', 'NR_CPF_CANDIDATO', 'NR_PARTIDO', 'SG_PARTIDO',
    'SQ_PRESTADOR_CONTAS', 'TP_PRESTACAO_CONTAS', 'DT_PRESTACAO_CONTAS',
    'DS_TIPO_FORNECEDOR', 'CD_CNAE_FORNECEDOR', 'DS_CNAE_FORNECEDOR',
    'NR_CPF_CNPJ_FORNECEDOR', 'NM_FORNECEDOR', 'NM_FORNECEDOR_RFB',
    'SG_UF_FORNECEDOR', 'NM_MUNICIPIO_FORNECEDOR', 'SQ_CANDIDATO_FORNECEDOR',
    'NR_CANDIDATO_FORNECEDOR', 'DS_CARGO_FORNECEDOR', 'SG_PARTIDO_FORNECEDOR',
    'DS_TIPO_DOCUMENTO', 'NR_DOCUMENTO', 'DS_ORIGEM_DESPESA', 'SQ_DESPESA',
    'DT_DESPESA', 'DS_DESPESA', 'VR_DESPESA_CONTRATADA',
]
COLUNAS_PAGA = [
    'SG_UF', 'SQ_PRESTADOR_CONTAS', 'DS_FONTE_DESPESA', 'DS_ORIGEM_DESPESA',
    'DS_ESPECIE_RECURSO', 'SQ_DESPESA', 'DT_PAGTO_DESPESA', 'VR_PAGTO_DESPESA',
]
COLUNAS_RECEITA = [
    'SG_UF', 'CD_CARGO', 'SQ_CANDIDATO', 'SG_PARTIDO', 'DS_FONTE_RECEITA',
    'DS_ORIGEM_RECEITA', 'DS_NATUREZA_RECEITA', 'DS_ESPECIE_RECEITA',
    'CD_CNAE_DOADOR', 'NR_CPF_CNPJ_DOADOR', 'NM_DOADOR', 'NM_DOADOR_RFB',
    'SQ_CANDIDATO_DOADOR', 'SG_PARTIDO_DOADOR', 'SQ_RECEITA', 'DT_RECEITA',
    'VR_RECEITA', 'DS_GENERO', 'DS_COR_RACA',
]
COLUNAS_ORIGINARIO = [
    'SG_UF', 'NR_CPF_CNPJ_DOADOR_ORIGINARIO', 'NM_DOADOR_ORIGINARIO',
    'NM_DOADOR_ORIGINARIO_RFB', 'TP_DOADOR_ORIGINARIO', 'SQ_RECEITA',
    'DT_RECEITA', 'VR_RECEITA',
]
COLUNAS_CAND = [
    'SG_UF', 'SG_UE', 'CD_CARGO', 'DS_CARGO', 'SQ_CANDIDATO', 'NR_CANDIDATO',
    'NM_CANDIDATO', 'NM_URNA_CANDIDATO', 'NR_CPF_CANDIDATO',
    'DS_SITUACAO_CANDIDATURA', 'NR_PARTIDO', 'SG_PARTIDO', 'NM_PARTIDO',
    'NR_FEDERACAO', 'NM_FEDERACAO', 'DS_COMPOSICAO_FEDERACAO',
    'DS_GENERO', 'DS_COR_RACA', 'DS_OCUPACAO', 'DT_NASCIMENTO',
    'DS_SIT_TOT_TURNO',
]

Despesa = namedtuple('Despesa', 'uf cargo sq nr nome cpf partido prestador '
                                'tipo_prest tipo_forn cnae doc forn forn_rfb '
                                'uf_forn sq_cand_forn cargo_forn part_forn '
                                'tipo_doc num_doc tipo dt valor descricao')
Paga = namedtuple('Paga', 'uf prestador fonte tipo especie dt valor')
Receita = namedtuple('Receita', 'uf cargo sq partido fonte origem natureza '
                                'especie cnae doc doador doador_rfb '
                                'sq_cand_doador part_doador sq_receita dt '
                                'valor genero cor_raca')
Originario = namedtuple('Originario', 'uf doc nome nome_rfb tipo sq_receita dt valor')
Cand = namedtuple('Cand', 'uf ue cargo ds_cargo sq nr nome urna cpf situacao '
                          'nr_partido partido nm_partido nr_fed fed comp_fed '
                          'genero cor_raca ocupacao nascimento sit_turno')


class LayoutMudou(RuntimeError):
    """O TSE mexeu no arquivo. Melhor parar do que adivinhar."""


def limpo(s):
    """Texto util, ou string vazia. Trata as quatro formas de vazio do TSE."""
    s = (s or '').strip()
    return '' if s in VAZIO else s


def valor(s):
    """'1.234,56' -> 123456 centavos. Vazio e lixo viram 0."""
    s = (s or '').strip()
    if s in VAZIO:
        return 0
    s = s.replace('.', '').replace(',', '.')
    try:
        return int(round(float(s) * 100))
    except ValueError:
        return 0


def data(s):
    """'17/09/2026' -> '2026-09-17'. O que nao for data vira string vazia."""
    s = (s or '').strip()
    if len(s) != 10 or s[2] != '/' or s[5] != '/':
        return ''
    d, m, a = s[:2], s[3:5], s[6:]
    if not (d.isdigit() and m.isdigit() and a.isdigit()):
        return ''
    return f'{a}-{m}-{d}'


def documento(s):
    """So digito. Devolve '' quando nao for CPF (11) nem CNPJ (14)."""
    s = ''.join(c for c in (s or '') if c.isdigit())
    return s if len(s) in (11, 14) else ''


def num_documento(s):
    """Numero da nota, normalizado para comparar entre candidatos.

    O TSE aceita texto livre aqui. 'S/N', 'RECIBO' e afins nao identificam
    nada, entao nao servem para cruzar; so numero com tres digitos ou mais.
    """
    s = limpo(s).upper()
    so_num = ''.join(c for c in s if c.isdigit()).lstrip('0')
    if len(so_num) < 3:
        return ''
    return so_num


def cnpj_raiz(doc):
    """Os 8 primeiros digitos do CNPJ: a empresa, sem a filial."""
    return doc[:8] if len(doc) == 14 else ''


def mascara(doc):
    """CPF nunca sai inteiro daqui: '123.***.**9-00' vira '***.456.789-**'.

    O TSE ja publica o CPF completo, mas repetir isso num painel facil de
    varrer e outra coisa. CNPJ sai inteiro, porque e publico por natureza.
    """
    if len(doc) == 11:
        return f'***.{doc[3:6]}.{doc[6:9]}-**'
    if len(doc) == 14:
        return f'{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}'
    return ''


def checar_layout(cabecalho, esperado, nome):
    faltando = [c for c in esperado if c not in cabecalho]
    if faltando:
        raise LayoutMudou(
            f'{nome}: o TSE mudou o arquivo. Faltam {len(faltando)} colunas: '
            f'{", ".join(faltando)}. Colunas presentes: {", ".join(cabecalho)}')
    return True


def _dicts(z, membro, esperado, nome):
    """Itera dicts do CSV, tolerando BOM, NUL e linha torta."""
    with io.TextIOWrapper(z.open(membro), encoding='latin-1', newline='') as f:
        leitor = csv.reader((l.replace('\0', '') for l in f), delimiter=';')
        try:
            cab = next(leitor)
        except StopIteration:
            return
        cab = [c.lstrip('﻿').strip('"').strip() for c in cab]
        checar_layout(cab, esperado, nome)
        n = len(cab)
        for linha in leitor:
            if len(linha) == n:
                yield dict(zip(cab, linha))


def membro_brasil(z, prefixo):
    """O arquivo BRASIL do prefixo pedido. Ele tem DF e os cargos nacionais."""
    alvo = f'{prefixo}_BRASIL.csv'
    for m in z.namelist():
        if m.endswith(alvo) or m == alvo:
            return m
    raise LayoutMudou(f'{alvo} nao esta no zip. Membros: {z.namelist()[:10]}')


def membro_uf(z, prefixo, uf):
    alvo = f'{prefixo}_{uf}.csv'
    for m in z.namelist():
        if m.endswith(alvo) or m == alvo:
            return m
    raise LayoutMudou(f'{alvo} nao esta no zip')


def _membro(z, prefixo, uf):
    return membro_uf(z, prefixo, uf) if uf else membro_brasil(z, prefixo)


def despesas(z, uf=None):
    for r in _dicts(z, _membro(z, 'despesas_contratadas_candidatos_2026', uf),
                    COLUNAS_DESPESA, 'despesas contratadas'):
        yield Despesa(
            uf=limpo(r['SG_UF']), cargo=limpo(r['CD_CARGO']),
            sq=limpo(r['SQ_CANDIDATO']), nr=limpo(r['NR_CANDIDATO']),
            nome=limpo(r['NM_CANDIDATO']), cpf=documento(r['NR_CPF_CANDIDATO']),
            partido=limpo(r['SG_PARTIDO']),
            prestador=limpo(r['SQ_PRESTADOR_CONTAS']),
            tipo_prest=limpo(r['TP_PRESTACAO_CONTAS']),
            tipo_forn=limpo(r['DS_TIPO_FORNECEDOR']),
            cnae=limpo(r['CD_CNAE_FORNECEDOR']),
            doc=documento(r['NR_CPF_CNPJ_FORNECEDOR']),
            forn=limpo(r['NM_FORNECEDOR']), forn_rfb=limpo(r['NM_FORNECEDOR_RFB']),
            uf_forn=limpo(r['SG_UF_FORNECEDOR']),
            sq_cand_forn=limpo(r['SQ_CANDIDATO_FORNECEDOR']),
            cargo_forn=limpo(r['DS_CARGO_FORNECEDOR']),
            part_forn=limpo(r['SG_PARTIDO_FORNECEDOR']),
            tipo_doc=limpo(r['DS_TIPO_DOCUMENTO']),
            num_doc=num_documento(r['NR_DOCUMENTO']),
            tipo=limpo(r['DS_ORIGEM_DESPESA']), dt=data(r['DT_DESPESA']),
            valor=valor(r['VR_DESPESA_CONTRATADA']),
            descricao=limpo(r['DS_DESPESA']))


def pagas(z, uf=None):
    for r in _dicts(z, _membro(z, 'despesas_pagas_candidatos_2026', uf),
                    COLUNAS_PAGA, 'despesas pagas'):
        yield Paga(uf=limpo(r['SG_UF']), prestador=limpo(r['SQ_PRESTADOR_CONTAS']),
                   fonte=limpo(r['DS_FONTE_DESPESA']),
                   tipo=limpo(r['DS_ORIGEM_DESPESA']),
                   especie=limpo(r['DS_ESPECIE_RECURSO']),
                   dt=data(r['DT_PAGTO_DESPESA']),
                   valor=valor(r['VR_PAGTO_DESPESA']))


def receitas(z, uf=None):
    for r in _dicts(z, _membro(z, 'receitas_candidatos_2026', uf),
                    COLUNAS_RECEITA, 'receitas'):
        yield Receita(
            uf=limpo(r['SG_UF']), cargo=limpo(r['CD_CARGO']),
            sq=limpo(r['SQ_CANDIDATO']), partido=limpo(r['SG_PARTIDO']),
            fonte=limpo(r['DS_FONTE_RECEITA']), origem=limpo(r['DS_ORIGEM_RECEITA']),
            natureza=limpo(r['DS_NATUREZA_RECEITA']),
            especie=limpo(r['DS_ESPECIE_RECEITA']), cnae=limpo(r['CD_CNAE_DOADOR']),
            doc=documento(r['NR_CPF_CNPJ_DOADOR']), doador=limpo(r['NM_DOADOR']),
            doador_rfb=limpo(r['NM_DOADOR_RFB']),
            sq_cand_doador=limpo(r['SQ_CANDIDATO_DOADOR']),
            part_doador=limpo(r['SG_PARTIDO_DOADOR']),
            sq_receita=limpo(r['SQ_RECEITA']), dt=data(r['DT_RECEITA']),
            valor=valor(r['VR_RECEITA']), genero=limpo(r['DS_GENERO']),
            cor_raca=limpo(r['DS_COR_RACA']))


def originarios(z, uf=None):
    for r in _dicts(z, _membro(z, 'receitas_candidatos_doador_originario_2026', uf),
                    COLUNAS_ORIGINARIO, 'doador originario'):
        yield Originario(
            uf=limpo(r['SG_UF']), doc=documento(r['NR_CPF_CNPJ_DOADOR_ORIGINARIO']),
            nome=limpo(r['NM_DOADOR_ORIGINARIO']),
            nome_rfb=limpo(r['NM_DOADOR_ORIGINARIO_RFB']),
            tipo=limpo(r['TP_DOADOR_ORIGINARIO']),
            sq_receita=limpo(r['SQ_RECEITA']), dt=data(r['DT_RECEITA']),
            valor=valor(r['VR_RECEITA']))


def candidaturas(z, uf=None):
    for r in _dicts(z, _membro(z, 'consulta_cand_2026', uf), COLUNAS_CAND,
                    'consulta_cand'):
        yield Cand(
            uf=limpo(r['SG_UF']), ue=limpo(r['SG_UE']), cargo=limpo(r['CD_CARGO']),
            ds_cargo=limpo(r['DS_CARGO']), sq=limpo(r['SQ_CANDIDATO']),
            nr=limpo(r['NR_CANDIDATO']), nome=limpo(r['NM_CANDIDATO']),
            urna=limpo(r['NM_URNA_CANDIDATO']) or limpo(r['NM_CANDIDATO']),
            cpf=documento(r['NR_CPF_CANDIDATO']),
            situacao=limpo(r['DS_SITUACAO_CANDIDATURA']),
            nr_partido=limpo(r['NR_PARTIDO']), partido=limpo(r['SG_PARTIDO']),
            nm_partido=limpo(r['NM_PARTIDO']), nr_fed=limpo(r['NR_FEDERACAO']),
            fed=limpo(r['NM_FEDERACAO']), comp_fed=limpo(r['DS_COMPOSICAO_FEDERACAO']),
            genero=limpo(r['DS_GENERO']), cor_raca=limpo(r['DS_COR_RACA']),
            ocupacao=limpo(r['DS_OCUPACAO']), nascimento=data(r['DT_NASCIMENTO']),
            sit_turno=limpo(r['DS_SIT_TOT_TURNO']))


def geracao(z, prefixo='despesas_contratadas_candidatos_2026'):
    """A data que o TSE carimbou no arquivo (DT_GERACAO da primeira linha)."""
    membro = membro_brasil(z, prefixo)
    with io.TextIOWrapper(z.open(membro), encoding='latin-1', newline='') as f:
        leitor = csv.reader(f, delimiter=';')
        cab = [c.lstrip('﻿').strip('"').strip() for c in next(leitor)]
        linha = next(leitor, None)
        if not linha:
            return ''
        r = dict(zip(cab, linha))
        return data(r.get('DT_GERACAO', ''))


if __name__ == '__main__':
    z = zipfile.ZipFile(sys.argv[1])
    uf = sys.argv[2] if len(sys.argv) > 2 else None
    n = 0
    total = 0
    for d in despesas(z, uf):
        n += 1
        total += d.valor
    print(f'{n} despesas, R$ {total / 100:,.2f}')
