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


class TestComparacaoEntrePares(unittest.TestCase):
    """Um numero sozinho nao diz nada; o grupo de comparacao e (UF, cargo)."""

    def _agg(self, uf, cargo, valor):
        a = A.Agg(f'{uf}{cargo}{valor}')
        a.uf, a.cargo, a.contratado = uf, cargo, valor
        return a

    def test_grupo_e_uf_mais_cargo(self):
        aggs = {}
        for v in (100, 200, 300, 400, 500):
            a = self._agg('SP', '6', v)
            aggs[a.sq] = a
        for v in (10, 20):
            a = self._agg('AC', '7', v)
            aggs[a.sq] = a
        refs = A.referencias(aggs)
        self.assertEqual(set(refs), {('SP', '6'), ('AC', '7')})
        self.assertEqual(refs[('SP', '6')]['n'], 5)
        self.assertEqual(refs[('SP', '6')]['mediana'], 300)

    def test_quem_nao_gastou_nao_puxa_a_mediana_para_zero(self):
        aggs = {}
        for v in (100, 200, 300):
            a = self._agg('SP', '6', v)
            aggs[a.sq] = a
        for i in range(20):
            a = self._agg('SP', '6', 0)
            a.sq = f'zero{i}'
            aggs[a.sq] = a
        refs = A.referencias(aggs)
        self.assertEqual(refs[('SP', '6')]['n'], 3)
        self.assertEqual(refs[('SP', '6')]['mediana'], 200)

    def test_posicao_traz_multiplo_e_fatia(self):
        aggs = {}
        for v in (100, 200, 700):
            a = self._agg('SP', '6', v)
            aggs[a.sq] = a
        refs = A.referencias(aggs)
        maior = max(aggs.values(), key=lambda x: x.contratado)
        p = A.posicao(maior, refs)
        self.assertEqual(p['vezes_a_mediana'], 3.5)
        self.assertEqual(p['fatia_do_grupo'], 70.0)

    def test_sem_gasto_nao_tem_comparacao(self):
        a = self._agg('SP', '6', 0)
        self.assertIsNone(A.posicao(a, A.referencias({a.sq: a})))


