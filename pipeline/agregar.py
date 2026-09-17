#!/usr/bin/env python3
"""Soma o dado bruto do TSE em duas estruturas: uma por candidato, uma nacional.

A estrutura por candidato e o que vira ficha e ranking. A nacional existe para
as perguntas que so aparecem quando se olha o pais inteiro: um fornecedor que
atende 5.183 candidaturas, um numero de nota que aparece em duas contas, um
doador que financia dez campanhas.

Uma passada por arquivo. Nada e lido duas vezes.
"""
import collections

# Cargo por codigo, do proprio TSE. So estes entram no painel: suplente de
# senador nao tem prestacao propria e vice concorre na chapa.
CARGOS = {
    '1': 'Presidente', '2': 'Vice-presidente', '3': 'Governador',
    '4': 'Vice-governador', '5': 'Senador', '6': 'Deputado Federal',
    '7': 'Deputado Estadual', '8': 'Deputado Distrital',
    '9': '1º Suplente', '10': '2º Suplente',
}
CARGOS_PAINEL = ('1', '3', '5', '6', '7', '8')

# O TSE chama de SG_UF a unidade eleitoral, e para os cargos nacionais ela e
# 'BR'. Na tela isso precisa ter nome, senao 'BR' parece uma sigla de estado
# que ninguem reconhece.
NOME_UF = {
    'BR': 'Presidência', 'BRASIL': 'Brasil inteiro',
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas',
    'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal',
    'ES': 'Espírito Santo', 'GO': 'Goiás', 'MA': 'Maranhão',
    'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais',
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco',
    'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima',
    'SC': 'Santa Catarina', 'SP': 'São Paulo', 'SE': 'Sergipe',
    'TO': 'Tocantins',
}

# Receita que e dinheiro publico. Sai do bolso de todo mundo, entao e o corte
# que mais interessa a quem le.
FONTES_PUBLICAS = ('FUNDO ESPECIAL', 'FUNDO PARTIDARIO', 'FUNDO PARTIDÁRIO')


def publica(fonte):
    f = (fonte or '').upper()
    return any(p in f for p in FONTES_PUBLICAS)


class Agg:
    """O que se sabe sobre o dinheiro de um candidato."""
    __slots__ = ('sq', 'uf', 'cargo', 'nr', 'nome', 'partido', 'cpf', 'fed',
                 'prestadores', 'tipo_prest',
                 'contratado', 'pago', 'pago_publico',
                 'receita', 'estimavel', 'receita_publica',
                 'n_despesas', 'por_tipo', 'por_forn', 'por_dia',
                 'por_origem', 'por_fonte_paga', 'por_doador',
                 'primeira', 'ultima', 'genero', 'cor_raca')

    def __init__(self, sq):
        self.sq = sq
        self.uf = self.cargo = self.nr = self.nome = self.partido = self.cpf = ''
        self.fed = ''
        self.genero = self.cor_raca = ''
        self.prestadores = set()
        self.tipo_prest = ''
        self.contratado = self.pago = self.pago_publico = 0
        self.receita = self.estimavel = self.receita_publica = 0
        self.n_despesas = 0
        self.por_tipo = collections.Counter()
        self.por_forn = {}          # doc -> [valor, n, nome, tipo_forn, cnae, sq_cand_forn]
        self.por_dia = collections.Counter()
        self.por_origem = collections.Counter()
        self.por_fonte_paga = collections.Counter()
        self.por_doador = {}        # doc -> [valor, n, nome, origem]
        self.primeira = self.ultima = ''

    @property
    def movimento(self):
        return self.contratado or self.pago or self.receita or self.estimavel


class Nacional:
    """O que so se ve olhando o pais inteiro."""

    def __init__(self):
        # doc -> [valor, n_linhas, nome, tipo_forn, cnae, n_candidatos]
        self.fornecedores = {}
        self._forn_cands = collections.defaultdict(set)
        # 'doc|numero' -> [sq...] quando a mesma nota aparece em mais de um
        self.docs_vistos = {}
        self.docs_colisao = collections.defaultdict(set)
        self.doadores = {}
        self._doador_cands = collections.defaultdict(set)
        # (partido, uf) -> [publico_total, publico_para_mulheres, publico_para_negros]
        self.fundo_partido = collections.defaultdict(lambda: [0, 0, 0])
        self.cargos = collections.Counter()
        # o proprio arquivo do TSE traz o nome de cada CNAE; nao
        # precisa de tabela mantida a mao
        self.cnae_nome = {}
        self.data_max = ''
        self.n_despesas = self.n_receitas = self.n_pagas = 0
        self.total_contratado = self.total_pago = self.total_receita = 0
        # Ha declaracao com data no futuro: em RR, 5 despesas, uma delas em
        # 10/10, depois do pleito. E erro de digitacao de quem declarou. O
        # painel conta quantas sao e nao deixa isso virar "dados ate 10/10".
        self.datas_no_futuro = 0
        self.hoje = ''

    def fecha(self):
        for doc, cands in self._forn_cands.items():
            if doc in self.fornecedores:
                self.fornecedores[doc][5] = len(cands)
        for doc, cands in self._doador_cands.items():
            if doc in self.doadores:
                self.doadores[doc][4] = len(cands)
        self._forn_cands.clear()
        self._doador_cands.clear()
        self.docs_vistos.clear()


