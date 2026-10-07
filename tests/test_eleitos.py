#!/usr/bin/env python3
"""Quem foi eleito antes e quem e eleito agora.

Os testes de cruzamento usam candidaturas montadas aqui, porque a fixture de
2026 e de antes da eleicao e nao tem desfecho. Os de leitura usam a fatia real
de Roraima de 2018 e 2022, congelada em tests/fixtures/tse-rr.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import carregar as C   # noqa: E402
from pipeline import eleitos as EL   # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(AQUI, 'fixtures', 'tse-rr')


class ComSal(unittest.TestCase):
    """Todo teste daqui roda com uma CONTAS_SAL de teste, e devolve a de antes."""

    def setUp(self):
        self.antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        if self.antes is None:
            os.environ.pop('CONTAS_SAL', None)
        else:
            os.environ['CONTAS_SAL'] = self.antes
        shutil.rmtree(self.tmp, ignore_errors=True)


def cand(**kw):
    base = dict(uf='RR', ue='RR', cargo='6', ds_cargo='DEPUTADO FEDERAL', sq='1',
                nr='1010', nome='MARIA DA SILVA', urna='MARIA', cpf='',
                situacao='APTO', nr_partido='10', partido='PAB', nm_partido='',
                nr_fed='', fed='', comp_fed='', genero='FEMININO', cor_raca='',
                ocupacao='', nascimento='1970-01-01', sit_turno='')
    base.update(kw)
    return C.Cand(**base)


def zip_cand(caminho, ano, uf, linhas):
    """Um consulta_cand de mentira, com o cabecalho de verdade daquele ano."""
    cols = C.COLUNAS_CAND if ano >= 2022 else C.COLUNAS_CAND_2018
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', quoting=csv.QUOTE_ALL, lineterminator='\n')
    w.writerow(cols)
    for l in linhas:
        w.writerow([l.get(c, '#NULO') for c in cols])
    with zipfile.ZipFile(caminho, 'w') as z:
        z.writestr(f'consulta_cand_{ano}_{uf}.csv', buf.getvalue().encode('latin-1'))


def linha_csv(cargo, cpf, nome, urna, partido, sit, nasc='01/01/1970', uf='RR', sq='1'):
    return {'SG_UF': uf, 'SG_UE': uf, 'CD_CARGO': cargo, 'SQ_CANDIDATO': sq,
            'NM_CANDIDATO': nome, 'NM_URNA_CANDIDATO': urna,
            'NR_CPF_CANDIDATO': cpf, 'SG_PARTIDO': partido, 'DS_GENERO': 'FEMININO',
            'DT_NASCIMENTO': nasc, 'DS_SIT_TOT_TURNO': sit}


class TestLeituraDeAnoAntigo(unittest.TestCase):
    def test_2018_nao_tem_coluna_de_federacao(self):
        self.assertNotIn('NM_FEDERACAO', C.COLUNAS_CAND_2018)
        self.assertIn('DS_SIT_TOT_TURNO', C.COLUNAS_CAND_2018)

    def test_le_2018_sem_federacao(self):
        tmp = tempfile.mkdtemp()
        try:
            z = os.path.join(tmp, 'c.zip')
            zip_cand(z, 2018, 'RR', [linha_csv('5', '11144477735', 'ANA', 'ANA',
                                               'PSC', 'ELEITO')])
            cs = list(C.candidaturas(zipfile.ZipFile(z), 'RR', ano=2018))
            self.assertEqual(len(cs), 1)
            self.assertEqual(cs[0].fed, '')
            self.assertEqual(cs[0].nascimento, '1970-01-01')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_2026_continua_igual(self):
        zk = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand.zip'))
        self.assertTrue(next(C.candidaturas(zk, 'RR')).sq)


class TestChaves(ComSal):
    def test_cpf_vira_hmac_e_some(self):
        k = EL.chave_cpf('11144477735')
        self.assertTrue(k.startswith('p'))
        self.assertNotIn('11144477735', k)
        self.assertEqual(EL.chave_cpf(''), '')

    def test_chave_de_nome_ignora_acento_caixa_e_espaco(self):
        a = EL.chave_nasc('José  da Silva', '1970-01-01')
        b = EL.chave_nasc('JOSE DA SILVA', '1970-01-01')
        self.assertEqual(a, b)
        self.assertNotEqual(a, EL.chave_nasc('JOSE DA SILVA', '1970-01-02'))
        self.assertEqual(EL.chave_nasc('JOSE', ''), '')

    def test_a_marca_do_sal_muda_com_o_sal(self):
        m1 = EL.sal_marca()
        os.environ['CONTAS_SAL'] = 'outra-chave'
        self.assertNotEqual(m1, EL.sal_marca())


class TestAnteriores(ComSal):
    def test_guarda_so_eleito_nos_cargos_contados(self):
        cs = [cand(sit_turno='ELEITO', cpf='11144477735'),
              cand(sit_turno='SUPLENTE', cpf='22255588846'),
              cand(sit_turno='ELEITO', cargo='4', cpf='33366699957')]
        ls = EL.linhas_anteriores(cs, 2022)
        self.assertEqual(len(ls), 1)
        self.assertEqual(ls[0]['cargo'], '6')
        self.assertEqual(ls[0]['genero'], 'F')

    def test_2018_so_senado(self):
        cs = [cand(sit_turno='ELEITO', cargo='5', cpf='11144477735'),
              cand(sit_turno='ELEITO', cargo='6', cpf='22255588846')]
        self.assertEqual([l['cargo'] for l in EL.linhas_anteriores(cs, 2018)], ['5'])

    def test_gravar_e_ler(self):
        ls = EL.linhas_anteriores([cand(sit_turno='ELEITO', cpf='11144477735')], 2022)
        EL.gravar_anteriores(self.tmp, ls)
        lidas, motivo = EL.ler_anteriores(self.tmp)
        self.assertEqual((len(lidas), motivo), (1, ''))

    def test_ler_anteriores_sem_arquivo(self):
        self.assertEqual(EL.ler_anteriores(self.tmp), ([], 'falta'))

    def test_ler_anteriores_recusa_sal_diferente(self):
        EL.gravar_anteriores(self.tmp, [])
        os.environ['CONTAS_SAL'] = 'outra-chave'
        self.assertEqual(EL.ler_anteriores(self.tmp), ([], 'sal'))


class TestFerramentaAnteriores(ComSal):
    def _fontes(self):
        fontes = os.path.join(self.tmp, 'fontes')
        os.makedirs(fontes)
        zip_cand(os.path.join(fontes, 'consulta_cand_2022.zip'), 2022, 'RR', [
            linha_csv('6', '11144477735', 'ANA DE SOUZA', 'ANA', 'PSC', 'ELEITO POR QP'),
            linha_csv('6', '22255588846', 'BIA', 'BIA', 'PT', 'NÃO ELEITO', sq='2'),
        ])
        zip_cand(os.path.join(fontes, 'consulta_cand_2018.zip'), 2018, 'RR', [
            linha_csv('5', '33366699957', 'CIDA', 'CIDA', 'PTB', 'ELEITO', sq='3'),
            linha_csv('6', '44477700068', 'DORA', 'DORA', 'PT', 'ELEITO', sq='4'),
        ])
        return fontes

    def test_grava_sem_cpf_nem_nascimento(self):
        from ferramentas import anteriores
        est = os.path.join(self.tmp, 'estado')
        r = anteriores.main(['--estado', est, '--fonte-local', self._fontes(),
                             '--uf', 'RR', '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 0)
        texto = open(os.path.join(est, EL.ARQUIVO), encoding='utf-8').read()
        for cpf in ('11144477735', '33366699957'):
            self.assertNotIn(cpf, texto)
        self.assertNotIn('1970-01-01', texto)
        self.assertNotIn('01/01/1970', texto)
        linhas, motivo = EL.ler_anteriores(est)
        self.assertEqual(motivo, '')
        self.assertEqual(sorted((l['ano'], l['cargo']) for l in linhas),
                         [(2018, '5'), (2022, '6')])

    def test_sem_sal_para_sem_gravar(self):
        from ferramentas import anteriores
        os.environ.pop('CONTAS_SAL')
        est = os.path.join(self.tmp, 'estado')
        r = anteriores.main(['--estado', est, '--fonte-local', self._fontes(),
                             '--uf', 'RR', '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 1)
        self.assertFalse(os.path.exists(os.path.join(est, EL.ARQUIVO)))

    def test_congela_a_fatia_da_uf(self):
        from ferramentas import anteriores
        saida = os.path.join(self.tmp, 'fixture')
        anteriores.main(['--estado', os.path.join(self.tmp, 'e'), '--fonte-local',
                         self._fontes(), '--uf', 'RR', '--congelar', 'RR',
                         '--saida-fixture', saida, '--destino', os.path.join(self.tmp, 'd')])
        for ano in (2018, 2022):
            z = zipfile.ZipFile(os.path.join(saida, f'consulta_cand_{ano}.zip'))
            self.assertEqual(z.namelist(), [f'consulta_cand_{ano}_RR.csv'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