class TestAlarmes(unittest.TestCase):
    def setUp(self):
        self.a = A.Agg('999')
        self.a.uf, self.a.cargo, self.a.nome, self.a.partido = 'SP', '6', 'FULANO', 'XX'
        self.nac = A.Nacional()
        self.ctx = Contexto(self.nac, hoje='2026-09-17')

    def _forn(self, doc, valor, nome='FORNECEDOR X', tipo='PESSOA JURIDICA',
              cnae='', sq_forn=''):
        self.a.por_forn[doc] = [valor, 1, nome, tipo, cnae, sq_forn, '', valor]
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
        self._forn('11222333000181', 900000)
        self.ctx.receita = {'11222333000181': {'situacao_cadastral': 'Baixada'}}
        xs = al_forn.avaliar(self.a, self.ctx)
        self.assertEqual([x.codigo for x in xs], ['A2'])
        self.assertEqual(xs[0].grav, 2, 'R$ 9 mil nao e o topo da fila')
        self.ctx.receita = {'11222333000181': {'situacao_cadastral': 'Ativa'}}
        self.assertEqual(al_forn.avaliar(self.a, self.ctx), [])

    def test_a2_grave_so_com_valor_alto(self):
        self._forn('11222333000181', 6000000)
        self.ctx.receita = {'11222333000181': {'situacao_cadastral': 'Inapta'}}
        xs = al_forn.avaliar(self.a, self.ctx)
        self.assertEqual(xs[0].grav, 3)

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
        self.a.por_forn['11144477735'] = [12000000, 1, 'JOAO', 'PESSOA FISICA',
                                          '', '', '', 12000000]
        x = al_forn.avaliar(self.a, self.ctx)[0]
        self.assertEqual(x.codigo, 'A6')
        self.assertIn('em 1 lançamento,', x.texto)
        self.a.por_forn['11144477735'][1] = 3
        x = al_forn.avaliar(self.a, self.ctx)[0]
        self.assertIn('em 3 lançamentos,', x.texto)

    def test_a6_ignora_o_ordinario(self):
        """R$ 60 mil a uma pessoa fisica e o comum, nao um sinal.

        Sao 374 mil CPF prestando servico nesta eleicao. O limiar antigo, de
        R$ 50 mil, gerava 630 sinais com mediana de R$ 60 mil: apontava o
        normal.
        """
        self.a.por_forn['11144477735'] = [6000000, 1, 'JOAO', 'PESSOA FISICA',
                                          '', '', '', 6000000]
        self.assertEqual([x for x in al_forn.avaliar(self.a, self.ctx)
                          if x.codigo == 'A6'], [])

    def test_a3_nao_dispara_em_repasse_entre_campanhas(self):
        """Candidato repassando dinheiro a outro nao e 'fornecedor'."""
        self.a.por_forn['11222333000181'] = [
            100000000, 1, 'ELEICAO 2026 FULANO', 'PESSOA JURIDICA', '', '888',
            'Doacoes financeiras a outros candidatos/partidos', 100000000]
        self.assertEqual([x for x in al_forn.avaliar(self.a, self.ctx)
                          if x.codigo == 'A3'], [])

    def test_a7_pega_digito_verificador_quebrado(self):
        self._forn('13347016000118', 500000)
        xs = [x for x in al_forn.avaliar(self.a, self.ctx) if x.codigo == 'A7']
        self.assertEqual(len(xs), 1)
        self.assertIn('dígito verificador', xs[0].texto)

    def test_a7_nao_reclama_de_documento_valido(self):
        self._forn('13347016000117', 500000)
        self.assertEqual([x for x in al_forn.avaliar(self.a, self.ctx)
                          if x.codigo == 'A7'], [])

    def test_b1_ignora_doacao_de_cnpj(self):
        """Partido que repassa e tambem fornece material nao e sinal."""
        self.a.por_doador['3' * 14] = [5000000, 1, 'PARTIDO X', 'Recursos de partido']
        self.a.por_forn['3' * 14] = [5000000, 1, 'PARTIDO X', 'PESSOA JURIDICA',
                                     '', '', '', 5000000]
        self.assertEqual([x for x in al_doa.avaliar(self.a, self.ctx)
                          if x.codigo == 'B1'], [])

    def test_b1_dispara_para_pessoa_fisica(self):
        self.a.por_doador['11144477735'] = [3000000, 1, 'MARIA',
                                            'Recursos de pessoas fisicas']
        self.a.por_forn['11144477735'] = [3000000, 1, 'MARIA', 'PESSOA FISICA',
                                          '', '', '', 3000000]
        xs = [x for x in al_doa.avaliar(self.a, self.ctx) if x.codigo == 'B1']
        self.assertEqual(len(xs), 1)

    def test_b3_usa_10_por_cento_do_teto_do_cargo(self):
        """A base legal e o teto do cargo, nao o rendimento do candidato.

        Lei 9.504/1997, art. 23, paragrafo 2-A. Os 10 % do rendimento bruto
        sao o limite de doacao de TERCEIRO, e a confusao entre os dois estava
        no desenho original deste alarme.
        """
        self.ctx.tetos = {('BR', '6'): 317657253}      # deputado federal 2026
        self.a.por_origem['Recursos proprios'] = 40000000   # R$ 400 mil
        self.a.receita = 100000000
        xs = [x for x in al_doa.avaliar(self.a, self.ctx) if x.codigo == 'B3']
        self.assertEqual(len(xs), 1)
        self.assertEqual(xs[0].grav, 3)
        self.assertIn('10 %', xs[0].texto)

    def test_b3_cala_dentro_do_limite(self):
        self.ctx.tetos = {('BR', '6'): 317657253}
        self.a.por_origem['Recursos proprios'] = 30000000   # R$ 300 mil
        self.a.receita = 100000000
        self.assertEqual([x for x in al_doa.avaliar(self.a, self.ctx)
                          if x.codigo == 'B3'], [])

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


