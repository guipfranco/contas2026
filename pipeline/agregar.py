#!/usr/bin/env python3
"""Soma o dado bruto do TSE em duas estruturas: uma por candidato, uma nacional.

A estrutura por candidato e o que vira ficha e ranking. A nacional existe para
as perguntas que so aparecem quando se olha o pais inteiro: um fornecedor que
atende 5.183 candidaturas, um numero de nota que aparece em duas contas, um
doador que financia dez campanhas.

Uma passada por arquivo. Nada e lido duas vezes.
"""
import collections
import heapq

from .carregar import limpar_nome

# Cargo por codigo, do proprio TSE. So estes entram no painel: suplente de
# senador nao tem prestacao propria e vice concorre na chapa.
CARGOS = {
    '1': 'Presidente', '2': 'Vice-presidente', '3': 'Governador',
    '4': 'Vice-governador', '5': 'Senador', '6': 'Deputado Federal',
    '7': 'Deputado Estadual', '8': 'Deputado Distrital',
    '9': '1º Suplente', '10': '2º Suplente',
}
CARGOS_PAINEL = ('1', '3', '5', '6', '7', '8')

# Quantos fornecedores cada lista do recorte carrega. A tela de fornecedor
# obedece aos mesmos filtros das outras, e o recorte por unidade, partido e
# cargo e a conta que o front nao tem como fazer: a linha do ranking nao diz
# quem recebeu. Sem corte o arquivo do pais daria 34 MB; com estes topos da
# 0,6 MB, e cada lista declara quantos ficaram de fora e quanto eles somam.
TOPO_RECORTE_GERAL = 200
TOPO_RECORTE_PARTIDO = 60
TOPO_RECORTE_CARGO = 60
TOPO_RECORTE_CELULA = 30

# Quantos fornecedores cada lista do CRUZADO carrega. Aqui o corte e bem mais
# curto que no recorte porque cada lista e multiplicada pelos tipos de despesa
# (33 em Roraima): o arquivo e o produto dos dois eixos, nao a soma. Os numeros
# sao os de um cartao que cabe numa tela, nao os de uma lista de conferencia.
#
# Se o arquivo do pais passar do limite do validador, o primeiro a cortar e a
# CELULA: ela e a chave mais numerosa (um partido vezes um cargo) e a que menos
# gente abre, porque exige dois filtros ligados ao mesmo tempo.
TOPO_CRUZADO_GERAL = 12
TOPO_CRUZADO_PARTIDO = 8
TOPO_CRUZADO_CARGO = 8
TOPO_CRUZADO_CELULA = 5
# Quantos fornecedores o fluxo de duas colunas mostra a divisao exata por
# partido. Doze e o mesmo topo do cartao: o fluxo desenha o que o cartao lista.
TOPO_CRUZADO_FLUXO = 12

