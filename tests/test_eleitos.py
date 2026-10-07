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
from pipeline import escrever as E   # noqa: E402
from pipeline import validar as V    # noqa: E402

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

    def test_eleicao_suplementar_nao_conta(self):
        cs = [cand(sit_turno='ELEITO', cargo='3', tipo_eleicao='1', cpf='11144477735'),
              cand(sit_turno='ELEITO', cargo='6', tipo_eleicao='2', cpf='22255588846'),
              cand(sit_turno='ELEITO', cargo='7', cpf='33366699957')]
        ls = EL.linhas_anteriores(cs, 2022)
        self.assertEqual(sorted(l['cargo'] for l in ls), ['6', '7'])

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

    def test_ler_anteriores_truncado_e_corrompido(self):
        ls = EL.linhas_anteriores([cand(sit_turno='ELEITO', cpf='11144477735')], 2022)
        caminho = EL.gravar_anteriores(self.tmp, ls)
        texto = open(caminho, encoding='utf-8').read()
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(texto[:len(texto) // 2])
        self.assertEqual(EL.ler_anteriores(self.tmp), ([], 'corrompido'))

    def test_ler_anteriores_que_nao_e_objeto_e_corrompido(self):
        with open(os.path.join(self.tmp, EL.ARQUIVO), 'w', encoding='utf-8') as f:
            f.write('[1, 2]')
        self.assertEqual(EL.ler_anteriores(self.tmp), ([], 'corrompido'))


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

    def test_pais_inteiro_com_contagem_fora_da_margem_nao_grava(self):
        # sem --uf a ferramenta le o pais inteiro, e a contagem tem de bater com as
        # cadeiras: um arquivo errado na branch dados congelaria a aba de toda rodada
        from ferramentas import anteriores
        est = os.path.join(self.tmp, 'estado')
        saida = io.StringIO()
        from unittest import mock
        with mock.patch('sys.stdout', saida):
            r = anteriores.main(['--estado', est, '--fonte-local', self._fontes(),
                                 '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 1)
        self.assertFalse(os.path.exists(os.path.join(est, EL.ARQUIVO)))
        self.assertIn('esperado perto de 513', saida.getvalue())

    def test_congela_a_fatia_da_uf(self):
        from ferramentas import anteriores
        saida = os.path.join(self.tmp, 'fixture')
        anteriores.main(['--estado', os.path.join(self.tmp, 'e'), '--fonte-local',
                         self._fontes(), '--uf', 'RR', '--congelar', 'RR',
                         '--saida-fixture', saida, '--destino', os.path.join(self.tmp, 'd')])
        for ano in (2018, 2022):
            z = zipfile.ZipFile(os.path.join(saida, f'consulta_cand_{ano}.zip'))
            self.assertEqual(z.namelist(), [f'consulta_cand_{ano}_RR.csv'])


def antes(cpf='11144477735', ano=2022, cargo='6', uf='RR', partido='PAB',
          nome='MARIA DA SILVA', nasc='1970-01-01'):
    return {'chave': EL.chave_cpf(cpf), 'chave_nasc': EL.chave_nasc(nome, nasc),
            'ano': ano, 'cargo': cargo, 'uf': uf, 'partido': partido,
            'nome_urna': nome.split()[0], 'genero': 'F'}


class TestSucessao(unittest.TestCase):
    def test_transitiva_e_sem_laco(self):
        t = {'A': 'B', 'B': 'C', 'X': 'Y', 'Y': 'X'}
        self.assertEqual(EL.sucessor('A', t), 'C')
        self.assertEqual(EL.sucessor('Z', t), 'Z')
        self.assertIn(EL.sucessor('X', t), ('X', 'Y'))

    def test_le_o_csv(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, 's.csv')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('antigo,sucessor,data,ato\nPSC,PODE,2023-06-13,ato\n')
            self.assertEqual(EL.carregar_sucessao(p), {'PSC': 'PODE'})
            self.assertEqual(EL.carregar_sucessao(os.path.join(tmp, 'nao')), {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestVenceTurno(unittest.TestCase):
    """Uma regra so de qual linha de turno vence, em desfecho.py, usada por
    agregar.juntar_candidaturas e por eleitos.cruzar."""

    def test_turno_mais_alto_com_resultado_vence(self):
        self.assertTrue(EL.D.vence_turno(2, 'NÃO ELEITO', 1, '2º TURNO'))
        self.assertFalse(EL.D.vence_turno(1, '2º TURNO', 2, 'NÃO ELEITO'))

    def test_empate_a_ultima_linha_com_resultado_vence(self):
        self.assertTrue(EL.D.vence_turno(1, 'ELEITO', 1, 'SUPLENTE'))

    def test_linha_sem_resultado_nunca_apaga_uma_com_resultado(self):
        self.assertFalse(EL.D.vence_turno(2, '', 1, 'ELEITO'))
        self.assertTrue(EL.D.vence_turno(1, 'ELEITO', 2, ''))

    def test_entre_duas_sem_resultado_vale_o_turno_mais_alto(self):
        self.assertTrue(EL.D.vence_turno(2, '', 1, ''))
        self.assertFalse(EL.D.vence_turno(1, '', 2, ''))

    def test_agregar_e_eleitos_usam_a_mesma_regra(self):
        from pipeline import agregar as A
        self.assertFalse(hasattr(EL, '_vence_turno'))
        self.assertFalse(hasattr(EL, '_turno'))
        self.assertIs(A.numero_turno, EL.D.numero_turno)


class TestCruzamento(ComSal):
    def um(self, anteriores, cands, suc=None):
        pessoas, est = EL.cruzar(anteriores, cands, suc or {})
        return pessoas, est

    def test_reeleita_no_mesmo_cargo(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', sit_turno='ELEITO', sq='9')])
        self.assertEqual(len(ps), 1)
        p = ps[0]
        self.assertEqual((p['destino'], p['ano_antes'], p['sq'], p['mudou']),
                         (EL.MESMO_CARGO, 2022, '9', 0))

    def test_mesmo_cargo_em_outra_uf_e_outro_destino(self):
        ps, _ = self.um([antes(uf='AM')], [cand(cpf='11144477735', sit_turno='ELEITO')])
        self.assertEqual(ps[0]['destino'], EL.OUTRO_CARGO)

    def test_eleita_para_outro_cargo(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='5', sit_turno='ELEITO')])
        self.assertEqual((ps[0]['destino'], ps[0]['cargo_agora']), (EL.OUTRO_CARGO, '5'))

    def test_segundo_turno(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='3', sit_turno='2º TURNO')])
        self.assertEqual(ps[0]['destino'], EL.SEGUNDO_TURNO)

    def test_vice(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='4', sit_turno='ELEITO')])
        self.assertEqual(ps[0]['destino'], EL.VICE)

    def test_concorreu_e_nao_se_elegeu_inclui_suplente(self):
        for sit in ('SUPLENTE', 'NÃO ELEITO'):
            ps, _ = self.um([antes()], [cand(cpf='11144477735', sit_turno=sit)])
            self.assertEqual(ps[0]['destino'], EL.NAO_ELEITA, sit)

    def test_sem_resultado_publicado_nao_e_nao_eleita(self):
        # renuncia, indeferimento, sub judice ou totalizacao que ainda nao chegou:
        # o dado nao diz que a pessoa concorreu e perdeu
        for sit in ('#NULO', ''):
            ps, _ = self.um([antes()], [cand(cpf='11144477735', sit_turno=sit)])
            self.assertEqual(ps[0]['destino'], EL.SEM_RESULTADO, repr(sit))
        self.assertEqual(EL.SEM_RESULTADO, 7)

    def test_candidatura_com_resultado_vence_a_sem_resultado(self):
        for ordem in (('', 'NÃO ELEITO'), ('NÃO ELEITO', '')):
            ps, _ = self.um([antes()], [
                cand(cpf='11144477735', sit_turno=ordem[0], sq='1'),
                cand(cpf='11144477735', cargo='7', sit_turno=ordem[1], sq='2')])
            self.assertEqual(len(ps), 1)
            self.assertEqual(ps[0]['destino'], EL.NAO_ELEITA, ordem)
            self.assertEqual(ps[0]['desfecho'], EL.D.NAO_ELEITA, ordem)

    def test_vice_continua_vice_sem_resultado(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='4', sit_turno='')])
        self.assertEqual(ps[0]['destino'], EL.VICE)

    def test_sem_candidatura(self):
        ps, _ = self.um([antes()], [])
        p = ps[0]
        self.assertEqual((p['destino'], p['sq'], p['cargo_agora']), (EL.SEM_CANDIDATURA, '', ''))

    def test_novata_eleita_entra_e_nao_eleita_nao(self):
        ps, _ = self.um([], [cand(cpf='22255588846', sit_turno='ELEITO', sq='1'),
                             cand(cpf='33366699957', sit_turno='NÃO ELEITO', sq='2')])
        self.assertEqual([(p['sq'], p['destino'], p['ano_antes']) for p in ps], [('1', 0, 0)])

    def test_mudanca_por_sucessao_nao_conta(self):
        ps, _ = self.um([antes(partido='PSC')],
                        [cand(cpf='11144477735', partido='PODE', sit_turno='ELEITO')],
                        {'PSC': 'PODE'})
        self.assertEqual(ps[0]['mudou'], 0)

    def test_mudanca_sem_sucessao_conta(self):
        ps, _ = self.um([antes(partido='PSC')],
                        [cand(cpf='11144477735', partido='PT', sit_turno='ELEITO')],
                        {'PSC': 'PODE'})
        self.assertEqual(ps[0]['mudou'], 1)

    def test_liga_pelo_nome_e_nascimento_quando_falta_cpf(self):
        ps, est = self.um([antes(cpf='', nome='José da Silva')],
                          [cand(cpf='11144477735', nome='JOSE DA SILVA', sit_turno='ELEITO')])
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0]['destino'], EL.MESMO_CARGO)
        self.assertEqual(est['ligados_por_nome'], 1)

    def test_candidatura_dupla_vira_uma_linha(self):
        ps, _ = self.um([antes()], [
            cand(cpf='11144477735', sit_turno='NÃO ELEITO', sq='1'),
            cand(cpf='11144477735', cargo='5', sit_turno='ELEITO', sq='2')])
        self.assertEqual([(p['sq'], p['destino']) for p in ps], [('2', EL.OUTRO_CARGO)])

    def test_2022_vence_2018_para_a_mesma_pessoa(self):
        ps, est = self.um([antes(ano=2018, cargo='5'), antes(ano=2022, cargo='3')], [])
        self.assertEqual([(p['ano_antes'], p['cargo_antes']) for p in ps], [(2022, '3')])
        # a contagem bruta continua com as duas eleicoes
        self.assertEqual(est['anteriores'], {'2018': {'5': 1}, '2022': {'3': 1}})

    def test_sigla_sem_par_e_avisada(self):
        _, est = self.um([antes(partido='PSC'), antes(cpf='22255588846', partido='PTB')],
                         [cand(cpf='33366699957', partido='PODE', sit_turno='ELEITO')],
                         {'PSC': 'PODE'})
        self.assertEqual(est['siglas_sem_par'], ['PTB'])

    def test_filtro_de_uf(self):
        ps, _ = EL.cruzar([antes(uf='AM'), antes(cpf='22255588846')], [], {}, ufs=['RR'])
        self.assertEqual([p['uf_antes'] for p in ps], ['RR'])

    def test_federacao_de_2026(self):
        _, est = self.um([], [cand(cpf='22255588846', partido='PT', fed='FEDERAÇÃO BRASIL DA ESPERANÇA', sit_turno='ELEITO')])
        self.assertEqual(est['fed'], {'PT': 'FEDERAÇÃO BRASIL DA ESPERANÇA'})

    def test_mesma_pessoa_com_e_sem_cpf_vira_uma_linha(self):
        ps, est = self.um([antes(ano=2022, cpf='11144477735', nome='MARIA DA SILVA'),
                           antes(ano=2018, cpf='', nome='MARIA DA SILVA')],
                          [cand(cpf='11144477735', sit_turno='ELEITO', sq='9')])
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0]['sq'], '9')
        self.assertEqual(est['anteriores'], {'2022': {'6': 1}, '2018': {'6': 1}})

    def test_registro_com_cpf_acha_candidatura_sem_cpf(self):
        ps, est = self.um([antes(cpf='11144477735', nome='MARIA DA SILVA')],
                          [cand(cpf='', nome='MARIA DA SILVA', sit_turno='ELEITO')])
        self.assertEqual(len(ps), 1)
        self.assertEqual((ps[0]['destino'], est['ligados_por_nome']), (EL.MESMO_CARGO, 1))

    def test_partido_antes_vazio_nao_e_mudanca(self):
        ps, _ = self.um([antes(partido='')],
                        [cand(cpf='11144477735', partido='PT', sit_turno='ELEITO')])
        self.assertEqual(ps[0]['mudou'], 0)

    def test_sem_cpf_e_sem_nascimento_continua_na_lista(self):
        ps, _ = self.um([antes(cpf='', nasc='')], [])
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0]['destino'], EL.SEM_CANDIDATURA)

    def test_sem_cpf_junta_2018_e_2022_pela_chave_de_nome(self):
        ps, _ = self.um([antes(ano=2018, cpf='', cargo='5', nasc='1970-01-01'),
                         antes(ano=2022, cpf='', cargo='3', nasc='1970-01-01')], [])
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0]['ano_antes'], 2022)

    def test_perdeu_no_segundo_turno_nas_duas_ordens(self):
        # o consulta_cand tem uma linha por turno, e a do turno 2 as vezes vem antes
        t1 = cand(cpf='11144477735', cargo='3', sit_turno='2º TURNO', sq='9', turno='1')
        t2 = cand(cpf='11144477735', cargo='3', sit_turno='NÃO ELEITO', sq='9', turno='2')
        for ordem in ([t1, t2], [t2, t1]):
            ps, _ = self.um([antes(cargo='3')], ordem)
            self.assertEqual(len(ps), 1)
            self.assertEqual((ps[0]['destino'], ps[0]['desfecho']),
                             (EL.NAO_ELEITA, EL.D.NAO_ELEITA))

    def test_eleita_no_segundo_turno_nas_duas_ordens(self):
        t1 = cand(cpf='11144477735', cargo='3', sit_turno='2º TURNO', sq='9', turno='1')
        t2 = cand(cpf='11144477735', cargo='3', sit_turno='ELEITO', sq='9', turno='2')
        for ordem in ([t1, t2], [t2, t1]):
            ps, _ = self.um([antes(cargo='3')], ordem)
            self.assertEqual((ps[0]['destino'], ps[0]['desfecho']),
                             (EL.MESMO_CARGO, EL.D.ELEITA))

    def test_novata_que_perdeu_no_segundo_turno_sai(self):
        t1 = cand(cpf='22255588846', cargo='3', sit_turno='2º TURNO', sq='9', turno='1')
        t2 = cand(cpf='22255588846', cargo='3', sit_turno='NÃO ELEITO', sq='9', turno='2')
        for ordem in ([t1, t2], [t2, t1]):
            ps, _ = self.um([], ordem)
            self.assertEqual(ps, [])

    def test_senador_de_2018_absorvido_por_2022_e_contado_por_uf(self):
        _, est = self.um([antes(ano=2018, cargo='5', uf='SC'),
                          antes(ano=2022, cargo='3', uf='SC'),
                          antes(cpf='22255588846', ano=2018, cargo='5', uf='SC',
                                nome='ANA LIMA'),
                          antes(cpf='33366699957', ano=2022, cargo='3', uf='AM',
                                nome='BIA LIMA'),
                          antes(cpf='33366699957', ano=2018, cargo='5', uf='AM',
                                nome='BIA LIMA')], [])
        self.assertEqual(est['absorvidos'], {'SC': 1, 'AM': 1})

    def test_sem_absorvido_da_dicionario_vazio(self):
        _, est = self.um([antes(ano=2018, cargo='5')], [])
        self.assertEqual(est['absorvidos'], {})

    def test_absorvido_sem_cpf_pela_chave_de_nome(self):
        _, est = self.um([antes(ano=2018, cpf='', cargo='5', uf='SC'),
                          antes(ano=2022, cpf='11144477735', cargo='3', uf='SC')], [])
        self.assertEqual(est['absorvidos'], {'SC': 1})

    def test_cpf_diferente_nos_dois_lados_nao_liga_pelo_nome(self):
        ps, est = self.um([antes(cpf='11144477735', nome='MARIA DA SILVA')],
                          [cand(cpf='22255588846', nome='MARIA DA SILVA',
                                sit_turno='ELEITO', sq='9')])
        self.assertEqual(est['ligados_por_nome'], 0)
        por_sq = {p['sq']: p for p in ps}
        self.assertEqual(por_sq['']['destino'], EL.SEM_CANDIDATURA)
        self.assertEqual(por_sq['9']['ano_antes'], 0)

    def test_cpf_que_nao_casa_liga_pelo_nome_a_candidatura_sem_cpf(self):
        ps, est = self.um([antes(cpf='11144477735', nome='MARIA DA SILVA')],
                          [cand(cpf='', nome='MARIA DA SILVA', sit_turno='ELEITO', sq='9'),
                           cand(cpf='22255588846', nome='OUTRA', sit_turno='ELEITO', sq='8')])
        self.assertEqual(est['ligados_por_nome'], 1)
        por_sq = {p['sq']: p for p in ps}
        self.assertEqual(por_sq['9']['destino'], EL.MESMO_CARGO)

    def test_cpf_exato_vence_ligacao_pelo_nome_em_qualquer_ordem(self):
        pelo_nome = antes(cpf='', nome='MARIA DA SILVA', cargo='7')
        exato = antes(cpf='11144477735', nome='MARIA S', nasc='1980-02-02')
        c = cand(cpf='11144477735', nome='MARIA DA SILVA', sit_turno='ELEITO', sq='9')
        for ordem in ([pelo_nome, exato], [exato, pelo_nome]):
            ps, est = self.um(ordem, [c])
            ligado = [p for p in ps if p['sq'] == '9']
            self.assertEqual(len(ligado), 1)
            self.assertEqual(ligado[0]['cargo_antes'], '6')
            self.assertEqual(est['ligados_por_nome'], 0)

    def test_duas_pessoas_de_antes_nunca_ligam_a_mesma_candidatura(self):
        ps, est = self.um([antes(cpf='11144477735', nome='MARIA DA SILVA'),
                           antes(cpf='22255588846', nome='MARIA DA SILVA')],
                          [cand(cpf='', nome='MARIA DA SILVA', sit_turno='ELEITO', sq='9')])
        sqs = [p['sq'] for p in ps]
        self.assertEqual(sqs.count('9'), 1)
        self.assertEqual(est['ligados_por_nome'], 1)


