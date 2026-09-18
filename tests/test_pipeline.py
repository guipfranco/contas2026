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
            self.assertIsNone(re.search(r'\b[A-D]\d\b', CURTO[cod]),
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
            r"\b(lancamento|lancamentos|fisica|fisicas|digito|digitacao|proprio|"
            r"propria|proprios|servico|servicos|eleicao|declaracao|declaracoes|"
            r"prestacao|situacao|arrecadacao|constituicao|paragrafo|publico|"
            r"publica|automatico|minimo|padrao|tambem|numero|nao|esta|ate)\b")
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
            r"\b(nao|acao|acoes|declaracao|prestacao|ausencia|conferencia|"
            r"indice|codigo|proprio|propria|servico|fisica|publico|publica|"
            r"minimo|numero|tambem|eleicao|situacao|atividade economica|"
            r"digito|padrao|orgao)\b", re.I)
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


class TestRedacaoDoSite(unittest.TestCase):
    """O texto de site/index.html tambem e tela, e nenhum teste o lia.

    As travas eram conferidas so no texto que o pipeline escreve, e o site tem
    mais texto que ele: titulo de secao, nota, ressalva, rotulo de filtro. Foi
    por ai que passou um cabecalho afirmando propriedade ("quem sao os donos")
    sobre um dado que so diz quem consta como socio.
    """

    @classmethod
    def setUpClass(cls):
        import re
        caminho = os.path.join(os.path.dirname(AQUI), 'site', 'index.html')
        fonte = io.open(caminho, encoding='utf-8').read()
        cls.fonte = fonte
        # as cadeias de texto do JavaScript, fora de comentario de bloco
        sem_bloco = re.sub(r'/\*.*?\*/', ' ', fonte, flags=re.S)
        brutos = re.findall(r"'((?:[^'\\]|\\.){12,})'", sem_bloco)
        # so o que e frase: tag HTML e nome de atributo saem, e sobra o texto que
        # alguem le na tela. Trecho com chave, igual ou parentese e codigo.
        frases = []
        for t in brutos:
            limpo = re.sub(r'<[^>]*>', ' ', t)
            limpo = re.sub(r'\s+', ' ', limpo).strip()
            if any(c in limpo for c in '{}=;()[]'):
                continue
            if len(re.findall(r'[A-Za-zÀ-ÿ]{3,}', limpo)) < 3:
                continue
            frases.append(limpo)
        cls.textos = frases

    def test_palavra_que_imputa_conduta_so_entra_negada(self):
        """"Irregularidade" e palavra proibida, e a tela precisa dela.

        No pipeline a regua e simples, porque la a palavra so poderia aparecer
        afirmando. Na tela ela aparece nas ressalvas, que sao o coracao do
        produto: "nao mede irregularidade", "nao e acusacao". A regua aqui e a
        que faz sentido: se a frase nao nega, ela afirma.
        """
        import re
        nega = re.compile(r'\b(não|nao|nunca|nenhum|nenhuma)\b', re.I)
        achados = []
        for t in self.textos:
            baixo = t.lower()
            for p in PROIBIDAS:
                if p in baixo and not nega.search(t):
                    achados.append((p, t[:70]))
        self.assertEqual(achados, [], f'{len(achados)} textos com palavra proibida')

    def test_a_tela_nunca_usa_travessao(self):
        for marca in ('—', '–'):
            self.assertNotIn(marca, self.fonte, f'travessao {marca!r} no site')

    def test_texto_da_tela_sai_acentuado(self):
        import re
        sem_acento = re.compile(
            r'\b(lancamento|lancamentos|fisica|fisicas|proprio|propria|servico|'
            r'servicos|eleicao|declaracao|declaracoes|prestacao|situacao|'
            # 'publica' fica de fora: e verbo comum ('o TSE publica o CPF')
            r'arrecadacao|publico|minimo|padrao|tambem|numero|nao|'
            r'conferencia|indice|codigo|orgao|socio|socios)\b')
        achados = []
        for t in self.textos:
            achados += [(m, t[:70]) for m in sem_acento.findall(t.lower())]
        self.assertEqual(achados, [], f'{len(achados)} palavras sem acento')