# O TSE chama de SG_UF a unidade eleitoral, e para os cargos nacionais ela e
# 'BR'. Na tela isso precisa ter nome, senao 'BR' parece uma sigla de estado
# que ninguem reconhece.
#
# ONDE_UF e o mesmo mapa com a preposicao ja contraida, para o texto do sinal
# nao sair com "em Bahia" e "em Presidencia". O front tem a copia dele.
ONDE_UF = {
    'BR': 'na disputa presidencial', 'BRASIL': 'no Brasil inteiro',
    'AC': 'no Acre', 'AL': 'em Alagoas', 'AP': 'no Amapá', 'AM': 'no Amazonas',
    'BA': 'na Bahia', 'CE': 'no Ceará', 'DF': 'no Distrito Federal',
    'ES': 'no Espírito Santo', 'GO': 'em Goiás', 'MA': 'no Maranhão',
    'MT': 'no Mato Grosso', 'MS': 'no Mato Grosso do Sul', 'MG': 'em Minas Gerais',
    'PA': 'no Pará', 'PB': 'na Paraíba', 'PR': 'no Paraná', 'PE': 'em Pernambuco',
    'PI': 'no Piauí', 'RJ': 'no Rio de Janeiro', 'RN': 'no Rio Grande do Norte',
    'RS': 'no Rio Grande do Sul', 'RO': 'em Rondônia', 'RR': 'em Roraima',
    'SC': 'em Santa Catarina', 'SP': 'em São Paulo', 'SE': 'em Sergipe',
    'TO': 'no Tocantins',
}
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
                 'n_despesas', 'por_tipo', 'por_forn', 'por_forn_tipo', 'por_dia',
                 'por_origem', 'por_fonte_paga', 'por_doador',
                 'primeira', 'ultima', 'genero', 'cor_raca', 'ocupacao')

    def __init__(self, sq):
        self.sq = sq
        self.uf = self.cargo = self.nr = self.nome = self.partido = self.cpf = ''
        self.fed = ''
        self.genero = self.cor_raca = self.ocupacao = ''
        self.prestadores = set()
        self.tipo_prest = ''
        self.contratado = self.pago = self.pago_publico = 0
        self.receita = self.estimavel = self.receita_publica = 0
        self.n_despesas = 0
        self.por_tipo = collections.Counter()
        self.por_forn = {}          # doc -> [valor, n, nome, tipo_forn, cnae, sq_cand_forn]
        # (doc, tipo) -> valor. A chave e uma tupla, e nao um dict aninhado
        # dentro de por_forn: sao 419.531 fornecedores no pais, e um dict vazio
        # por fornecedor custa mais memoria que a conta inteira.
        self.por_forn_tipo = {}
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
        # doc -> {sq: valor}. Era um conjunto de sq, so para contar campanhas;
        # virou o valor por campanha porque e o corpo da ficha do fornecedor:
        # quem pagou a ele, e quanto. Custa 8 bytes por par em relacao ao set.
        self.forn_cands = collections.defaultdict(dict)
        # 'doc|numero' -> [sq, valor somado daquela nota no primeiro candidato]
        self.docs_vistos = {}
        # 'doc|numero' -> {sq: valor daquela nota naquele candidato}. O valor e
        # o da nota, nunca o total do fornecedor: ele vai para o sinal D3 e de
        # la para o indice, entao medir o total inflaria a fila de conferencia.
        self.docs_colisao = collections.defaultdict(dict)
        self.doadores = {}
        self._doador_cands = collections.defaultdict(set)
        # (partido, uf) -> [publico_total, publico_para_mulheres,
        #                   publico_para_negros, {sq das candidaturas}]
        self.fundo_partido = collections.defaultdict(lambda: [0, 0, 0, set()])
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
        for doc, cands in self.forn_cands.items():
            if doc in self.fornecedores:
                self.fornecedores[doc][5] = len(cands)
        for doc, cands in self._doador_cands.items():
            if doc in self.doadores:
                self.doadores[doc][4] = len(cands)
        # forn_cands nao e limpo: ele e a ficha de cada fornecedor, escrita
        # depois desta chamada
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
        # o CPF sai de dentro do nome aqui, na entrada: quem grava ficha, lista
        # e sinal le este mesmo campo, e a limpeza num lugar so nao tem brecha
        nome_forn = limpar_nome(d.forn_rfb or d.forn)
        if d.doc:
            _bota_forn(a.por_forn, d.doc, d.valor, nome_forn, d.tipo_forn,
                       d.cnae, d.sq_cand_forn, d.tipo)
            _bota_forn(nac.fornecedores, d.doc, d.valor, nome_forn, d.tipo_forn,
                       d.cnae, d.sq_cand_forn, d.tipo)
            # o mesmo par que por_tipo guarda por candidatura, agora tambem por
            # fornecedor: e o unico cruzamento da visao geral que o front nao
            # consegue refazer a partir das linhas do ranking
            chave_ft = (d.doc, d.tipo or 'Não informado')
            a.por_forn_tipo[chave_ft] = a.por_forn_tipo.get(chave_ft, 0) + d.valor
            if d.cnae and d.ds_cnae and d.cnae not in nac.cnae_nome:
                nac.cnae_nome[d.cnae] = d.ds_cnae
            porcand = nac.forn_cands[d.doc]
            porcand[d.sq] = porcand.get(d.sq, 0) + d.valor
            if d.num_doc:
                chave = f'{d.doc}|{d.num_doc}'
                antes = nac.docs_vistos.get(chave)
                if antes is None:
                    nac.docs_vistos[chave] = [d.sq, d.valor]
                elif antes[0] == d.sq:
                    # a mesma nota, na mesma conta, em mais de uma linha: e a
                    # nota com varios itens que o carregar.py descreve
                    antes[1] += d.valor
                    if chave in nac.docs_colisao:
                        nac.docs_colisao[chave][d.sq] = antes[1]
                else:
                    colisao = nac.docs_colisao[chave]
                    colisao.setdefault(antes[0], antes[1])
                    colisao[d.sq] = colisao.get(d.sq, 0) + d.valor
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
            # quantas candidaturas entram na conta do recorte: sem isso, um
            # partido com uma candidatura unica a Presidencia aparece com 0 %
            # de fatia como se fosse escolha, quando e aritmetica
            f[3].add(r.sq)
        if r.doc:
            # o doador pessoa fisica tambem pode trazer o CPF dentro do nome
            nome = limpar_nome(r.doador_rfb or r.doador)
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
        # A ocupacao declarada e o unico campo do cadastro que diz o que a
        # pessoa faz. Ela e declaracao de quem se candidatou, nunca registro
        # de mandato: DS_SIT_TOT_TURNO vem #NULO em 100 % das linhas de 2026,
        # porque a eleicao ainda nao aconteceu.
        a.ocupacao = a.ocupacao or c.ocupacao
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


