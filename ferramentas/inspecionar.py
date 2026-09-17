#!/usr/bin/env python3
"""Abre os zips do TSE e descreve o que tem dentro, sem supor nada.

Existe por dois motivos. O primeiro e de partida: o layout de 2026 precisa ser
lido, nao herdado de 2022. O segundo e permanente: rodar isto quando o
validador reclamar diz, em um minuto, se o TSE mudou o arquivo.

Uso:
    python -m ferramentas.inspecionar [--fonte-local DIR] [--linhas 3]
"""
import argparse
import csv
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.baixar import baixar_fontes  # noqa: E402


def _texto(z, membro, encoding='latin-1'):
    return io.TextIOWrapper(z.open(membro), encoding=encoding, newline='')


def descreve_csv(z, membro, amostra=3):
    """Cabecalho, contagem de linhas e primeiras linhas de um membro CSV."""
    print(f'\n  --- {membro}')
    try:
        with _texto(z, membro) as f:
            leitor = csv.reader(f, delimiter=';')
            try:
                cab = next(leitor)
            except StopIteration:
                print('      (vazio)')
                return None
            cab = [c.lstrip('﻿').strip('"') for c in cab]
            print(f'      {len(cab)} colunas')
            for i in range(0, len(cab), 4):
                print('      ' + ' | '.join(f'{j + i}:{c}' for j, c in enumerate(cab[i:i + 4])))
            linhas = []
            n = 0
            for linha in leitor:
                n += 1
                if len(linhas) < amostra:
                    linhas.append(linha)
            print(f'      {n} linhas de dados')
            for linha in linhas:
                pares = [f'{c}={v!r}' for c, v in zip(cab, linha) if v not in ('', '#NULO#', '-1', '#NULO')]
                print(f'      . {"; ".join(pares[:14])}')
            return {'colunas': cab, 'linhas': n}
    except Exception as e:  # noqa: BLE001
        print(f'      ERRO ao ler: {type(e).__name__}: {e}')
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fonte-local', default=None)
    p.add_argument('--destino', default=os.environ.get('RUNNER_TEMP', 'tmp') + '/tse')
    p.add_argument('--linhas', type=int, default=3)
    p.add_argument('--quais', default='candidatos,consulta_cand,orgaos,cnpj_campanha')
    a = p.parse_args(argv)

    quais = [q.strip() for q in a.quais.split(',') if q.strip()]
    print('baixando:', ', '.join(quais))
    fontes = baixar_fontes(a.destino, a.fonte_local, quais=quais)

    resumo = {}
    for nome, (caminho, lm) in fontes.items():
        tam = os.path.getsize(caminho)
        print('\n' + '=' * 72)
        print(f'{nome}: {tam / 1e6:.2f} MB  last-modified={lm}')
        print('=' * 72)
        with zipfile.ZipFile(caminho) as z:
            infos = sorted(z.infolist(), key=lambda i: -i.file_size)
            print(f'{len(infos)} membros:')
            for i in infos[:40]:
                print(f'   {i.file_size / 1e6:9.3f} MB  {i.filename}')
            if len(infos) > 40:
                print(f'   ... e mais {len(infos) - 40}')
            # descreve o maior CSV de cada prefixo distinto
            vistos = set()
            for i in infos:
                if not i.filename.lower().endswith('.csv'):
                    continue
                base = i.filename.rsplit('_', 1)[0]
                if base in vistos:
                    continue
                vistos.add(base)
                r = descreve_csv(z, i.filename, a.linhas)
                if r:
                    resumo[f'{nome}:{i.filename}'] = r
                if len(vistos) >= 8:
                    break
            for i in infos:
                if i.filename.lower().endswith('.txt') and i.file_size < 50e6:
                    r = descreve_csv(z, i.filename, a.linhas)
                    if r:
                        resumo[f'{nome}:{i.filename}'] = r
                    break

    print('\n' + '=' * 72)
    print('RESUMO')
    for k, v in resumo.items():
        print(f'  {k}: {v["linhas"]} linhas, {len(v["colunas"])} colunas')
    return 0


if __name__ == '__main__':
    sys.exit(main())