def linha_ok(**kw):
    base = dict(nome='MARIA', uf_a='RR', cargo_a='6', part_a=0, ano_a=2022, destino=1,
                uf_g='RR', cargo_g='6', part_g=0, desf=1, sq='9', gen='F', mudou=0)
    base.update(kw)
    return [base[k] for k in ('nome', 'uf_a', 'cargo_a', 'part_a', 'ano_a', 'destino',
                              'uf_g', 'cargo_g', 'part_g', 'desf', 'sq', 'gen', 'mudou')]


class TestEscritaEValidacao(ComSal):
    def test_escreve_linhas_de_13_campos_com_indice_de_partido(self):
        ps, est = EL.cruzar([antes(partido='PSC')],
                            [cand(cpf='11144477735', partido='PODE', sit_turno='ELEITO', sq='9'),
                             cand(cpf='22255588846', partido='PT', fed='FED X', sit_turno='ELEITO', sq='8')],
                            {'PSC': 'PODE'})
        dics = {k: E.Dic() for k in ('partido', 'fed')}
        E.escrever_eleitos(ps, est, dics, self.tmp)
        d = json.load(open(os.path.join(self.tmp, 'eleitos', 'BRASIL.json'), encoding='utf-8'))
        self.assertTrue(all(len(l) == 13 for l in d['c']))
        por_sq = {l[10]: l for l in d['c']}
        self.assertEqual(dics['partido'].lista[por_sq['9'][3]], 'PSC')
        self.assertEqual(dics['partido'].lista[por_sq['9'][8]], 'PODE')
        self.assertEqual(por_sq['8'][3], -1)
        self.assertEqual(d['fed'], {str(dics['partido'].idx['PT']): dics['fed'].idx['FED X']})
        self.assertEqual(V._checar_eleitos(d, len(dics['partido'].lista),
                                           len(dics['fed'].lista), False), [])

    def test_sem_ficha_o_sq_fica_vazio(self):
        ps, est = EL.cruzar([antes()],
                            [cand(cpf='11144477735', sit_turno='ELEITO', sq='9'),
                             cand(cpf='22255588846', sit_turno='ELEITO', sq='8',
                                  nome='ANA', urna='ANA')], {})
        dics = {k: E.Dic() for k in ('partido', 'fed')}
        E.escrever_eleitos(ps, est, dics, self.tmp, com_ficha={'9'})
        d = json.load(open(os.path.join(self.tmp, 'eleitos', 'BRASIL.json'), encoding='utf-8'))
        self.assertEqual(sorted(l[10] for l in d['c']), ['', '9'])
        self.assertEqual(V._checar_eleitos(d, len(dics['partido'].lista),
                                           len(dics['fed'].lista), False), [])

    def test_absorvidos_vao_para_o_arquivo_e_o_validador_confere(self):
        ps, est = EL.cruzar([antes(ano=2018, cargo='5', uf='SC'),
                             antes(ano=2022, cargo='3', uf='SC')], [], {})
        dics = {k: E.Dic() for k in ('partido', 'fed')}
        E.escrever_eleitos(ps, est, dics, self.tmp)
        d = json.load(open(os.path.join(self.tmp, 'eleitos', 'BRASIL.json'), encoding='utf-8'))
        self.assertEqual(d['absorvidos'], {'SC': 1})
        n_p = len(dics['partido'].lista)
        self.assertEqual(V._checar_eleitos(d, n_p, 0, False), [])
        for ruim in ({'SCX': 1}, {'SC': 0}, {'SC': '1'}, {'SC': True}, ['SC']):
            erros = V._checar_eleitos(dict(d, absorvidos=ruim), n_p, 0, False)
            self.assertTrue(erros and 'absorvidos' in erros[0], (ruim, erros))

    def test_validador_reprova_forma(self):
        for ruim, trecho in ((linha_ok()[:12], '13'),
                             (linha_ok(destino=8), 'destino'),
                             (linha_ok(ano_a=0), 'destino'),
                             (linha_ok(part_g=5), 'partido'),
                             (linha_ok(desf=5), 'desfecho'),
                             (linha_ok(cargo_a='9'), 'cargo')):
            erros = V._checar_eleitos({'c': [ruim]}, 1, 0, False)
            self.assertTrue(erros and trecho in erros[0], (ruim, erros))

    def test_validador_aceita_sem_resultado(self):
        linha = linha_ok(destino=7, desf=0)
        self.assertEqual(V._checar_eleitos({'c': [linha]}, 1, 0, False), [])

    def test_validador_reprova_sq_repetido(self):
        erros = V._checar_eleitos({'c': [linha_ok(), linha_ok()]}, 1, 0, False)
        self.assertTrue(any('repetido' in e for e in erros))

    def test_confere_cadeiras_aceita_a_contagem_real_e_reprova_400_deputados(self):
        cheio = {'2022': {'1': 1, '3': 27, '5': 27, '6': 513, '7': 1035, '8': 24},
                 '2018': {'5': 54}}
        self.assertEqual(V.confere_cadeiras(cheio), [])
        # ate 2 % abaixo passa: cassacao, eleicao anulada
        self.assertEqual(V.confere_cadeiras(dict(cheio, **{'2022': dict(cheio['2022'], **{'6': 503})})), [])
        erros = V.confere_cadeiras(dict(cheio, **{'2022': dict(cheio['2022'], **{'6': 400})}))
        self.assertEqual(len(erros), 1)
        self.assertIn('400', erros[0])
        self.assertIn('513', erros[0])

    def test_rodada_do_pais_com_cadeiras_erradas_nao_grava_eleitos(self):
        from unittest import mock
        from pipeline import rodar
        import argparse
        import time
        est = os.path.join(self.tmp, 'estado')
        EL.gravar_anteriores(est, [antes()])
        a = argparse.Namespace(estado=est, dados=os.path.join(self.tmp, 'sem-dados'),
                               site=os.path.join(self.tmp, 'site'))
        dics = {k: E.Dic() for k in ('partido', 'fed')}
        saida = io.StringIO()
        with mock.patch('sys.stdout', saida):
            r = rodar._eleitos(a, [cand(cpf='11144477735', sit_turno='ELEITO', sq='9')],
                               dics, [], None, time.time(), completo=True)
        self.assertIsNone(r)
        self.assertFalse(os.path.exists(os.path.join(a.site, 'eleitos', 'BRASIL.json')))
        self.assertIn('::warning::', saida.getvalue())
        self.assertIn('esperado perto de 513', saida.getvalue())
        # a mesma rodada numa UF so nao confere cadeiras, e grava
        with mock.patch('sys.stdout', io.StringIO()):
            r = rodar._eleitos(a, [cand(cpf='11144477735', sit_turno='ELEITO', sq='9')],
                               dics, ['RR'], None, time.time(), completo=False)
        self.assertIsNotNone(r)
        self.assertTrue(os.path.exists(os.path.join(a.site, 'eleitos', 'BRASIL.json')))

    def test_cadeiras_so_no_pais_inteiro(self):
        cheio = {'2022': {'1': 1, '3': 27, '5': 27, '6': 513, '7': 1035, '8': 24},
                 '2018': {'5': 54}}
        self.assertEqual(V._checar_eleitos({'c': [], 'anteriores': cheio}, 1, 0, True), [])
        pouco = dict(cheio, **{'2022': dict(cheio['2022'], **{'6': 400})})
        self.assertTrue(V._checar_eleitos({'c': [], 'anteriores': pouco}, 1, 0, True))
        self.assertEqual(V._checar_eleitos({'c': [], 'anteriores': pouco}, 1, 0, False), [])
        demais = dict(cheio, **{'2018': {'5': 55}})
        self.assertTrue(V._checar_eleitos({'c': [], 'anteriores': demais}, 1, 0, True))