def _funde_no(destino, mapa):
    """Soma um mapa de fornecedores dentro de outro. [valor, campanhas, lancamentos]."""
    for doc, e in mapa.items():
        x = destino.get(doc)
        if x is None:
            destino[doc] = [e[0], e[1], e[2]]
        else:
            x[0] += e[0]
            x[1] += e[1]
            x[2] += e[2]


def _celulas(lista):
    """(partido, cargo) -> {doc: [valor, campanhas, lancamentos]}.

    A celula e a unidade menor do recorte, e partido e cargo saem dela por
    fusao: uma passada so pelas despesas ja agregadas, em vez de tres.
    """
    celulas = collections.defaultdict(dict)
    for a in lista:
        alvo = celulas[(a.partido or '', a.cargo or '')]
        for doc, e in a.por_forn.items():
            x = alvo.get(doc)
            if x is None:
                alvo[doc] = [e[0], 1, e[1]]
            else:
                x[0] += e[0]
                x[1] += 1          # uma candidatura a mais pagou a este
                x[2] += e[1]
    return celulas


def _topo(mapa, quantos, por_campanhas=False):
    """Os maiores do mapa, e quantos ficaram de fora somando quanto.

    Devolve (lista ordenada, [n_restantes, soma_restante] ou None). O empate
    desce pelo documento, para a lista nao mudar de ordem entre rodadas.
    """
    def chave(kv):
        if por_campanhas:
            return (kv[1][1], kv[1][0], kv[0])
        return (kv[1][0], kv[0])

    if len(mapa) <= quantos:
        return sorted(mapa.items(), key=chave, reverse=True), None
    lista = heapq.nlargest(quantos, mapa.items(), key=chave)
    resto = sum(e[0] for e in mapa.values()) - sum(e[1][0] for e in lista)
    return lista, [len(mapa) - quantos, resto]


def _cortar_recorte(celulas):
    """Das celulas para as listas publicaveis, com a conta de quem ficou fora.

    Cada partido e cada cargo e fundido, cortado e descartado antes do
    seguinte: guardar os tres mapas inteiros ao mesmo tempo dobraria o pico de
    memoria da rodada nacional sem precisar.
    """
    geral = {}
    for mapa in celulas.values():
        _funde_no(geral, mapa)
    fora = {}

    def corta(mapa, quantos, chave, por_campanhas=False):
        lista, sobra = _topo(mapa, quantos, por_campanhas)
        if sobra:
            fora[chave] = sobra
        return lista

    saida = {
        'geral': corta(geral, TOPO_RECORTE_GERAL, 'geral'),
        'geral_por_camp': corta(geral, TOPO_RECORTE_GERAL, 'geral_por_camp',
                                True),
        'partido': {},
        'cargo': {},
        'celula': {},
    }
    del geral
    for p in sorted({p for p, _ in celulas}):
        mapa = {}
        for (pp, _), m in celulas.items():
            if pp == p:
                _funde_no(mapa, m)
        saida['partido'][p] = corta(mapa, TOPO_RECORTE_PARTIDO, ('p', p))
    for c in sorted({c for _, c in celulas}):
        mapa = {}
        for (_, cc), m in celulas.items():
            if cc == c:
                _funde_no(mapa, m)
        saida['cargo'][c] = corta(mapa, TOPO_RECORTE_CARGO, ('c', c))
    for (p, c), mapa in celulas.items():
        saida['celula'][(p, c)] = corta(mapa, TOPO_RECORTE_CELULA,
                                        ('p', p, 'c', c))
    saida['fora'] = fora
    return saida


