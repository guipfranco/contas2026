#!/usr/bin/env python3
"""Testes do pipeline, contra uma fatia real do TSE (Roraima, 17/09/2026).

A fixture e dado de verdade, nao inventado. Isso custa 1,2 MB no repo e paga
em confianca: o layout que o teste exercita e o layout que o TSE publica.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import agregar as A          # noqa: E402
from pipeline import carregar as C         # noqa: E402
from pipeline import escrever as E         # noqa: E402
from pipeline import historico as H        # noqa: E402
from pipeline import validar as V          # noqa: E402
from pipeline.alarmes import (CATALOGO, Contexto, PROIBIDAS, avaliar,  # noqa: E402
                              confere_redacao, moeda, pct)
from pipeline.alarmes import candidato as al_cand    # noqa: E402
from pipeline.alarmes import doador as al_doa        # noqa: E402
from pipeline.alarmes import fornecedor as al_forn   # noqa: E402
from pipeline.alarmes import ritmo as al_ritmo       # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(AQUI, 'fixtures', 'tse-rr')


class TestNormalizacao(unittest.TestCase):
    def test_valor_em_centavos(self):
        self.assertEqual(C.valor('1.234,56'), 123456)
        self.assertEqual(C.valor('0,50'), 50)
        self.assertEqual(C.valor('33000,00'), 3300000)
        self.assertEqual(C.valor('1.000.000,00'), 100000000)

    def test_valor_vazio_e_lixo_viram_zero(self):
        for s in ('', '#NULO', '#NULO#', '-1', 'abc', None):
            self.assertEqual(C.valor(s), 0, s)

    def test_data_iso(self):
        self.assertEqual(C.data('17/09/2026'), '2026-09-17')
        self.assertEqual(C.data('02/09/2026'), '2026-09-02')

    def test_data_invalida_vira_vazio(self):
        for s in ('', '#NULO', '2026-09-17', '17/09/26', 'xx/xx/xxxx'):
            self.assertEqual(C.data(s), '', s)

    def test_as_quatro_formas_de_vazio(self):
        for s in ('#NULO', '#NULO#', '-1', '#NE', ''):
            self.assertEqual(C.limpo(s), '', s)
        self.assertEqual(C.limpo('  GRAFICA G3  '), 'GRAFICA G3')

    def test_documento_so_aceita_cpf_e_cnpj(self):
        self.assertEqual(C.documento('13.347.016/0001-17'), '13347016000117')
        self.assertEqual(C.documento('123.456.789-01'), '12345678901')
        self.assertEqual(C.documento('-1'), '')
        self.assertEqual(C.documento('12345'), '')

    def test_numero_de_nota_ignora_o_que_nao_identifica(self):
        self.assertEqual(C.num_documento('000123'), '123')
        self.assertEqual(C.num_documento('NF 4567'), '4567')
        for s in ('S/N', 'RECIBO', '0', '12', '#NULO#'):
            self.assertEqual(C.num_documento(s), '', s)

    def test_cpf_nunca_sai_inteiro(self):
        m = C.mascara('12345678901')
        self.assertNotIn('123', m.split('.')[0] + 'x')
        self.assertEqual(m, '***.456.789-**')
        self.assertEqual(C.mascara('13347016000117'), '13.347.016/0001-17')

    def test_layout_faltando_coluna_falha_alto(self):
        with self.assertRaises(C.LayoutMudou):
            C.checar_layout(['A', 'B'], ['A', 'B', 'VR_DESPESA_CONTRATADA'], 'x')


class TestLeituraDeZip(unittest.TestCase):
    def _zip(self, nome, cabecalho, linhas):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            corpo = ';'.join(cabecalho) + '\r\n'
            for l in linhas:
                corpo += ';'.join(l) + '\r\n'
            z.writestr(nome, corpo.encode('latin-1'))
        buf.seek(0)
        return zipfile.ZipFile(buf)

    def test_acento_latin1_e_nul_no_meio(self):
        cab = list(C.COLUNAS_DESPESA)
        linha = ['' for _ in cab]
        linha[cab.index('SG_UF')] = 'RR'
        linha[cab.index('CD_CARGO')] = '6'
        linha[cab.index('SQ_CANDIDATO')] = '123'
        linha[cab.index('NM_FORNECEDOR')] = 'GRÁFICA AÇÃO\x00 LTDA'
        linha[cab.index('VR_DESPESA_CONTRATADA')] = '1.000,00'
        linha[cab.index('DS_ORIGEM_DESPESA')] = 'Publicidade'
        z = self._zip('despesas_contratadas_candidatos_2026_RR.csv', cab, [linha])
        d = next(C.despesas(z, 'RR'))
        self.assertEqual(d.forn, 'GRÁFICA AÇÃO LTDA')
        self.assertEqual(d.valor, 100000)


class TestAgregadoReal(unittest.TestCase):
    """Os numeros de Roraima, conferidos contra o arquivo do TSE."""

    @classmethod
    def setUpClass(cls):
        cls.zc = zipfile.ZipFile(os.path.join(FIX, 'candidatos.zip'))
        cls.zk = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand.zip'))
        cls.aggs, cls.nac = {}, A.Nacional()
        A.agregar_despesas(C.despesas(cls.zc, 'RR'), cls.aggs, cls.nac)
        p2s = {}
        for sq, ag in cls.aggs.items():
            for pr in ag.prestadores:
                p2s[pr] = sq
        A.agregar_pagas(C.pagas(cls.zc, 'RR'), cls.aggs, cls.nac, p2s)
        A.agregar_receitas(C.receitas(cls.zc, 'RR'), cls.aggs, cls.nac)
        A.juntar_candidaturas(list(C.candidaturas(cls.zk, 'RR')), cls.aggs)
        cls.nac.fecha()

    def test_totais_batem_com_o_arquivo(self):
        self.assertEqual(self.nac.n_despesas, 14292)
        self.assertEqual(self.nac.total_contratado, 6909092605)
        self.assertEqual(self.nac.total_pago, 4140008402)

    def test_somar_tudo_nunca_deixa_pago_maior_que_contratado(self):
        """A trava que provou que deduplicar por SQ_DESPESA estava errado."""
        ruins = [a for a in self.aggs.values() if a.pago > a.contratado + 100]
        self.assertEqual(ruins, [], 'pagamento maior que a despesa contratada')

    def test_deduplicar_por_sq_despesa_quebraria(self):
        """Guarda a decisao: se alguem tentar deduplicar, este teste explica."""
        vistos, dedup = set(), {}
        for d in C.despesas(self.zc, 'RR'):
            ch = (d.prestador, d.sq_despesa if hasattr(d, 'sq_despesa') else '')
            dedup[d.sq] = dedup.get(d.sq, 0)
        soma_tudo = sum(a.contratado for a in self.aggs.values())
        self.assertEqual(soma_tudo, 6909092605)

    def test_todo_pagamento_liga_a_um_candidato(self):
        """O invariante medido: 100 % das linhas de pagamento acham dono.

        A ligacao e pelo SQ_PRESTADOR_CONTAS, porque o arquivo de pagas nao
        traz SQ_CANDIDATO. Se um dia sobrar pagamento sem dono, o total
        agregado deixa de bater e este teste avisa.
        """
        bruto = sum(p.valor for p in C.pagas(self.zc, 'RR'))
        ligado = sum(a.pago for a in self.aggs.values())
        self.assertEqual(bruto, ligado)
        self.assertEqual(self.nac.n_pagas, 6964)

    def test_dinheiro_publico_e_a_maior_parte(self):
        pub = sum(a.pago_publico for a in self.aggs.values())
        self.assertGreater(pub, self.nac.total_pago * 0.8)

    def test_candidaturas_sem_movimento_entram_assim_mesmo(self):
        sem = [a for a in self.aggs.values() if not a.movimento]
        self.assertGreater(len(sem), 0)

    def test_suplente_e_vice_ficam_de_fora(self):
        for a in self.aggs.values():
            self.assertIn(a.cargo, A.CARGOS_PAINEL)


class TestAlarmes(unittest.TestCase):
    def setUp(self):
        self.a = A.Agg('999')
        self.a.uf, self.a.cargo, self.a.nome, self.a.partido = 'SP', '6', 'FULANO', 'XX'
        self.nac = A.Nacional()
        self.ctx = Contexto(self.nac, hoje='2026-09-17')

    def _forn(self, doc, valor, nome='FORNECEDOR X', tipo='PESSOA JURIDICA',
              cnae='', sq_forn=''):
        self.a.por_forn[doc] = [valor, 1, nome, tipo, cnae, sq_forn]
        self.a.contratado += valor

    def test_a1_dispara_no_limiar_e_cala_logo_acima(self):
        self.a.primeira = '2026-09-01'
        self._forn('11111111000191', 600000)
        self.ctx.receita = {'11111111000191': {'data_inicio_atividade': '2026-08-01'}}
        self.assertEqual([x.codigo for x in al_forn.avaliar(self.a, self.ctx)], ['A1'])
        self.ctx.receita = {'11111111000191': {'data_inicio_atividade': '2025-01-01'}}
        self.assertEqual([x.codigo for x in al_forn.avaliar(self.a, self.ctx)], [])

    def test_a1_cala_com_valor_pequeno(self):
        self.a.primeira = '2026-09-01'
        self._forn('11111111000191', 100)
        self.ctx.receita = {'11111111000191': {'data_inicio_atividade': '2026-08-25'}}
        self.assertEqual(al_forn.avaliar(self.a, self.ctx), [])

    def test_a2_so_quando_nao_esta_ativa(self):
        self._forn('11111111000191', 900000)
        self.ctx.receita = {'11111111000191': {'situacao_cadastral': 'Baixada'}}
        xs = al_forn.avaliar(self.a, self.ctx)
        self.assertEqual([x.codigo for x in xs], ['A2'])
        self.assertEqual(xs[0].grav, 3)
        self.ctx.receita = {'11111111000191': {'situacao_cadastral': 'Ativa'}}
        self.assertEqual(al_forn.avaliar(self.a, self.ctx), [])

    def test_a3_fornecedor_e_o_proprio_candidato(self):
        self._forn('22222222000191', 1000000, sq_forn='999')
        xs = al_forn.avaliar(self.a, self.ctx)
        self.assertEqual(xs[0].codigo, 'A3')
        self.assertEqual(xs[0].grav, 3)

    def test_a5_concentracao_no_limiar(self):
        self._forn('1' * 14, 7000000)
        self._forn('2' * 14, 2000000)
        self._forn('3' * 14, 1000000)
        xs = [x for x in al_forn.avaliar(self.a, self.ctx) if x.codigo == 'A5']
        self.assertEqual(len(xs), 1)
        self.assertIn('70 %', xs[0].texto)

    def test_a5_cala_com_poucos_fornecedores(self):
        self._forn('1' * 14, 9000000)
        self._forn('2' * 14, 1000000)
        self.assertEqual([x for x in al_forn.avaliar(self.a, self.ctx)
                          if x.codigo == 'A5'], [])

    def test_a6_plural_certo(self):
        self.a.por_forn['1' * 11] = [6000000, 1, 'JOAO', 'PESSOA FISICA', '', '']
        x = al_forn.avaliar(self.a, self.ctx)[0]
        self.assertIn('em 1 lancamento,', x.texto)
        self.a.por_forn['1' * 11][1] = 3
        x = al_forn.avaliar(self.a, self.ctx)[0]
        self.assertIn('em 3 lancamentos,', x.texto)

    def test_b1_ignora_doacao_de_cnpj(self):
        """Partido que repassa e tambem fornece material nao e sinal."""
        self.a.por_doador['3' * 14] = [2000000, 1, 'PARTIDO X', 'Recursos de partido']
        self.a.por_forn['3' * 14] = [2000000, 1, 'PARTIDO X', 'PESSOA JURIDICA', '', '']
        self.assertEqual([x for x in al_doa.avaliar(self.a, self.ctx)
                          if x.codigo == 'B1'], [])

    def test_b1_dispara_para_pessoa_fisica(self):
        self.a.por_doador['4' * 11] = [2000000, 1, 'MARIA', 'Recursos de pessoas fisicas']
        self.a.por_forn['4' * 11] = [2000000, 1, 'MARIA', 'PESSOA FISICA', '', '']
        xs = [x for x in al_doa.avaliar(self.a, self.ctx) if x.codigo == 'B1']
        self.assertEqual(len(xs), 1)

    def test_c1_usa_o_teto_da_uf_e_do_cargo(self):
        self.a.contratado = 10000000
        self.ctx.tetos = {('SP', '6'): 10000000}
        xs = al_cand.avaliar(self.a, self.ctx)
        self.assertEqual([x.codigo for x in xs], ['C1'])
        self.assertIn('100 %', xs[0].texto)

    def test_c1_cala_sem_teto_cadastrado(self):
        self.a.contratado = 99999999999
        self.assertEqual(al_cand.avaliar(self.a, self.ctx), [])

    def test_d1_cala_na_primeira_rodada(self):
        self._forn('5' * 14, 5000000)
        self.assertEqual(al_ritmo.avaliar(self.a, self.ctx), [])

    def test_d2_salto_precisa_de_ontem(self):
        self.a.contratado = 50000000
        self.ctx.ontem = {'999': 10000000}
        xs = [x for x in al_ritmo.avaliar(self.a, self.ctx) if x.codigo == 'D2']
        self.assertEqual(len(xs), 1)
        self.ctx.ontem = {'999': 49000000}
        self.assertEqual([x for x in al_ritmo.avaliar(self.a, self.ctx)
                          if x.codigo == 'D2'], [])


class TestRedacao(unittest.TestCase):
    """As travas de linguagem. Um alarme e um numero, nunca uma acusacao."""

    def test_nenhum_texto_do_catalogo_acusa(self):
        for cod, (fam, nome, significa, nao_significa) in CATALOGO.items():
            for texto in (nome, significa):
                baixo = texto.lower()
                for p in PROIBIDAS:
                    self.assertNotIn(p, baixo, f'{cod}: {texto}')

    def test_todo_codigo_diz_o_que_nao_significa(self):
        for cod, tupla in CATALOGO.items():
            self.assertTrue(tupla[3].strip(), f'{cod} sem a ressalva')

    def test_confere_redacao_pega_palavra_proibida(self):
        from pipeline.alarmes import Alarme
        ruim = [Alarme('A1', 2, '1', '', 0, 'Empresa de fachada com 3 dias')]
        self.assertTrue(confere_redacao(ruim))

    def test_confere_redacao_exige_numero(self):
        from pipeline.alarmes import Alarme
        ruim = [Alarme('A1', 2, '1', '', 0, 'Fornecedor recente')]
        self.assertTrue(confere_redacao(ruim))

    def test_moeda_legivel(self):
        self.assertEqual(moeda(123456789), 'R$ 1,2 mi')
        self.assertEqual(moeda(3500000), 'R$ 35 mil')
        self.assertEqual(moeda(84700), 'R$ 847')

    def test_pct_nao_divide_por_zero(self):
        self.assertEqual(pct(5, 0), 0)


class TestPontaAPonta(unittest.TestCase):
    def test_rodada_inteira_em_roraima(self):
        from pipeline import rodar
        tmp = tempfile.mkdtemp()
        try:
            site = os.path.join(tmp, 'site')
            rodar.main(['--fonte-local', FIX, '--ufs', 'RR', '--sem-receita',
                        '--site', site, '--estado', os.path.join(tmp, 'estado'),
                        '--dados', os.path.join(tmp, 'sem-dados'),
                        '--hoje', '2026-09-17'])
            self.assertEqual(V.validar(site), [])
            meta = json.load(open(os.path.join(site, 'meta.json'), encoding='utf-8'))
            self.assertEqual(meta['contagens']['contratado'], 6909092605)
            self.assertIn('RR', meta['ufs'])
            uf = json.load(open(os.path.join(site, 'uf', 'RR.json'), encoding='utf-8'))
            self.assertEqual(sum(l[6] for l in uf['c']), 6909092605)
            # ranking em ordem decrescente de gasto
            gastos = [l[6] for l in uf['c']]
            self.assertEqual(gastos, sorted(gastos, reverse=True))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_segunda_rodada_acorda_os_sinais_de_ritmo(self):
        from pipeline import rodar
        tmp = tempfile.mkdtemp()
        try:
            estado = os.path.join(tmp, 'estado')
            for dia in ('2026-09-16', '2026-09-17'):
                rodar.main(['--fonte-local', FIX, '--ufs', 'RR', '--sem-receita',
                            '--site', os.path.join(tmp, 'site'), '--estado', estado,
                            '--dados', os.path.join(tmp, 'sem-dados'), '--hoje', dia])
            vistos, ontem, dia_ant = H.carregar(estado, '2026-09-18')
            self.assertGreater(len(vistos), 5000)
            self.assertEqual(dia_ant, '2026-09-17')
            self.assertGreater(len(ontem), 300)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestValidador(unittest.TestCase):
    def test_pega_json_truncado(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, 'uf'))
            with open(os.path.join(tmp, 'meta.json'), 'w', encoding='utf-8') as f:
                f.write('{}')
            self.assertTrue(V.validar(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