class TestHigieneDoFonte(unittest.TestCase):
    """O bug que deixou tres testes de redacao passando com qualquer conteudo.

    Um heredoc de shell decodificou \\b e gravou um caractere de backspace no
    lugar da borda de palavra da expressao regular. O teste passava sempre.
    """

    def test_nenhum_fonte_do_repo_tem_caractere_de_controle(self):
        raiz = os.path.dirname(AQUI)
        proibidos = {chr(c) for c in range(32)} - {'\n', '\r', '\t'}
        achados = []
        for pasta, subs, arquivos in os.walk(raiz):
            subs[:] = [s for s in subs
                       if s not in ('.git', '__pycache__', 'fixtures', 'tmp')]
            for nome in arquivos:
                if not nome.endswith(('.py', '.html', '.yml', '.md')):
                    continue
                caminho = os.path.join(pasta, nome)
                with io.open(caminho, encoding='utf-8', errors='replace') as f:
                    texto = f.read()
                for i, ch in enumerate(texto):
                    if ch in proibidos:
                        achados.append((os.path.relpath(caminho, raiz),
                                        hex(ord(ch)), texto[max(0, i - 30):i + 5]))
        self.assertEqual(achados, [], f'{len(achados)} caracteres de controle')


class TestValorEnvolvido(unittest.TestCase):
    """O valor do sinal alimenta o indice: medir a coisa errada muda a fila."""

    def _despesa(self, sq, doc, num, valor, nome='GRAFICA X'):
        return C.Despesa(
            uf='RR', cargo='6', sq=sq, nr='11', nome='FULANO ' + sq, cpf='',
            partido='XX', prestador='p' + sq, tipo_prest='', tipo_forn='PESSOA JURIDICA',
            cnae='', ds_cnae='', doc=doc, forn=nome, forn_rfb=nome, uf_forn='RR',
            sq_cand_forn='', cargo_forn='', part_forn='', tipo_doc='NOTA',
            num_doc=num, tipo='Material impresso', dt='2026-09-10', valor=valor,
            descricao='')

    def test_d3_mede_a_nota_repetida_e_nao_o_total_do_fornecedor(self):
        """A nota citada no texto e a nota que o 'valor envolvido' mede."""
        aggs, nac = {}, A.Nacional()
        linhas = [
            self._despesa('111', '11222333000181', '900', 2500000),
            self._despesa('222', '11222333000181', '900', 2500000),
            # a mesma grafica fez muito mais coisa para o candidato 111
            self._despesa('111', '11222333000181', '901', 100000000),
        ]
        A.agregar_despesas(iter(linhas), aggs, nac)
        nac.fecha()
        por_cand = al_ritmo.indexar_colisoes(nac, aggs)
        ctx = Contexto(nac, hoje='2026-09-17')
        ctx.colisao_por_cand = por_cand
        sinais = list(al_ritmo.d3_nota_repetida(aggs['111'], ctx))
        self.assertEqual(len(sinais), 1)
        self.assertEqual(sinais[0].valor, 2500000)
        self.assertEqual(aggs['111'].por_forn['11222333000181'][0], 102500000)
        self.assertIn('900', sinais[0].texto)


class TestCotaDeDinheiroPublico(unittest.TestCase):
    """A tela da cota abre pela menor fatia: o denominador tem de ir junto."""

    def _nac_com(self, partido, uf, total, mulheres, sqs):
        nac = A.Nacional()
        f = nac.fundo_partido[(partido, uf)]
        f[0], f[1], f[2] = total, mulheres, 0
        f[3].update(sqs)
        return nac

    def test_unidade_sai_pelo_nome_nunca_como_sigla_crua(self):
        nac = self._nac_com('PL', 'BR', 4200000000, 0, {'1'})
        linha = al_doa.b4_cota(nac)[0]
        self.assertIn('na disputa presidencial', linha['texto'])
        self.assertNotIn(' em BR ', linha['texto'])

    def test_a_preposicao_vem_contraida_com_o_nome_do_estado(self):
        """'em Bahia' e 'em Acre' sao erro de portugues numa tela publica."""
        for uf, esperado in (('BA', 'na Bahia'), ('AC', 'no Acre'),
                             ('SP', 'em São Paulo'), ('RJ', 'no Rio de Janeiro')):
            nac = self._nac_com('PT', uf, 4200000000, 0, {'1', '2'})
            self.assertIn(esperado, al_doa.b4_cota(nac)[0]['texto'])

    def test_recorte_declara_quantas_candidaturas_entram_na_conta(self):
        nac = self._nac_com('PL', 'BR', 4200000000, 0, {'1'})
        linha = al_doa.b4_cota(nac)[0]
        self.assertEqual(linha['n_cands'], 1)
        self.assertIn('1 candidatura', linha['texto'])

    def test_com_muitas_candidaturas_o_plural_acerta(self):
        nac = self._nac_com('PT', 'SP', 9000000000, 1000000000, {'1', '2', '3'})
        linha = al_doa.b4_cota(nac)[0]
        self.assertEqual(linha['n_cands'], 3)
        self.assertIn('3 candidaturas', linha['texto'])