def recorte_fornecedores(aggs):
    """Quem recebeu, por unidade e por recorte de partido e cargo.

    A tela de fornecedor obedece aos mesmos filtros das outras, e a linha do
    ranking nao diz quem recebeu: sem este agregado o front teria de baixar as
    fichas de 419 mil fornecedores para responder "quem recebeu do PT no
    Amazonas". A conta e feita depois de `juntar_candidaturas`, porque so ali o
    partido de cada candidatura e definitivo.

    Devolve {unidade: recorte}, com 'BRASIL' no mesmo formato. Medido em RR:
    0,03 s para 10.933 pares.
    """
    saida = {}
    nacional = collections.defaultdict(dict)
    for uf, lista in por_uf(aggs).items():
        celulas = _celulas(lista)
        saida[uf] = _cortar_recorte(celulas)
        for chave, mapa in celulas.items():
            _funde_no(nacional[chave], mapa)
    saida['BRASIL'] = _cortar_recorte(nacional)
    return saida


# ---------- o cruzado: fornecedor por tipo de despesa e por partido ----------
#
# A visao geral cruza cinco dimensoes numa tela so, e quatro delas o front
# calcula sozinho sobre as linhas do ranking que ja estao filtradas. Fornecedor
# e a quinta, e ele nao esta na linha: a conta tem de vir pronta daqui.


def _celulas_cruzadas(lista):
    """(partido, cargo) -> {tipo: {doc: valor}}.

    Mesma ideia de `_celulas`, com o tipo de despesa como eixo a mais. A celula
    continua sendo a unidade menor: partido, cargo e o geral saem dela por
    fusao, numa passada so.
    """
    celulas = collections.defaultdict(dict)
    for a in lista:
        alvo = celulas[(a.partido or '', a.cargo or '')]
        for (doc, tipo), valor in a.por_forn_tipo.items():
            porta = alvo.get(tipo)
            if porta is None:
                porta = alvo[tipo] = {}
            porta[doc] = porta.get(doc, 0) + valor
    return celulas


def _funde_cruzado(destino, mapa):
    """Soma um {tipo: {doc: valor}} dentro de outro."""
    for tipo, docs in mapa.items():
        alvo = destino.get(tipo)
        if alvo is None:
            alvo = destino[tipo] = {}
        for doc, valor in docs.items():
            alvo[doc] = alvo.get(doc, 0) + valor


def _topo_simples(mapa, quantos):
    """Os maiores de {doc: valor}, e quantos ficaram fora somando quanto.

    O empate desce pelo documento, para a lista nao mudar de ordem entre
    rodadas, que e a mesma regra de `_topo`.
    """
    def chave(kv):
        return (kv[1], kv[0])

    if len(mapa) <= quantos:
        return sorted(mapa.items(), key=chave, reverse=True), None
    lista = heapq.nlargest(quantos, mapa.items(), key=chave)
    resto = sum(mapa.values()) - sum(v for _, v in lista)
    return lista, [len(mapa) - quantos, resto]


def _fatias(celulas, cargo=None, tipo=None, fundidas=None):
    """[(partido, {doc: valor})], uma fatia por celula do recorte pedido."""
    saida = []
    for (p, c), mapa in celulas.items():
        if cargo is not None and c != cargo:
            continue
        if tipo is None:
            docs = fundidas[(p, c)]
        else:
            docs = mapa.get(tipo) or {}
        if docs:
            saida.append((p, docs))
    return saida