def _bota_forn(mapa, doc, valor, nome, tipo_forn, cnae, sq_cand_forn='', tipo=''):
    """Acumula um fornecedor.

    O indice 6 guarda o tipo de despesa do MAIOR lancamento daquele fornecedor
    para aquele candidato. E o que o alarme A4 compara com a atividade da
    empresa: comparar com o gasto dominante do candidato inteiro acusaria a
    grafica pelo combustivel que outro fornecedor vendeu.
    """
    e = mapa.get(doc)
    if e is None:
        mapa[doc] = [valor, 1, nome, tipo_forn, cnae, sq_cand_forn, tipo, valor]
        return
    e[0] += valor
    e[1] += 1
    if not e[2] and nome:
        e[2] = nome
    if not e[4] and cnae:
        e[4] = cnae
    if not e[5] and sq_cand_forn:
        e[5] = sq_cand_forn
    if valor > e[7]:
        e[6], e[7] = tipo, valor


def agregar_despesas(fluxo, aggs, nac):
    """Uma passada pelas despesas contratadas. Soma TODAS as linhas.

    O porque de somar tudo esta no docstring de carregar.py: SQ_DESPESA
    agrupa itens de uma nota, nao identifica linha.
    """
    for d in fluxo:
        if d.cargo not in CARGOS_PAINEL or not d.sq:
            continue
        a = aggs.get(d.sq)
        if a is None:
            a = aggs[d.sq] = Agg(d.sq)
            a.uf, a.cargo, a.nr = d.uf, d.cargo, d.nr
            a.nome, a.partido, a.cpf = d.nome, d.partido, d.cpf
        a.prestadores.add(d.prestador)
        if d.tipo_prest:
            a.tipo_prest = d.tipo_prest
        a.contratado += d.valor
        a.n_despesas += 1
        a.por_tipo[d.tipo or 'Não informado'] += d.valor
        if d.dt:
            a.por_dia[d.dt] += d.valor
            if not a.primeira or d.dt < a.primeira:
                a.primeira = d.dt
            if d.dt > a.ultima:
                a.ultima = d.dt
            if nac.hoje and d.dt > nac.hoje:
                nac.datas_no_futuro += 1
            elif d.dt > nac.data_max:
                nac.data_max = d.dt
        nome_forn = d.forn_rfb or d.forn
        if d.doc:
            _bota_forn(a.por_forn, d.doc, d.valor, nome_forn, d.tipo_forn,
                       d.cnae, d.sq_cand_forn, d.tipo)
            _bota_forn(nac.fornecedores, d.doc, d.valor, nome_forn, d.tipo_forn,
                       d.cnae, d.sq_cand_forn, d.tipo)
            if d.cnae and d.ds_cnae and d.cnae not in nac.cnae_nome:
                nac.cnae_nome[d.cnae] = d.ds_cnae
            nac._forn_cands[d.doc].add(d.sq)
            if d.num_doc:
                chave = f'{d.doc}|{d.num_doc}'
                antes = nac.docs_vistos.get(chave)
                if antes is None:
                    nac.docs_vistos[chave] = d.sq
                elif antes != d.sq:
                    nac.docs_colisao[chave].add(antes)
                    nac.docs_colisao[chave].add(d.sq)
        nac.n_despesas += 1
        nac.total_contratado += d.valor
        nac.cargos[d.cargo] += 1


def agregar_pagas(fluxo, aggs, nac, prestador_para_sq):
    """As pagas nao trazem candidato: ligam pelo SQ_PRESTADOR_CONTAS.

    Medido em AC e RR: 100 % das linhas ligam. A fonte da despesa diz se o
    dinheiro que pagou era publico, e isso e o corte que mais interessa.
    """
    for p in fluxo:
        sq = prestador_para_sq.get(p.prestador)
        if not sq:
            continue
        a = aggs.get(sq)
        if a is None:
            continue
        a.pago += p.valor
        a.por_fonte_paga[p.fonte or 'Não informada'] += p.valor
        if publica(p.fonte):
            a.pago_publico += p.valor
        nac.n_pagas += 1
        nac.total_pago += p.valor


