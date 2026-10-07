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
import secrets
import sys
import zipfile
from collections import Counter

from ferramentas.anonimizar import anonimizar_csv
from pipeline import carregar as C
from pipeline import eleitos as EL
from pipeline.baixar import baixar_fontes
from pipeline.ident import tem_sal_de_verdade
from pipeline.validar import confere_cadeiras

ANOS = (2018, 2022)


def ufs_do_zip(z, ano):
    """O arquivo BRASIL quando existe; senao, cada arquivo de UF."""
    try:
        C.membro_brasil(z, f'consulta_cand_{ano}')
        return [None]
    except C.LayoutMudou:
        padrao = re.compile(rf'consulta_cand_{ano}_([A-Z]{{2}})\.csv$')
        return sorted({m.group(1) for m in map(padrao.search, z.namelist()) if m})


def congelar(z, ano, uf, saida, chave):
    """A fatia da UF, anonimizada, no nome que a fixture usa: consulta_cand.zip
    para 2026 e consulta_cand_<ano>.zip para os anos de antes. A chave e a mesma
    nos tres anos, para o mesmo CPF virar o mesmo falso em todos."""
    os.makedirs(saida, exist_ok=True)
    membro = C.membro_uf(z, f'consulta_cand_{ano}', uf)
    nome = 'consulta_cand.zip' if ano == 2026 else f'consulta_cand_{ano}.zip'
    alvo = os.path.join(saida, nome)
    texto = anonimizar_csv(z.read(membro).decode('latin-1'), chave)
    with zipfile.ZipFile(alvo, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr(os.path.basename(membro), texto.encode('latin-1'))
    print(f'   fixture: {alvo}, {os.path.getsize(alvo) / 1e6:.2f} MB')


def _conta(n, um, varios):
    return f'{n} {um if n == 1 else varios}'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--estado', default='estado')
    p.add_argument('--destino', default=os.environ.get('RUNNER_TEMP', 'tmp') + '/tse')
    p.add_argument('--fonte-local', default=None)
    p.add_argument('--uf', default='', help='so esta UF (teste)')
    p.add_argument('--congelar', default='',
                   help='UF que vira fixture anonimizada (2018, 2022 e 2026)')
    p.add_argument('--saida-fixture', default='fixture')
    a = p.parse_args(argv)

    if not tem_sal_de_verdade():
        print('CONTAS_SAL nao esta no ambiente. Sem ela a chave de cada pessoa')
        print('seria reversivel, e o arquivo vai para uma branch publica.')
        print('Nada foi gravado.')
        return 1

    # A fixture leva tambem o 2026 da mesma UF, anonimizado com a mesma chave, para
    # a ligacao entre os tres anos continuar de pe nela. A rodada sem --congelar
    # nao baixa o 2026, que ela nao le.
    quais = [f'consulta_cand_{ano}' for ano in ANOS]
    if a.congelar:
        quais.append('consulta_cand')
    fontes = baixar_fontes(a.destino, a.fonte_local, quais=quais)
    # aleatoria, so na memoria desta execucao: nunca e gravada nem impressa
    chave = secrets.token_bytes(32) if a.congelar else None
    if a.congelar:
        congelar(zipfile.ZipFile(fontes['consulta_cand'][0]), 2026, a.congelar,
                 a.saida_fixture, chave)
    linhas, vistas = [], set()
    for ano in ANOS:
        z = zipfile.ZipFile(fontes[f'consulta_cand_{ano}'][0])
        if a.congelar:
            congelar(z, ano, a.congelar, a.saida_fixture, chave)
        ufs = [a.uf] if a.uf else ufs_do_zip(z, ano)
        doano, sem_cpf = [], 0
        for uf in ufs:
            for l in EL.linhas_anteriores(C.candidaturas(z, uf, ano=ano), ano):
                # a Presidencia pode aparecer em mais de um arquivo de UF
                k = (l['chave'] or l['chave_nasc'] or l['nome_urna'], ano,
                     l['cargo'], l['uf'], l['suplementar'])
                if k in vistas:
                    continue
                vistas.add(k)
                doano.append(l)
                sem_cpf += not l['chave'] and not l['suplementar']
        ordinaria = [l for l in doano if not l['suplementar']]
        print(f'{ano}: {_conta(len(ordinaria), "eleito", "eleitos")}, '
              f'{sem_cpf} sem CPF no arquivo do TSE')
        for cargo, n in sorted(Counter(l['cargo'] for l in ordinaria).items()):
            print(f'   cargo {cargo}: {n}')
        # a suplementar fica guardada para a tela contar as cadeiras, e fora da
        # conferencia de cadeiras e do "eleito antes"
        sup = Counter(l['cargo'] for l in doano if l['suplementar'])
        if sup:
            print(f'{ano}: ' + _conta(sum(sup.values()),
                                      'linha de eleição suplementar guardada à parte',
                                      'linhas de eleição suplementar guardadas à parte'))
            for cargo, n in sorted(sup.items()):
                print(f'   cargo {cargo}: {n} de suplementar')
        linhas.extend(doano)
    # Sem --uf, a ferramenta leu o pais inteiro, e a contagem da eleicao ordinaria
    # tem de bater com as cadeiras. Um arquivo errado na branch dados tiraria a
    # aba de toda rodada.
    if not a.uf:
        contagem = {}
        for l in linhas:
            if l['suplementar']:
                continue
            doano = contagem.setdefault(str(l['ano']), {})
            doano[l['cargo']] = doano.get(l['cargo'], 0) + 1
        erros = confere_cadeiras(contagem)
        if erros:
            print('A contagem nao bate com as cadeiras. Nada foi gravado.')
            for e in erros:
                print(f'   {e}')
            return 1
    caminho = EL.gravar_anteriores(a.estado, linhas)
    print(f'{_conta(len(linhas), "linha gravada", "linhas gravadas")} em {caminho}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