class TestCpfNoNome(unittest.TestCase):
    """O nome do fornecedor MEI traz o CPF inteiro dentro dele.

    A razao social de microempreendedor individual e 'FULANO DE TAL 12345678901'.
    O painel mascara o campo do documento e publicava o numero completo no campo
    ao lado, no nome, que e o texto mais visivel da ficha.
    """

    def test_cpf_valido_sai_do_nome(self):
        from pipeline.carregar import limpar_nome
        self.assertEqual(limpar_nome('JOSE DA SILVA 11144477735'), 'JOSE DA SILVA')
        self.assertEqual(limpar_nome('11144477735 JOSE DA SILVA'), 'JOSE DA SILVA')

    def test_numero_que_nao_e_cpf_fica(self):
        from pipeline.carregar import limpar_nome
        # digito verificador nao confere: e outro numero qualquer, e apagar seria
        # inventar um corte no nome de alguem
        self.assertEqual(limpar_nome('TRANSPORTES 12345678901'),
                         'TRANSPORTES 12345678901')
        self.assertEqual(limpar_nome('GRAFICA 2026 LTDA'), 'GRAFICA 2026 LTDA')

    def test_nome_nunca_fica_vazio(self):
        from pipeline.carregar import limpar_nome
        self.assertEqual(limpar_nome('11144477735'), '11144477735')

    def test_a_fixture_real_nao_publica_cpf_em_nome_nenhum(self):
        import re
        z = zipfile.ZipFile(os.path.join(FIX, 'candidatos.zip'))
        aggs, nac = {}, A.Nacional()
        A.agregar_despesas(C.despesas(z, 'RR'), aggs, nac)
        onze = re.compile(r'(?<!\d)\d{11}(?!\d)')
        sobrou = []
        for doc, e in nac.fornecedores.items():
            for achado in onze.findall(e[2] or ''):
                if C.cpf_valido(achado):
                    sobrou.append((doc, e[2]))
        self.assertEqual(sobrou, [], f'{len(sobrou)} nomes com CPF dentro')