def agregar_receitas(fluxo, aggs, nac):
    for r in fluxo:
        if r.cargo not in CARGOS_PAINEL or not r.sq:
            continue
        a = aggs.get(r.sq)
        if a is None:
            a = aggs[r.sq] = Agg(r.sq)
            a.uf, a.cargo, a.partido = r.uf, r.cargo, r.partido
        if not a.genero:
            a.genero, a.cor_raca = r.genero, r.cor_raca
        estimavel = r.natureza.upper().startswith('ESTIM')
        if estimavel:
            a.estimavel += r.valor
        else:
            a.receita += r.valor
        a.por_origem[r.origem or 'Não informada'] += r.valor
        if publica(r.fonte):
            a.receita_publica += r.valor
            f = nac.fundo_partido[(r.partido, r.uf)]
            f[0] += r.valor
            if (r.genero or '').upper().startswith('F'):
                f[1] += r.valor
            if (r.cor_raca or '').upper() in ('PRETA', 'PARDA'):
                f[2] += r.valor
        if r.doc:
            nome = r.doador_rfb or r.doador
            e = a.por_doador.get(r.doc)
            if e is None:
                a.por_doador[r.doc] = [r.valor, 1, nome, r.origem]
            else:
                e[0] += r.valor
                e[1] += 1
            e = nac.doadores.get(r.doc)
            if e is None:
                nac.doadores[r.doc] = [r.valor, 1, nome, r.origem, 0]
            else:
                e[0] += r.valor
                e[1] += 1
            nac._doador_cands[r.doc].add(r.sq)
        nac.n_receitas += 1
        nac.total_receita += r.valor


def juntar_candidaturas(cands, aggs):
    """Casa a lista mestra de candidaturas com quem tem movimento.

    Quem esta na lista e nao gastou entra com zero, porque 'nao declarou nada'
    tambem e informacao. Quem gastou e nao esta na lista fica com o que a
    propria despesa diz, e sai marcado.
    """
    sem_ficha = 0
    for c in cands:
        if c.cargo not in CARGOS_PAINEL:
            continue
        a = aggs.get(c.sq)
        if a is None:
            a = aggs[c.sq] = Agg(c.sq)
        a.uf = a.uf or c.uf
        a.cargo = a.cargo or c.cargo
        a.nr = c.nr or a.nr
        a.nome = c.urna or a.nome
        a.partido = c.partido or a.partido
        a.cpf = a.cpf or c.cpf
        a.genero = a.genero or c.genero
        a.cor_raca = a.cor_raca or c.cor_raca
        a.fed = c.fed or a.fed
    ficha = {c.sq for c in cands}
    for sq, a in aggs.items():
        if sq not in ficha:
            sem_ficha += 1
    return sem_ficha


def referencias(aggs):
    """A distribuicao de gasto entre pares, por (UF, cargo).

    Um numero sozinho nao diz nada. R$ 800 mil e muito para deputado estadual
    no Acre e pouco para federal em Sao Paulo. Esta e a lição que o Serenata
    de Amor tirou do proprio classificador de precos: nunca comparar um caso
    com a media geral, sempre com o grupo a que ele pertence.

    Devolve {(uf, cargo): {n, mediana, p25, p75, p90, total}}, contando so
    quem declarou gasto: incluir os zeros puxaria a mediana para zero e
    descreveria o grupo errado.
    """
    porgrupo = collections.defaultdict(list)
    for a in aggs.values():
        if a.contratado:
            porgrupo[(a.uf, a.cargo)].append(a.contratado)
    saida = {}
    for chave, vs in porgrupo.items():
        vs.sort()
        n = len(vs)
        def q(f):
            return vs[min(n - 1, int(n * f))]
        saida[chave] = {'n': n, 'mediana': q(0.5), 'p25': q(0.25),
                        'p75': q(0.75), 'p90': q(0.9), 'total': sum(vs)}
    return saida


def posicao(a, refs):
    """Onde este candidato esta entre os pares: posicao e multiplo da mediana."""
    r = refs.get((a.uf, a.cargo))
    if not r or not a.contratado:
        return None
    return {
        'grupo_n': r['n'],
        'mediana': r['mediana'],
        'p90': r['p90'],
        'vezes_a_mediana': round(a.contratado / r['mediana'], 1) if r['mediana'] else 0,
        'fatia_do_grupo': round(a.contratado / r['total'] * 100, 1) if r['total'] else 0,
    }


def por_uf(aggs):
    saida = collections.defaultdict(list)
    for a in aggs.values():
        saida[a.uf or '??'].append(a)
    return saida