class TestIndiceDeConferencia(unittest.TestCase):
    """O indice ordena a fila de quem vai conferir. Nao mede ilegalidade."""

    def _al(self, grav, valor, cod='A1'):
        from pipeline.alarmes import Alarme
        return Alarme(cod, grav, '1', 'x', valor, 'texto com 1 numero')

    def test_sem_sinal_e_zero(self):
        from pipeline.alarmes import faixa, indice
        self.assertEqual(indice(100000000, []), 0)
        self.assertEqual(faixa(0), 'nada apontado')

    def test_pesa_por_quanto_do_dinheiro_o_sinal_alcanca(self):
        """O mesmo sinal vale mais quando toca a maior parte da campanha."""
        from pipeline.alarmes import indice
        grande = indice(100000000, [self._al(3, 1000)])
        metade = indice(100000000, [self._al(3, 50000000)])
        tudo = indice(100000000, [self._al(3, 100000000)])
        self.assertLess(grande, metade)
        self.assertLess(metade, tudo)

    def test_volume_de_sinal_leve_nao_domina(self):
        """500 fornecedores nao podem virar pontuacao por volume."""
        from pipeline.alarmes import indice
        muitos = indice(100000000, [self._al(1, 100000)] * 50)
        um_grave = indice(100000000, [self._al(3, 100000000)])
        self.assertLess(muitos, um_grave)

    def test_nao_passa_de_cem(self):
        from pipeline.alarmes import indice
        self.assertEqual(indice(1000, [self._al(3, 1000)] * 30), 100)

    def test_nada_declarado_fica_fora_do_indice(self):
        """C2 e ausencia de conta, nao algo a conferir dentro dela."""
        from pipeline.alarmes import FORA_DO_INDICE, indice
        self.assertIn('C2', FORA_DO_INDICE)
        self.assertEqual(indice(0, [self._al(1, 0, 'C2')]), 0)

    def test_todo_codigo_tem_rotulo_curto_sem_codigo_dentro(self):
        """O codigo e endereco interno: nunca aparece na tela."""
        import re
        from pipeline.alarmes import CATALOGO, CURTO
        for cod in CATALOGO:
            self.assertIn(cod, CURTO, f'{cod} sem rotulo curto')
            self.assertLessEqual(len(CURTO[cod]), 22, f'{cod}: rotulo longo')
            self.assertIsNone(re.search(r'[A-D]\d', CURTO[cod]),
                              f'{cod}: o rotulo contem o codigo')


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

    def test_nenhum_texto_de_sinal_sai_sem_acento(self):
        """Portugues sem acento numa tela publica e erro, nao estilo.

        A regra vale para o texto escrito aqui. Nome proprio vindo do TSE fica
        como o TSE publicou.
        """
        import re
        from pipeline.alarmes import candidato, doador, fornecedor, ritmo
        sem_acento = re.compile(
            r"(lancamento|lancamentos|fisica|fisicas|digito|digitacao|proprio|"
            r"propria|proprios|servico|servicos|eleicao|declaracao|declaracoes|"
            r"prestacao|situacao|arrecadacao|constituicao|paragrafo|publico|"
            r"publica|automatico|minimo|padrao|tambem|numero|nao|esta|ate)")
        achados = []
        for mod in (candidato, doador, fornecedor, ritmo):
            fonte = open(mod.__file__, encoding='utf-8').read()
            # so as f-strings de mensagem, nunca comentario nem docstring
            for m in re.findall(r"f'([^']{20,})'", fonte):
                fora = re.sub(r'\{[^}]*\}', '', m)
                for p in sem_acento.findall(fora.lower()):
                    achados.append((mod.__name__, p, m[:60]))
        self.assertEqual(achados, [], f'{len(achados)} palavras sem acento')

    def test_todo_texto_que_vai_para_a_tela_tem_acento(self):
        """Nao so as mensagens: os dicionarios do catalogo tambem sao tela."""
        import re
        from pipeline.alarmes import (CATALOGO, CURTO, FAIXAS, FORA_DO_INDICE,
                                      GRAVIDADE)
        sem = re.compile(
            r"(nao|acao|acoes|declaracao|prestacao|ausencia|conferencia|"
            r"indice|codigo|proprio|propria|servico|fisica|publico|publica|"
            r"minimo|numero|tambem|eleicao|situacao|atividade economica|"
            r"digito|padrao|orgao)", re.I)
        achados = []
        for nome, d in (('FORA_DO_INDICE', FORA_DO_INDICE), ('CURTO', CURTO),
                        ('GRAVIDADE', GRAVIDADE)):
            for k, v in d.items():
                achados += [(nome, k, m) for m in sem.findall(str(v))]
        for corte, texto in FAIXAS:
            achados += [('FAIXAS', corte, m) for m in sem.findall(texto)]
        for cod, tupla in CATALOGO.items():
            for parte in tupla:
                achados += [(cod, parte[:24], m) for m in sem.findall(parte)]
        self.assertEqual(achados, [], f'{len(achados)} sem acento')

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
            self.assertTrue(all(len(l) == 16 for l in uf['c']))
            # a origem da receita vem na linha, para o filtro por fonte de
            # financiamento funcionar sem baixar a ficha de cada candidatura
            self.assertIn('origem', meta['dic'])
            com_origem = [l for l in uf['c'] if l[15]]
            self.assertGreater(len(com_origem), 100)
            n_orig = len(meta['dic']['origem'])
            for l in com_origem:
                for oid, v in l[15]:
                    self.assertTrue(0 <= oid < n_orig)
                    self.assertGreater(v, 0)
            br = json.load(open(os.path.join(site, 'uf', 'BRASIL.json'),
                                encoding='utf-8'))
            self.assertTrue(all(len(l) == 17 for l in br['c']))
            self.assertTrue(all(l[16] == 'RR' for l in br['c']))
            self.assertEqual(sum(l[6] for l in br['c']), 6909092605)
            self.assertIn('RR', meta['nome_uf'])
            self.assertEqual(meta['nome_uf']['BR'] if 'BR' in meta['nome_uf']
                             else 'Presidência', 'Presidência')
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
