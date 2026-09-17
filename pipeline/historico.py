#!/usr/bin/env python3
"""O que a rodada de hoje precisa saber sobre as rodadas anteriores.

Sem isto, "fornecedor novo" e "salto no gasto" nao existem: sem ontem nao ha
novo. Dois arquivos, os dois append-only e pequenos:

- `fornecedores-vistos.txt`: um CNPJ ou CPF por linha, a primeira vez que
  apareceu. Cresce ate uns 420 mil, uns 6 MB.
- `snapshots/AAAA-MM-DD.json`: o total contratado por candidato naquele dia.
  Uns 600 KB por dia; guarda 30 dias e apaga o resto.
"""
import json
import os

DIAS_GUARDADOS = 30


def _p(estado, *partes):
    return os.path.join(estado, *partes)


def carregar(estado, hoje):
    """(fornecedores ja vistos, total de ontem por candidato, dia de ontem)."""
    vistos = set()
    caminho = _p(estado, 'fornecedores-vistos.txt')
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as f:
            for linha in f:
                d = linha.strip()
                if d:
                    vistos.add(d)

    dir_snap = _p(estado, 'snapshots')
    anterior, dia = {}, ''
    if os.path.isdir(dir_snap):
        dias = sorted(x[:-5] for x in os.listdir(dir_snap) if x.endswith('.json'))
        dias = [d for d in dias if d < hoje]
        if dias:
            dia = dias[-1]
            with open(_p(dir_snap, f'{dia}.json'), encoding='utf-8') as f:
                anterior = json.load(f)
    return vistos, anterior, dia


def gravar(estado, hoje, nac, aggs):
    """Acrescenta os fornecedores novos e grava o retrato de hoje."""
    os.makedirs(_p(estado, 'snapshots'), exist_ok=True)
    caminho = _p(estado, 'fornecedores-vistos.txt')
    vistos = set()
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as f:
            vistos = {l.strip() for l in f if l.strip()}
    novos = [d for d in nac.fornecedores if d not in vistos]
    if novos:
        with open(caminho, 'a', encoding='utf-8') as f:
            f.write('\n'.join(sorted(novos)) + '\n')

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
