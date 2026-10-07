#!/usr/bin/env python3
"""Os eleitos de 2018 (Senado) e de 2022 (todos os cargos contados).

Roda a mao no GitHub Actions, pelo workflow anteriores.yml, porque da maquina
local o CDN do TSE devolve 403. Os dois anos nao mudam: o arquivo e feito uma
vez e so precisa ser refeito se a CONTAS_SAL mudar.

    python -m ferramentas.anteriores --estado estado
    python -m ferramentas.anteriores --estado estado --congelar RR --saida-fixture fixture
"""
import argparse
import os
import re
import sys
import zipfile
from collections import Counter

from pipeline import carregar as C
from pipeline import eleitos as EL
from pipeline.baixar import baixar_fontes
from pipeline.ident import tem_sal_de_verdade

ANOS = (2018, 2022)


def ufs_do_zip(z, ano):
    """O arquivo BRASIL quando existe; senao, cada arquivo de UF."""
    try:
        C.membro_brasil(z, f'consulta_cand_{ano}')
        return [None]
    except C.LayoutMudou:
        padrao = re.compile(rf'consulta_cand_{ano}_([A-Z]{{2}})\.csv$')
        return sorted({m.group(1) for m in map(padrao.search, z.namelist()) if m})


def congelar(z, ano, uf, saida):
    os.makedirs(saida, exist_ok=True)
    membro = C.membro_uf(z, f'consulta_cand_{ano}', uf)
    alvo = os.path.join(saida, f'consulta_cand_{ano}.zip')
    with zipfile.ZipFile(alvo, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr(os.path.basename(membro), z.read(membro))
    print(f'   fixture: {alvo}, {os.path.getsize(alvo) / 1e6:.2f} MB')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--estado', default='estado')
    p.add_argument('--destino', default=os.environ.get('RUNNER_TEMP', 'tmp') + '/tse')
    p.add_argument('--fonte-local', default=None)
    p.add_argument('--uf', default='', help='so esta UF (teste)')
    p.add_argument('--congelar', default='', help='UF que vira fixture')
    p.add_argument('--saida-fixture', default='fixture')
    a = p.parse_args(argv)

    if not tem_sal_de_verdade():
        print('CONTAS_SAL nao esta no ambiente. Sem ela a chave de cada pessoa')
        print('seria reversivel, e o arquivo vai para uma branch publica.')
        print('Nada foi gravado.')
        return 1

    fontes = baixar_fontes(a.destino, a.fonte_local,
                           quais=[f'consulta_cand_{ano}' for ano in ANOS])
    linhas, vistas = [], set()
    for ano in ANOS:
        z = zipfile.ZipFile(fontes[f'consulta_cand_{ano}'][0])
        if a.congelar:
            congelar(z, ano, a.congelar, a.saida_fixture)
        ufs = [a.uf] if a.uf else ufs_do_zip(z, ano)
        doano, sem_cpf = [], 0
        for uf in ufs:
            for l in EL.linhas_anteriores(C.candidaturas(z, uf, ano=ano), ano):
                # a Presidencia pode aparecer em mais de um arquivo de UF
                k = (l['chave'] or l['chave_nasc'] or l['nome_urna'], ano,
                     l['cargo'], l['uf'])
                if k in vistas:
                    continue
                vistas.add(k)
                doano.append(l)
                sem_cpf += not l['chave']
        por_cargo = Counter(l['cargo'] for l in doano)
        print(f'{ano}: {len(doano)} eleitos, {sem_cpf} sem CPF no arquivo do TSE')
        for cargo, n in sorted(por_cargo.items()):
            print(f'   cargo {cargo}: {n}')
        linhas.extend(doano)
    caminho = EL.gravar_anteriores(a.estado, linhas)
    print(f'{len(linhas)} eleitos gravados em {caminho}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