def _fluxo(fatias, quantos=TOPO_CRUZADO_FLUXO):
    """Os maiores fornecedores do recorte, com o valor dividido por partido.

    Duas passadas de proposito. A primeira soma so o total de cada fornecedor,
    um inteiro por documento; a segunda monta a divisao por partido apenas dos
    que ficaram na lista. Guardar a divisao de todo mundo para depois jogar
    fora custaria um dict por fornecedor, e sao 419.531 no pais.
    """
    totais = {}
    for _, docs in fatias:
        for doc, valor in docs.items():
            totais[doc] = totais.get(doc, 0) + valor
    if not totais:
        return []
    maiores = heapq.nlargest(quantos, totais.items(),
                             key=lambda kv: (kv[1], kv[0]))
    del totais
    divisao = {doc: {} for doc, _ in maiores}
    for partido, docs in fatias:
        for doc, alvo in divisao.items():
            valor = docs.get(doc)
            if valor:
                alvo[partido] = alvo.get(partido, 0) + valor
    return [(doc, sorted(divisao[doc].items(), key=lambda kv: (-kv[1], kv[0])))
            for doc, _ in maiores]


def _cortar_cruzado(celulas):
    """Das celulas para as listas publicaveis do cruzado.

    Devolve {'tipo': {chave: {tipo: lista}}, 'fora': {chave: {tipo: sobra}},
    'partido': {chave: [(doc, [(partido, valor)])]}}, com a chave em tupla,
    como `_cortar_recorte` faz, e o nome so no `escrever`.
    """
    por_tipo, fora, fluxos = {}, {}, {}

    def corta(mapa, quantos, chave):
        porta, sobrou = {}, {}
        for tipo, docs in mapa.items():
            lista, sobra = _topo_simples(docs, quantos)
            porta[tipo] = lista
            if sobra:
                sobrou[tipo] = sobra
        por_tipo[chave] = porta
        if sobrou:
            fora[chave] = sobrou

    geral = {}
    for mapa in celulas.values():
        _funde_cruzado(geral, mapa)
    corta(geral, TOPO_CRUZADO_GERAL, 'geral')
    tipos = sorted(geral)
    del geral
    partidos = sorted({p for p, _ in celulas})
    cargos = sorted({c for _, c in celulas})
    for p in partidos:
        mapa = {}
        for (pp, _), m in celulas.items():
            if pp == p:
                _funde_cruzado(mapa, m)
        corta(mapa, TOPO_CRUZADO_PARTIDO, ('p', p))
    for c in cargos:
        mapa = {}
        for (_, cc), m in celulas.items():
            if cc == c:
                _funde_cruzado(mapa, m)
        corta(mapa, TOPO_CRUZADO_CARGO, ('c', c))
    for (p, c), mapa in celulas.items():
        corta(mapa, TOPO_CRUZADO_CELULA, ('p', p, 'c', c))

    # Os fluxos. Nao ha chave de partido aqui: com o filtro de partido ligado o
    # fluxo tem uma fonte so, e a divisao seria a lista inteira num lado.
    fundidas = {}
    for chave, mapa in celulas.items():
        alvo = fundidas[chave] = {}
        for docs in mapa.values():
            for doc, valor in docs.items():
                alvo[doc] = alvo.get(doc, 0) + valor
    fluxos['geral'] = _fluxo(_fatias(celulas, fundidas=fundidas))
    for c in cargos:
        fluxos[('c', c)] = _fluxo(_fatias(celulas, cargo=c, fundidas=fundidas))
    del fundidas
    for t in tipos:
        fluxos[('t', t)] = _fluxo(_fatias(celulas, tipo=t))
        for c in cargos:
            lista = _fluxo(_fatias(celulas, cargo=c, tipo=t))
            if lista:
                fluxos[('c', c, 't', t)] = lista
    return {'tipo': por_tipo, 'fora': fora, 'partido': fluxos}


def recorte_forn_cruzado(aggs):
    """Fornecedor por tipo de despesa e por partido, por unidade e no pais.

    Irmao de `recorte_fornecedores`, e pela mesma razao: a linha do ranking nao
    diz quem recebeu. O recorte responde "quem recebeu do PT em Roraima"; este
    responde "quem recebeu por publicidade" e "de que partidos saiu o dinheiro
    que chegou a este fornecedor", que sao as duas contas da visao geral.
    """
    saida = {}
    nacional = collections.defaultdict(dict)
    for uf, lista in por_uf(aggs).items():
        celulas = _celulas_cruzadas(lista)
        saida[uf] = _cortar_cruzado(celulas)
        for chave, mapa in celulas.items():
            _funde_cruzado(nacional[chave], mapa)
    saida['BRASIL'] = _cortar_cruzado(nacional)
    return saida
