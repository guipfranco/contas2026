#!/usr/bin/env python3
"""O que a rodada de hoje precisa saber sobre as rodadas anteriores.

Sem isto, "fornecedor novo" e "salto no gasto" nao existem: sem ontem nao ha
novo. Dois arquivos, os dois append-only e pequenos:

- `fornecedores-vistos.txt`: um identificador por linha, a primeira vez que
  aquele fornecedor apareceu. Cresce ate uns 420 mil linhas.
- `snapshots/AAAA-MM-DD.json`: o total contratado por candidato naquele dia.
  Uns 600 KB por dia; guarda 30 dias e apaga o resto.

**O arquivo de vistos guardava o documento cru, e isso contradizia a trava.**
Ate 17/09/2026 ele tinha 419.531 linhas de CPF e CNPJ completos, numa branch
publica, enquanto o painel ao lado mascarava o CPF em toda tela. Uma lista
pronta e mais facil de varrer do que o painel inteiro. Agora ele guarda o que
o `ident.py` devolve: CNPJ segue inteiro, porque empresa e publica por
natureza, e pessoa fisica vira um HMAC com chave que nao mora no repositorio.

A conversao e automatica: a primeira rodada que encontrar linha em formato
antigo reescreve o arquivo inteiro. Quem consulta continua perguntando pelo
documento, e quem responde e o `Vistos` aqui embaixo.
"""
import json
import os

from .ident import ident, tem_sal_de_verdade

DIAS_GUARDADOS = 30


def _p(estado, *partes):
    return os.path.join(estado, *partes)


def _documento_cru(linha):
    """Formato antigo: so digitos, com 11 (CPF) ou 14 (CNPJ) deles."""
    return linha.isdigit() and len(linha) in (11, 14)


class Vistos:
    """Os fornecedores ja vistos, guardados por identificador.

    Aceita a pergunta em documento, que e como o resto do pipeline pensa: o
    sinal D1 pergunta "ja vi este fornecedor?" e nao precisa saber que existe
    identificador nenhum.
    """

    def __init__(self, ids=()):
        self.ids = set(ids)

    def __contains__(self, doc):
        # Sem a chave, pessoa fisica nao entra neste arquivo, e entao ela seria
        # "fornecedor novo" todo santo dia. Sem poder acompanhar, a resposta
        # honesta e "ja vista": o sinal D1 cala em vez de disparar no vazio.
        if len(doc or '') != 14 and not tem_sal_de_verdade():
            return True
        return ident(doc) in self.ids

    def __len__(self):
        return len(self.ids)

    def __bool__(self):
        return bool(self.ids)

    def add(self, doc):
        self.ids.add(ident(doc))


def carregar(estado, hoje):
    """(fornecedores ja vistos, total de ontem por candidato, dia de ontem)."""
    ids = set()
    caminho = _p(estado, 'fornecedores-vistos.txt')
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as f:
            for linha in f:
                d = linha.strip()
                if not d:
                    continue
                # linha antiga e documento cru: vira identificador ja na
                # leitura, senao o D1 acharia que o pais inteiro e fornecedor
                # novo no dia da mudanca
                ids.add(ident(d) if _documento_cru(d) else d)

    dir_snap = _p(estado, 'snapshots')
    anterior, dia = {}, ''
    if os.path.isdir(dir_snap):
        dias = sorted(x[:-5] for x in os.listdir(dir_snap) if x.endswith('.json'))
        dias = [d for d in dias if d < hoje]
        if dias:
            dia = dias[-1]
            with open(_p(dir_snap, f'{dia}.json'), encoding='utf-8') as f:
                anterior = json.load(f)
    return Vistos(ids), anterior, dia


def gravar(estado, hoje, nac, aggs):
    """Acrescenta os fornecedores novos e grava o retrato de hoje."""
    os.makedirs(_p(estado, 'snapshots'), exist_ok=True)
    caminho = _p(estado, 'fornecedores-vistos.txt')
    ids, converter = set(), False
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as f:
            for linha in f:
                d = linha.strip()
                if not d:
                    continue
                if _documento_cru(d) and len(d) == 11:
                    converter = True
                    ids.add(ident(d))
                else:
                    ids.add(d)
    # Sem a chave do ambiente, o identificador de pessoa fisica e reversivel, e
    # este arquivo vai para uma branch publica: nessa condicao so entram CNPJ, e
    # a conversao do formato antigo espera a rodada que tiver a chave.
    com_chave = tem_sal_de_verdade()
    docs = nac.fornecedores if com_chave else [d for d in nac.fornecedores
                                               if len(d) == 14]
    novos = sorted({ident(d) for d in docs} - ids)
    if converter and not com_chave:
        converter = False
    if converter:
        # uma vez so, na primeira rodada depois da mudanca: o arquivo inteiro
        # deixa o formato antigo, e nao fica CPF de ninguem para tras
        tmp = caminho + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(ids | set(novos))) + '\n')
        os.replace(tmp, caminho)
    elif novos:
        with open(caminho, 'a', encoding='utf-8') as f:
            f.write('\n'.join(novos) + '\n')

    snap = {a.sq: a.contratado for a in aggs.values() if a.contratado}
    tmp = _p(estado, 'snapshots', f'{hoje}.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(snap, f, separators=(',', ':'))
    os.replace(tmp, _p(estado, 'snapshots', f'{hoje}.json'))

    dir_snap = _p(estado, 'snapshots')
    dias = sorted(x for x in os.listdir(dir_snap) if x.endswith('.json'))
    for velho in dias[:-DIAS_GUARDADOS]:
        os.remove(_p(dir_snap, velho))
    return len(novos), len(snap)