class TestIdentificadorDeFornecedor(unittest.TestCase):
    """O endereco da ficha nao pode ser o CPF, nem coisa que volte para ele."""

    def test_cnpj_e_o_proprio_numero(self):
        from pipeline.ident import ident
        self.assertEqual(ident('11222333000181'), '11222333000181')

    def test_cpf_nunca_aparece_no_identificador(self):
        from pipeline.ident import ident
        cpf = '12345678901'
        i = ident(cpf)
        self.assertTrue(i.startswith('p'))
        self.assertNotIn(cpf, i)
        for pedaco in (cpf[:3], cpf[3:6], cpf[6:9]):
            self.assertNotIn(pedaco, i)

    def test_o_mesmo_documento_cai_sempre_no_mesmo_endereco(self):
        from pipeline.ident import ident, bloco
        a, b = ident('12345678901'), ident('12345678901')
        self.assertEqual(a, b)
        self.assertEqual(bloco(a), bloco(b))
        self.assertTrue(0 <= bloco(a) < 256)

    def test_a_chave_do_ambiente_muda_o_identificador(self):
        from pipeline import ident as I
        antes = os.environ.get('CONTAS_SAL')
        try:
            os.environ['CONTAS_SAL'] = 'uma-chave'
            um = I.ident('12345678901')
            os.environ['CONTAS_SAL'] = 'outra-chave'
            outro = I.ident('12345678901')
            self.assertNotEqual(um, outro)
            self.assertTrue(I.tem_sal_de_verdade())
        finally:
            if antes is None:
                os.environ.pop('CONTAS_SAL', None)
            else:
                os.environ['CONTAS_SAL'] = antes

    def test_o_estado_nao_guarda_documento_de_pessoa_fisica(self):
        """O arquivo de fornecedores vistos ficava em texto puro, com CPF."""
        tmp = tempfile.mkdtemp()
        antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.addCleanup(lambda: os.environ.pop('CONTAS_SAL', None) if antes is None
                        else os.environ.__setitem__('CONTAS_SAL', antes))
        try:
            nac = A.Nacional()
            nac.fornecedores = {'12345678901': [100, 1, 'FULANO', '', '', 1],
                                '11222333000181': [200, 1, 'EMPRESA', '', '', 1]}
            H.gravar(tmp, '2026-09-17', nac, {})
            texto = io.open(os.path.join(tmp, 'fornecedores-vistos.txt'),
                            encoding='utf-8').read()
            self.assertNotIn('12345678901', texto)
            self.assertIn('11222333000181', texto)
            vistos, _, _ = H.carregar(tmp, '2026-09-18')
            # e o pipeline continua sabendo que ja viu aquele fornecedor
            self.assertIn('12345678901', vistos)
            self.assertIn('11222333000181', vistos)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestFichaDeFornecedor(unittest.TestCase):
    """A ficha de quem recebe: quem e, quem sao os donos, quem pagou."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.nac = A.Nacional()
        self.nac.fornecedores = {
            '11222333000181': [500000, 3, 'GRAFICA BOA LTDA', 'PESSOA JURIDICA',
                               '1813099', 2, '', 0],
            # abaixo do piso da ficha de pessoa fisica, de proposito
            '12345678901': [90000, 1, 'FULANA DE TAL', 'PESSOA FISICA', '', 1, '', 0],
        }
        self.nac.forn_cands = {
            '11222333000181': {'111': 300000, '222': 200000},
            '12345678901': {'111': 90000},
        }
        self.aggs = {}
        for sq, nome in (('111', 'CANDIDATO UM'), ('222', 'CANDIDATA DOIS')):
            ag = A.Agg(sq)
            ag.uf, ag.cargo, ag.nome, ag.partido, ag.nr = 'RR', '6', nome, 'ZZ', '10'
            ag.contratado = 1000000
            self.aggs[sq] = ag
        self.dics = {k: E.Dic() for k in ('tipo', 'partido', 'fed', 'alarme')}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _escrever(self, receita=None, alarmes=None):
        return E.escrever_fornecedores_fichas(
            self.nac, self.aggs, receita or {}, {}, alarmes or [], self.tmp)

    def _bloco_de(self, doc):
        from pipeline.ident import bloco, ident
        i = ident(doc)
        caminho = os.path.join(self.tmp, 'forn', f'{bloco(i, self.blocos)}.json')
        return json.load(open(caminho, encoding='utf-8'))['f'][i]

    def test_a_ficha_diz_quais_candidaturas_pagaram_e_quanto(self):
        self.blocos = self._escrever()['blocos']
        f = self._bloco_de('11222333000181')
        pagantes = {c[1]: c[5] for c in f['cands']}
        self.assertEqual(pagantes, {'CANDIDATO UM': 300000, 'CANDIDATA DOIS': 200000})
        self.assertEqual(f['valor'], 500000)
        self.assertEqual(f['n_camp'], 2)

    def test_os_socios_entram_quando_a_receita_ja_respondeu(self):
        receita = {'11222333000181': {
            'razao_social': 'GRAFICA BOA LTDA', 'situacao_cadastral': 'Ativa',
            'data_inicio_atividade': '2019-03-01',
            'natureza_juridica': 'Sociedade Empresária Limitada',
            'porte_empresa': 'MICRO EMPRESA',
            'socios': ['MARIA DOS SANTOS', 'JOAO PEREIRA']}}
        self.blocos = self._escrever(receita=receita)['blocos']
        f = self._bloco_de('11222333000181')
        self.assertEqual(f['cadastro']['socios'], ['MARIA DOS SANTOS', 'JOAO PEREIRA'])
        self.assertEqual(f['cadastro']['situacao'], 'Ativa')

    def test_pessoa_fisica_tem_ficha_sem_o_cpf_aparecer_em_lugar_nenhum(self):
        antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.addCleanup(lambda: os.environ.pop('CONTAS_SAL', None) if antes is None
                        else os.environ.__setitem__('CONTAS_SAL', antes))
        self.nac.fornecedores['12345678901'][0] = 5000000      # acima do piso
        self.blocos = self._escrever()['blocos']
        f = self._bloco_de('12345678901')
        self.assertEqual(f['nome'], 'FULANA DE TAL')
        self.assertEqual(f['doc'], '***.456.789-**')
        self.assertNotIn('cadastro', f)
        bruto = io.open(os.path.join(self.tmp, 'forn', os.listdir(
            os.path.join(self.tmp, 'forn'))[0]), encoding='utf-8').read()
        for arquivo in os.listdir(os.path.join(self.tmp, 'forn')):
            bruto = io.open(os.path.join(self.tmp, 'forn', arquivo),
                            encoding='utf-8').read()
            self.assertNotIn('12345678901', bruto)

    def test_sem_a_chave_do_ambiente_a_ficha_de_pessoa_fisica_nao_e_escrita(self):
        """Sem CONTAS_SAL o identificador de CPF volta por forca bruta.

        Dez elevado a onze combinacoes caem em segundos numa placa de video, e o
        identificador vai publicado na URL. Sem a chave, a ficha de pessoa fisica
        nao sai; a de empresa sai, porque CNPJ e publico por natureza.
        """
        antes = os.environ.pop('CONTAS_SAL', None)
        try:
            saida = self._escrever()
            achadas = []
            for nome in os.listdir(os.path.join(self.tmp, 'forn')):
                d = json.load(open(os.path.join(self.tmp, 'forn', nome), encoding='utf-8'))
                achadas += list(d['f'])
            self.assertIn('11222333000181', achadas)
            self.assertFalse([x for x in achadas if x.startswith('p')])
            self.assertEqual(saida['pessoas_fora'], 1)
        finally:
            if antes is not None:
                os.environ['CONTAS_SAL'] = antes

    def test_com_a_chave_a_ficha_de_pessoa_fisica_sai(self):
        antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.nac.fornecedores['12345678901'][0] = 5000000      # acima do piso
        try:
            saida = self._escrever()
            achadas = []
            for nome in os.listdir(os.path.join(self.tmp, 'forn')):
                d = json.load(open(os.path.join(self.tmp, 'forn', nome), encoding='utf-8'))
                achadas += list(d['f'])
            self.assertTrue([x for x in achadas if x.startswith('p')])
            self.assertEqual(saida['pessoas_fora'], 0)
        finally:
            if antes is None:
                os.environ.pop('CONTAS_SAL', None)
            else:
                os.environ['CONTAS_SAL'] = antes

    def test_pessoa_fisica_abaixo_do_piso_nao_ganha_ficha(self):
        """Quem prestou um servico pequeno nao vira pagina.

        Medido em Roraima: 9.082 fornecedores pessoa fisica, e o piso de R$ 10
        mil deixa 455 deles (5 %), cobrindo 37,5 % de tudo que foi pago a pessoa
        fisica. Empresa nao tem piso: CNPJ e publico por natureza.
        """
        antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.addCleanup(lambda: os.environ.pop('CONTAS_SAL', None) if antes is None
                        else os.environ.__setitem__('CONTAS_SAL', antes))
        # a pessoa fisica da fixture recebeu R$ 900, abaixo do piso
        saida = self._escrever()
        achadas = []
        for nome in os.listdir(os.path.join(self.tmp, 'forn')):
            d = json.load(open(os.path.join(self.tmp, 'forn', nome), encoding='utf-8'))
            achadas += list(d['f'])
        self.assertIn('11222333000181', achadas)
        self.assertFalse([x for x in achadas if x.startswith('p')])
        self.assertEqual(saida['pessoas_pequenas'], 1)

    def test_pessoa_fisica_acima_do_piso_ganha_ficha(self):
        antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.addCleanup(lambda: os.environ.pop('CONTAS_SAL', None) if antes is None
                        else os.environ.__setitem__('CONTAS_SAL', antes))
        self.nac.fornecedores['12345678901'][0] = 5000000      # R$ 50 mil
        saida = self._escrever()
        achadas = []
        for nome in os.listdir(os.path.join(self.tmp, 'forn')):
            d = json.load(open(os.path.join(self.tmp, 'forn', nome), encoding='utf-8'))
            achadas += list(d['f'])
        self.assertTrue([x for x in achadas if x.startswith('p')])
        self.assertEqual(saida['pessoas_pequenas'], 0)

    def test_o_sinal_do_fornecedor_vai_junto_com_a_ressalva_do_codigo(self):
        from pipeline.alarmes import Alarme
        al = [Alarme('A1', 2, '111', '11222333000181', 300000,
                     'A empresa foi aberta 40 dias antes da primeira despesa.')]
        self.blocos = self._escrever(alarmes=al)['blocos']
        f = self._bloco_de('11222333000181')
        self.assertEqual(f['sinais'][0][0], 'A1')
        self.assertIn('40 dias', f['sinais'][0][2])


class TestRecorteDeFornecedores(unittest.TestCase):
    """Quem recebeu, por unidade e por recorte de partido e cargo.

    A tela de fornecedor obedece aos mesmos filtros das outras, e a linha do
    ranking nao diz quem recebeu: este agregado e a unica forma de responder
    "quem recebeu do PT em Roraima" sem baixar 419 mil fichas.
    """

    @classmethod
    def setUpClass(cls):
        # a classe mede o caminho SEM a chave, que e a rodada de quem
        # desenvolve: nela nenhuma pessoa fisica pode ganhar endereco
        cls.antes = os.environ.pop('CONTAS_SAL', None)
        cls.tmp = tempfile.mkdtemp()
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
        cls.recortes = A.recorte_fornecedores(cls.aggs)
        cls.dics = {k: E.Dic() for k in ('tipo', 'partido', 'fed', 'alarme')}
        # o dicionario de partido nasce no ranking, e o recorte carrega o mesmo
        # indice: a ordem tem de ser a mesma dos dois lados
        E.escrever_uf('RR', list(cls.aggs.values()), {}, cls.dics, cls.tmp)
        cls.rec = cls._grava(cls.tmp, cls.dics)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        if cls.antes is not None:
            os.environ['CONTAS_SAL'] = cls.antes

    @classmethod
    def _grava(cls, destino, dics):
        saida = {}
        for unidade, recorte in cls.recortes.items():
            E.escrever_forn_recorte(unidade, recorte, cls.nac, dics, destino)
            saida[unidade] = json.load(open(
                os.path.join(destino, 'forn-recorte', f'{unidade}.json'),
                encoding='utf-8'))
        return saida

    def _todas(self, r):
        """Cada lista do arquivo, para as travas valerem em todas elas."""
        yield r['geral']
        yield r['geral_por_camp']
        for chave in ('partido', 'cargo', 'celula'):
            for lista in r[chave].values():
                yield lista

    def test_o_geral_e_o_topo_por_valor_e_conta_quem_ficou_de_fora(self):
        """Roraima tem 9.581 fornecedores: 200 na lista, 9.381 contados.

        O total do recorte, R$ 69.083.282,65, e MENOR que o contratado da UF,
        R$ 69.090.926,05, e tem de ser: 660 linhas de despesa nao trazem
        documento de fornecedor e somam R$ 7.643,40 que existem no contratado e
        nao tem a quem ser atribuidos.
        """
        g = self.rec['RR']['geral']
        self.assertEqual(len(g), A.TOPO_RECORTE_GERAL)
        valores = [e[4] for e in g]
        self.assertEqual(valores, sorted(valores, reverse=True))
        fora = self.rec['RR']['fora']['geral']
        self.assertEqual(fora[0], len(self.nac.fornecedores) - len(g))
        self.assertEqual(fora[0], 9381)
        total = sum(valores) + fora[1]
        self.assertEqual(total, 6908328265)
        self.assertLess(total, sum(a.contratado for a in self.aggs.values()))

    def test_por_candidaturas_ordena_por_quantas_campanhas_pagaram(self):
        c = self.rec['RR']['geral_por_camp']
        campanhas = [e[5] for e in c]
        self.assertEqual(campanhas, sorted(campanhas, reverse=True))
        # e nao e a lista do valor em outra ordem: quem atende muita campanha
        # pequena nao e quem recebeu mais
        self.assertNotEqual([e[0] for e in c],
                            [e[0] for e in self.rec['RR']['geral']])
        fora = self.rec['RR']['fora']['geral_por_camp']
        self.assertEqual(sum(e[4] for e in c) + fora[1], 6908328265)

    def test_partido_cargo_e_celula_somam_o_mesmo_que_o_geral(self):
        r = self.rec['RR']
        fora = r['fora']

        def soma(listas, chave):
            total = 0
            for nome, lista in listas.items():
                total += sum(e[4] for e in lista)
                total += (fora.get(chave(nome)) or [0, 0])[1]
            return total

        total = sum(e[4] for e in r['geral']) + fora['geral'][1]
        self.assertEqual(soma(r['partido'], lambda p: f'p:{p}'), total)
        self.assertEqual(soma(r['cargo'], lambda c: f'c:{c}'), total)
        self.assertEqual(soma(r['celula'], lambda k: 'p:{}:c:{}'.format(
            *k.split(':'))), total)

    def test_a_celula_bate_com_a_conta_feita_a_mao(self):
        chave = sorted(self.rec['RR']['celula'])[0]
        pid, _, cargo = chave.partition(':')
        partido = self.dics['partido'].lista[int(pid)]
        mao = {}
        for a in self.aggs.values():
            if (a.partido or '') != partido or a.cargo != cargo:
                continue
            for doc, e in a.por_forn.items():
                x = mao.setdefault(doc, [0, 0, 0])
                x[0] += e[0]
                x[1] += 1
                x[2] += e[1]
        lista = self.rec['RR']['celula'][chave]
        fora = self.rec['RR']['fora'].get(f'p:{pid}:c:{cargo}') or [0, 0]
        self.assertEqual(len(mao), len(lista) + fora[0])
        self.assertEqual(sum(x[0] for x in mao.values()),
                         sum(e[4] for e in lista) + fora[1])
        maior = max(mao.items(), key=lambda kv: (kv[1][0], kv[0]))
        self.assertEqual(lista[0][2], C.mascara(maior[0]))
        self.assertEqual(lista[0][4:7], maior[1])

    def test_o_partido_e_o_indice_do_dicionario_do_ranking(self):
        uf = json.load(open(os.path.join(self.tmp, 'uf', 'RR.json'),
                            encoding='utf-8'))
        do_ranking = {l[3] for l in uf['c']}
        for pid in self.rec['RR']['partido']:
            self.assertIn(int(pid), do_ranking)
        pid = uf['c'][0][3]
        partido = self.dics['partido'].lista[pid]
        mao = sum(sum(e[0] for e in a.por_forn.values())
                  for a in self.aggs.values() if (a.partido or '') == partido)
        lista = self.rec['RR']['partido'][str(pid)]
        fora = self.rec['RR']['fora'].get(f'p:{pid}') or [0, 0]
        self.assertEqual(mao, sum(e[4] for e in lista) + fora[1])

    def test_pessoa_fisica_sai_mascarada_e_o_cpf_nao_aparece_no_arquivo(self):
        cpfs = [d for d in self.nac.fornecedores if len(d) == 11]
        self.assertEqual(len(cpfs), 9082)
        for unidade in ('RR', 'BRASIL'):
            bruto = io.open(os.path.join(self.tmp, 'forn-recorte',
                                         f'{unidade}.json'),
                            encoding='utf-8').read()
            self.assertEqual([c for c in cpfs if c in bruto], [])
        pf = [e for e in self.rec['RR']['geral'] if not e[3]]
        self.assertTrue(pf)
        self.assertTrue(all('*' in e[2] for e in pf))

    def test_sem_a_chave_nenhuma_pessoa_fisica_ganha_endereco_nem_ficha(self):
        self.assertIsNone(os.environ.get('CONTAS_SAL'))
        pessoas = 0
        for unidade in ('RR', 'BRASIL'):
            for lista in self._todas(self.rec[unidade]):
                for e in lista:
                    if e[3]:
                        continue
                    pessoas += 1
                    self.assertEqual(e[0], '')
                    self.assertEqual(e[7], 0)
        self.assertTrue(pessoas)

    def test_com_a_chave_so_a_pessoa_fisica_acima_do_piso_ganha_endereco(self):
        from pipeline.ident import ident
        outro = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outro, True)
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.addCleanup(lambda: os.environ.pop('CONTAS_SAL', None))
        rec = self._grava(outro, {k: E.Dic() for k in
                                  ('tipo', 'partido', 'fed', 'alarme')})
        valor = {ident(d): e[0] for d, e in self.nac.fornecedores.items()
                 if len(d) == 11}
        com = sem = 0
        for unidade in ('RR', 'BRASIL'):
            for lista in self._todas(rec[unidade]):
                for e in lista:
                    if e[3]:
                        continue
                    if e[0]:
                        com += 1
                        self.assertTrue(e[0].startswith('p'))
                        self.assertGreaterEqual(valor[e[0]], E.PISO_FICHA_PF)
                    else:
                        sem += 1
                        self.assertEqual(e[7], 0)
        self.assertTrue(com)
        self.assertTrue(sem)

    def test_tem_ficha_segue_o_total_nacional_e_nao_o_da_unidade(self):
        """R$ 300 em Roraima e R$ 50 mil no Amazonas: a ficha existe nos dois.

        O piso da ficha de pessoa fisica e medido na eleicao inteira. Se a
        lista da UF decidisse pelo valor dela, o mesmo fornecedor apareceria com
        link numa tela e sem link na outra.
        """
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.addCleanup(lambda: os.environ.pop('CONTAS_SAL', None))
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        cpf = '11144477735'
        aggs = {}
        for sq, uf, valor in (('1', 'RR', 30000), ('2', 'AM', 5000000)):
            ag = A.Agg(sq)
            ag.uf, ag.cargo, ag.partido, ag.nome = uf, '6', 'ZZ', 'CANDIDATO'
            ag.por_forn = {cpf: [valor, 1, 'FULANA DE TAL', 'PESSOA FISICA',
                                 '', '', '', valor]}
            aggs[sq] = ag
        nac = A.Nacional()
        nac.fornecedores = {cpf: [5030000, 2, 'FULANA DE TAL', 'PESSOA FISICA',
                                  '', 2, '', 0]}
        dics = {k: E.Dic() for k in ('tipo', 'partido', 'fed', 'alarme')}
        for unidade, recorte in A.recorte_fornecedores(aggs).items():
            E.escrever_forn_recorte(unidade, recorte, nac, dics, tmp)
        rr = json.load(open(os.path.join(tmp, 'forn-recorte', 'RR.json'),
                            encoding='utf-8'))
        e = rr['geral'][0]
        self.assertEqual(e[4], 30000)
        self.assertEqual(e[7], 1)
        self.assertTrue(e[0].startswith('p'))

    def test_a_lista_nao_passa_do_topo_e_os_grupos_pequenos_vem_inteiros(self):
        r = self.rec['RR']
        self.assertLessEqual(len(r['geral']), A.TOPO_RECORTE_GERAL)
        for pid, lista in r['partido'].items():
            self.assertLessEqual(len(lista), A.TOPO_RECORTE_PARTIDO)
            if len(lista) < A.TOPO_RECORTE_PARTIDO:
                self.assertNotIn(f'p:{pid}', r['fora'])
        for cargo, lista in r['cargo'].items():
            self.assertLessEqual(len(lista), A.TOPO_RECORTE_CARGO)
        pequenas = 0
        for chave, lista in r['celula'].items():
            self.assertLessEqual(len(lista), A.TOPO_RECORTE_CELULA)
            pid, _, cargo = chave.partition(':')
            if len(lista) < A.TOPO_RECORTE_CELULA:
                pequenas += 1
                self.assertNotIn(f'p:{pid}:c:{cargo}', r['fora'])
        self.assertTrue(pequenas)


class TestPontaAPonta(unittest.TestCase):
    def setUp(self):
        # a rodada de producao exige a chave que torna o identificador de pessoa
        # fisica irreversivel; o teste roda o mesmo caminho
        self.antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'

    def tearDown(self):
        if self.antes is None:
            os.environ.pop('CONTAS_SAL', None)
        else:
            os.environ['CONTAS_SAL'] = self.antes

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
            # A receita por origem saiu da linha do ranking em 17/09: ela
            # alimentava um filtro que lia a coluna errada do TSE (origem em
            # vez de fonte) e custava 100 KB no arquivo do pais. A pergunta
            # continua respondida na ficha, que traz origens e fontes lado a
            # lado, com o nome que o TSE usa para cada uma.
            self.assertNotIn('origem', meta['dic'])
            br = json.load(open(os.path.join(site, 'uf', 'BRASIL.json'),
                                encoding='utf-8'))
            self.assertTrue(all(len(l) == 17 for l in br['c']))
            self.assertTrue(all(l[16] == 'RR' for l in br['c']))
            # o campo 15 e a receita publica, e entrou para a coluna de cota de
            # genero na visao por partido: o campo 9 e pagamento, e a fatia de
            # 30 % que a Constituicao manda medir e sobre a receita
            self.assertEqual(sum(l[15] for l in br['c']),
                             sum(l[15] for l in uf['c']))
            self.assertGreater(sum(l[15] for l in uf['c']), 0)
            # o tipo de gasto por candidatura tambem saiu do arquivo do pais:
            # era 36 % dele, e o painel de tipos passa a ser o agregado
            self.assertTrue(all(l[11] == [] for l in br['c']))
            self.assertIn('tipos', br)
            self.assertGreater(len(br['tipos']), 5)
            self.assertEqual(sum(l[6] for l in br['c']), 6909092605)
            self.assertIn('RR', meta['nome_uf'])
            self.assertEqual(meta['nome_uf']['BR'] if 'BR' in meta['nome_uf']
                             else 'Presidência', 'Presidência')
            # ranking em ordem decrescente de gasto
            gastos = [l[6] for l in uf['c']]
            self.assertEqual(gastos, sorted(gastos, reverse=True))
            # o recorte de fornecedor sai por unidade e para o pais, e com uma
            # UF so os dois sao a mesma lista
            # o panorama e a lista nacional de fornecedores sairam em 18/09: a
            # tela agrupa no front, sobre as linhas ja filtradas, e quem recebeu
            # vem do recorte por unidade
            for morto in ('panorama.json', 'fornecedores.json'):
                self.assertFalse(os.path.exists(os.path.join(site, morto)), morto)
            rec = os.path.join(site, 'forn-recorte')
            r_rr = json.load(open(os.path.join(rec, 'RR.json'), encoding='utf-8'))
            r_br = json.load(open(os.path.join(rec, 'BRASIL.json'),
                                  encoding='utf-8'))
            self.assertEqual(r_br['geral'], r_rr['geral'])
            # e o validador reprova o que quebra a trava do CPF ou o link da
            # ficha, que e o que este arquivo tem de mais delicado
            for campo, valor in ((2, '111.444.777-35'), (0, '')):
                d = json.loads(json.dumps(r_rr))
                d['geral'][0][campo] = valor
                d['geral'][0][7] = 1
                with open(os.path.join(rec, 'RR.json'), 'w',
                          encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False)
                self.assertTrue(V.validar(site))
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
            # sem CONTAS_SAL a rodada guarda so os CNPJ: pessoa fisica nao ganha
            # identificador publicavel, e o teste mede o que de fato e gravado
            self.assertGreater(len(vistos), 400)
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