class TestAnterioresReais(ComSal):
    """A fatia real de Roraima. As contagens sao fato: RR tem 8 cadeiras na
    Camara, 24 na Assembleia, 3 no Senado (1 eleita em 2022, 2 em 2018)."""

    def test_contagem_de_roraima(self):
        from ferramentas import anteriores
        est = os.path.join(self.tmp, 'estado')
        r = anteriores.main(['--estado', est, '--fonte-local', FIX, '--uf', 'RR',
                             '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 0)
        linhas, _ = EL.ler_anteriores(est)
        por = {}
        for l in linhas:
            por[(l['ano'], l['cargo'])] = por.get((l['ano'], l['cargo']), 0) + 1
        self.assertEqual(por, {(2022, '6'): 8, (2022, '7'): 24, (2022, '3'): 1,
                               (2022, '5'): 1, (2018, '5'): 2})


class TestRodadaComDesfecho(ComSal):
    """A rodada da fixture com um desfecho escrito a mao no consulta_cand de 2026:
    reelege quem foi eleito deputado federal em 2022 e concorre de novo."""

    def _fonte_com_desfecho(self):
        fonte = os.path.join(self.tmp, 'fonte')
        shutil.copytree(FIX, fonte)
        # os CPF dos deputados federais eleitos em RR em 2022
        z22 = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand_2022.zip'))
        eleitos22 = {c.cpf for c in C.candidaturas(z22, 'RR', ano=2022)
                     if c.cargo == '6' and EL.D.codigo(c.sit_turno) == 1 and c.cpf}
        caminho = os.path.join(fonte, 'consulta_cand.zip')
        z = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand.zip'))
        membro = C.membro_uf(z, 'consulta_cand_2026', 'RR')
        texto = z.read(membro).decode('latin-1')
        leitor = list(csv.reader(io.StringIO(texto), delimiter=';'))
        cab = [c.lstrip('﻿').strip('"').strip() for c in leitor[0]]
        i_cpf, i_sit, i_cargo = (cab.index(k) for k in
                                 ('NR_CPF_CANDIDATO', 'DS_SIT_TOT_TURNO', 'CD_CARGO'))
        reeleitos = 0
        for l in leitor[1:]:
            if len(l) == len(cab) and l[i_cargo] == '6' and C.documento(l[i_cpf]) in eleitos22:
                l[i_sit] = 'ELEITO'
                reeleitos += 1
        buf = io.StringIO()
        csv.writer(buf, delimiter=';', quoting=csv.QUOTE_ALL,
                   lineterminator='\n').writerows(leitor)
        os.remove(caminho)
        with zipfile.ZipFile(caminho, 'w') as out:
            out.writestr(membro, buf.getvalue().encode('latin-1'))
        return fonte, reeleitos

    def test_rodada_escreve_eleitos_e_o_validador_aprova(self):
        from ferramentas import anteriores
        from pipeline import rodar
        fonte, reeleitos = self._fonte_com_desfecho()
        self.assertGreater(reeleitos, 0, 'nenhum deputado de 2022 concorre de novo '
                           'na fixture, ou o CPF nao veio em um dos anos')
        est = os.path.join(self.tmp, 'estado')
        anteriores.main(['--estado', est, '--fonte-local', FIX, '--uf', 'RR',
                         '--destino', os.path.join(self.tmp, 'd')])
        site = os.path.join(self.tmp, 'site')
        rodar.main(['--fonte-local', fonte, '--ufs', 'RR', '--sem-receita',
                    '--site', site, '--estado', est,
                    '--dados', os.path.join(self.tmp, 'sem-dados'),
                    '--hoje', '2026-10-06'])
        self.assertEqual(V.validar(site), [])
        meta = json.load(open(os.path.join(site, 'meta.json'), encoding='utf-8'))
        self.assertTrue(meta['tem_desfecho'])
        self.assertTrue(meta['eleitos'])
        d = json.load(open(os.path.join(site, 'eleitos', 'BRASIL.json'), encoding='utf-8'))
        destinos = [l[5] for l in d['c'] if l[2] == '6']
        self.assertEqual(destinos.count(EL.MESMO_CARGO), reeleitos)
        self.assertEqual(len(destinos), 8)
        texto = open(os.path.join(site, 'eleitos', 'BRASIL.json'), encoding='utf-8').read()
        for cpf in list(self._cpfs_2022())[:20]:
            self.assertNotIn(cpf, texto)
        # todo sq escrito abre uma ficha que existe
        sqs = [l[10] for l in d['c'] if l[10]]
        self.assertTrue(sqs)
        for sq in sqs:
            self.assertTrue(os.path.exists(os.path.join(site, 'cand', sq + '.json')), sq)

    def test_anteriores_corrompido_tira_a_aba_e_nao_a_rodada(self):
        from pipeline import rodar
        fonte, _ = self._fonte_com_desfecho()
        est = os.path.join(self.tmp, 'estado')
        os.makedirs(est)
        with open(os.path.join(est, EL.ARQUIVO), 'w', encoding='utf-8') as f:
            f.write('{"sal_marca": "abc", "linhas": [{"chave": "p1"')
        site = os.path.join(self.tmp, 'site')
        rodar.main(['--fonte-local', fonte, '--ufs', 'RR', '--sem-receita',
                    '--site', site, '--estado', est,
                    '--dados', os.path.join(self.tmp, 'sem-dados'),
                    '--hoje', '2026-10-06'])
        self.assertEqual(V.validar(site), [])
        meta = json.load(open(os.path.join(site, 'meta.json'), encoding='utf-8'))
        self.assertTrue(meta['tem_desfecho'])
        self.assertFalse(meta.get('eleitos'))
        self.assertFalse(os.path.exists(os.path.join(site, 'eleitos', 'BRASIL.json')))

    def test_erro_no_cruzamento_tira_a_aba_e_nao_mostra_conteudo(self):
        from unittest import mock
        from ferramentas import anteriores
        from pipeline import rodar
        fonte, _ = self._fonte_com_desfecho()
        est = os.path.join(self.tmp, 'estado')
        anteriores.main(['--estado', est, '--fonte-local', FIX, '--uf', 'RR',
                         '--destino', os.path.join(self.tmp, 'd')])
        site = os.path.join(self.tmp, 'site')
        saida = io.StringIO()
        with mock.patch.object(EL, 'cruzar', side_effect=ValueError('MARIA DA SILVA')), \
                mock.patch('sys.stdout', saida):
            rodar.main(['--fonte-local', fonte, '--ufs', 'RR', '--sem-receita',
                        '--site', site, '--estado', est,
                        '--dados', os.path.join(self.tmp, 'sem-dados'),
                        '--hoje', '2026-10-06'])
        self.assertIn('ValueError', saida.getvalue())
        self.assertNotIn('MARIA DA SILVA', saida.getvalue())
        self.assertEqual(V.validar(site), [])
        meta = json.load(open(os.path.join(site, 'meta.json'), encoding='utf-8'))
        self.assertFalse(meta.get('eleitos'))

    def _cpfs_2022(self):
        z22 = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand_2022.zip'))
        return {c.cpf for c in C.candidaturas(z22, 'RR', ano=2022) if c.cpf}


if __name__ == '__main__':
    unittest.main(verbosity=2)
