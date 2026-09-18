#!/usr/bin/env python3
"""Escreve os JSON que o site le.

Tres regras deste modulo:

**Dicionario no meta, id no resto.** Nome de tipo de despesa tem 50 caracteres
e se repete em 700 mil linhas. No JSON ele aparece uma vez, no `meta.json`, e
os outros arquivos carregam o indice. Corta o arquivo de SP pela metade.

**Array posicional, nao objeto.** `{"contratado": 123}` repetido 2.900 vezes e
chave gasta. O front sabe a ordem.

**Grava em .tmp e renomeia.** Arquivo JSON truncado no meio de um deploy vira
pagina quebrada que parece dado. A troca de nome e atomica.

**CPF nunca sai inteiro.** O TSE publica, este painel mascara: repetir o numero
completo num arquivo facil de varrer e outra coisa.
"""
import collections
import json
import os

from .agregar import CARGOS, NOME_UF
from .alarmes import faixa, indice
from .carregar import mascara

def curto(texto, k=48):
    """Corta com reticencia, para o nome cortado nao parecer o nome inteiro."""
    texto = texto or ''
    return texto if len(texto) <= k else texto[:k - 1] + '…'


TOPO_FORN_RANKING = 3      # no ranking, so o suficiente para dar cara
TOPO_FORN_FICHA = 30
TOPO_DOADOR_FICHA = 30
LIMITE_ALARMES = 4000


class Dic:
    """Vocabulario -> id, na ordem em que aparece."""

    def __init__(self):
        self.lista = []
        self.idx = {}

    def id(self, v):
        v = v or ''
        i = self.idx.get(v)
        if i is None:
            i = self.idx[v] = len(self.lista)
            self.lista.append(v)
        return i


def grava(caminho, obj):
    """Escreve JSON compacto, com staging. Devolve os bytes escritos."""
    os.makedirs(os.path.dirname(caminho) or '.', exist_ok=True)
    tmp = caminho + '.tmp'
    texto = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    json.loads(texto)  # se nao parseia, nao publica
    os.replace(tmp, caminho)
    return len(texto.encode('utf-8'))


def escrever_uf(uf, aggs, alarmes_por_sq, dics, destino):
    """Uma linha por candidato da UF, para o ranking.

    Dezesseis campos. Um deles era a receita por origem, e saiu em 17/09: ele
    existia para um filtro que lia DS_ORIGEM_RECEITA (como o partido
    classificou o repasse) enquanto o numero de capa da pagina, o dinheiro
    publico, vem de DS_FONTE_RECEITA. Os dois se contradiziam na mesma tela.

    O campo 15 e a RECEITA publica, e entrou em 18/09 por causa da coluna de
    cota de genero na visao por partido. O campo 9 e o que foi PAGO com
    dinheiro publico, e a Constituicao e o sinal B4 medem a fatia de 30 % sobre
    a receita, nao sobre o pagamento: sem este campo a tela mediria uma coisa e
    chamaria pelo nome da outra.
    """
    dtipo, dpart, dfed, dalarme = dics['tipo'], dics['partido'], dics['fed'], dics['alarme']
    linhas = []
    for a in sorted(aggs, key=lambda x: -x.contratado):
        al = alarmes_por_sq.get(a.sq, ())
        if not a.movimento and not al:
            # candidato sem nenhum movimento: cabecalho enxuto, para a busca
            linhas.append([a.sq, a.nome, a.nr, dpart.id(a.partido), a.cargo,
                           dfed.id(a.fed),
                           0, 0, 0, 0, 0, [], [], 0, 0, 0])
            continue
        tipos = [[dtipo.id(t), v] for t, v in a.por_tipo.most_common() if v]
        linhas.append([
            a.sq, a.nome, a.nr, dpart.id(a.partido), a.cargo,
            dfed.id(a.fed),
            a.contratado, a.pago, a.receita, a.pago_publico,
            len(a.por_forn), tipos,
            [[dalarme.id(x.codigo), x.grav] for x in al],
            1 if (a.genero or '').upper().startswith('F') else 0,
            indice(a.contratado, al),
            a.receita_publica,
        ])
    return grava(os.path.join(destino, 'uf', f'{uf}.json'),
                 {'uf': uf, 'n': len(linhas), 'c': linhas})


def _forn_publico(doc, e, com_chave=None):
    """O que pode ir ao ar sobre um fornecedor: endereco, documento, natureza.

    `e` e a entrada NACIONAL daquele fornecedor, porque o piso da ficha de
    pessoa fisica e medido na eleicao inteira: quem recebeu R$ 12 mil no pais
    tem ficha tambem na lista da UF onde recebeu R$ 300.

    O endereco vazio e o que define `tem_ficha` no arquivo. Sao duas contas
    (o piso, aqui, e a chave do ambiente, no ident) e amarrar a segunda na
    primeira e o que garante que nenhum nome aponte para pagina que nao existe.
    """
    from .ident import ident_publico
    endereco = ident_publico(doc) if tem_ficha(doc, e, com_chave) else ''
    return (endereco, mascara(doc), 1 if len(doc) == 14 else 0,
            1 if endereco else 0)


def _forn_linha(doc, e, alarmes_do_forn, cnae_nome):
    # o ultimo campo e o endereco da ficha daquele fornecedor: sem ele a lista
    # de quem recebeu seria a unica da tela que nao abre nada
    endereco, documento, pj, _ = _forn_publico(doc, e)
    return [documento, curto(e[2] or 'Não informado'), e[0], e[1], pj,
            (cnae_nome.get(e[4]) or '')[:44],
            sorted(alarmes_do_forn),
            endereco]


def escrever_ficha(a, alarmes, dics, cnae_nome, destino, extra=None, pares=None):
    forn = sorted(a.por_forn.items(), key=lambda kv: -kv[1][0])[:TOPO_FORN_FICHA]
    por_forn_alarme = {}
    for x in alarmes:
        if x.doc:
            por_forn_alarme.setdefault(x.doc, set()).add(x.codigo)
    doadores = sorted(a.por_doador.items(), key=lambda kv: -kv[1][0])[:TOPO_DOADOR_FICHA]
    ficha = {
        'sq': a.sq, 'nome': a.nome, 'nr': a.nr, 'partido': a.partido,
        'cargo': CARGOS.get(a.cargo, a.cargo), 'uf': a.uf,
        'fed': a.fed, 'genero': a.genero, 'cor_raca': a.cor_raca,
        # a ocupacao declarada no registro da candidatura. E declaracao de
        # quem se candidatou, nunca registro de mandato
        'ocupacao': a.ocupacao,
        'contratado': a.contratado, 'pago': a.pago, 'pago_publico': a.pago_publico,
        'receita': a.receita, 'estimavel': a.estimavel,
        'receita_publica': a.receita_publica,
        'n_despesas': a.n_despesas, 'n_forn': len(a.por_forn),
        'prestacao': a.tipo_prest,
        'tipos': [[t, v] for t, v in a.por_tipo.most_common() if v],
        'origens': [[t, v] for t, v in a.por_origem.most_common() if v],
        'fontes': [[t, v] for t, v in a.por_fonte_paga.most_common() if v],
        'forn': [_forn_linha(d, e, por_forn_alarme.get(d, ()), cnae_nome)
                 for d, e in forn],
        'doadores': [[mascara(d), curto(e[2] or 'Não informado'), e[0], e[1], e[3]]
                     for d, e in doadores],
        'serie': sorted(a.por_dia.items()),
        'indice': indice(a.contratado, alarmes),
        'faixa': faixa(indice(a.contratado, alarmes)),
        'alarmes': [{'cod': x.codigo, 'grav': x.grav, 'texto': x.texto}
                    for x in sorted(alarmes, key=lambda x: (-x.grav, -x.valor))],
    }
    if pares:
        ficha['pares'] = pares
    if extra:
        ficha.update(extra)
    return grava(os.path.join(destino, 'cand', f'{a.sq}.json'), ficha)


def escrever_brasil(aggs, alarmes_por_sq, dics, destino):
    """O pais inteiro num arquivo so.

    Ele existe porque a pergunta "quem gastou mais no Brasil" nao se responde
    somando 28 arquivos no celular. Sao as mesmas linhas das UFs, com a UF
    acrescentada no fim de cada uma, para o front saber de onde veio sem
    baixar os 28.

    **O gasto por tipo nao vem por linha aqui.** Media em 17/09: a lista de
    tipos era 36 % do arquivo do pais, quase 1 MB comprimido que o celular
    baixava para alimentar um painel que nasce fechado. No lugar dela vai o
    agregado do pais inteiro, no cabecalho, que e o que aquele painel mostra.
    Nas UFs o campo continua por linha, porque la ele custa pouco e o filtro
    por tipo precisa dele.
    """
    dpart, dfed, dalarme = dics['partido'], dics['fed'], dics['alarme']
    dtipo = dics['tipo']
    linhas = []
    tipos_pais = collections.Counter()
    for a in sorted(aggs, key=lambda x: -x.contratado):
        # A visao nacional e sobre dinheiro. Quem nao declarou nada continua
        # achavel pela busca e pela propria UF, mas nao entra num ranking de
        # 20 mil linhas onde so ocuparia espaco.
        if not a.movimento:
            continue
        al = alarmes_por_sq.get(a.sq, ())
        for t, v in a.por_tipo.items():
            if v:
                tipos_pais[t] += v
        linhas.append([
            a.sq, a.nome, a.nr, dpart.id(a.partido), a.cargo, dfed.id(a.fed),
            a.contratado, a.pago, a.receita, a.pago_publico,
            len(a.por_forn),
            [],
            [[dalarme.id(x.codigo), x.grav] for x in al],
            1 if (a.genero or '').upper().startswith('F') else 0,
            indice(a.contratado, al),
            a.receita_publica,
            a.uf,
        ])
    sem_movimento = sum(1 for a in aggs if not a.movimento)
    return grava(os.path.join(destino, 'uf', 'BRASIL.json'),
                 {'uf': 'BRASIL', 'n': len(linhas),
                  'sem_movimento': sem_movimento,
                  'tipos': [[dtipo.id(t), v] for t, v in tipos_pais.most_common()],
                  'c': linhas})


def escrever_indice(aggs, dics, destino):
    """A busca nacional. Um array por candidato, o menor que da."""
    dpart = dics['partido']
    docup = dics['ocupacao']
    linhas = [[a.sq, a.nome, a.uf, a.cargo, dpart.id(a.partido), a.nr,
               1 if a.movimento else 0, docup.id(a.ocupacao)]
              for a in aggs]
    linhas.sort(key=lambda l: l[1])
    return grava(os.path.join(destino, 'indice.json'), {'c': linhas})


# O que nao e item de fila de conferencia. Era uma lista propria daqui, com so
# ('C2',), enquanto o indice tirava C2 e D1 e o front lia a lista do indice: a
# mesma palavra, "para conferir", contava tres conjuntos diferentes em tres
# telas. A regua agora e uma so, a do modulo de alarmes, e o meta publica ela.
from .alarmes import FORA_DO_INDICE as FORA_DA_LISTA_NACIONAL


def escrever_alarmes(alarmes, aggs_por_sq, dics, destino, limite=LIMITE_ALARMES):
    dpart = dics['partido']
    linhas = []
    elegiveis = [x for x in alarmes if x.codigo not in FORA_DA_LISTA_NACIONAL]
    cortados = len(elegiveis) - min(len(elegiveis), limite)
    for x in sorted(elegiveis, key=lambda x: (-x.grav, -x.valor))[:limite]:
        a = aggs_por_sq.get(x.sq)
        if not a:
            continue
        linhas.append([x.codigo, x.grav, a.uf, a.sq, a.nome,
                       dpart.id(a.partido), a.cargo, x.valor, x.texto])
    return grava(os.path.join(destino, 'alarmes.json'),
                 {'n': len(linhas), 'total': len(elegiveis), 'cortados': cortados,
                  'a': linhas})


# Piso da ficha de pessoa fisica. Empresa nao tem piso, porque CNPJ e publico
# por natureza e a ficha dela responde a uma pergunta de interesse publico.
# Pessoa fisica e outra coisa: a maior parte dos fornecedores do pais e gente que
# prestou um servico pontual, e uma pagina com nome, valor e as campanhas que
# pagaram nao se sustenta para quem recebeu R$ 300.
#
# Calibrado contra Roraima, onde ha 9.082 fornecedores pessoa fisica:
#   R$  1 mil -> 7.753 fichas (85 % das pessoas), 96,6 % do valor pago a elas
#   R$  5 mil ->   952 fichas (10,5 %),           49,4 % do valor
#   R$ 10 mil ->   455 fichas (5,0 %),            37,5 % do valor
#   R$ 20 mil ->   129 fichas (1,4 %),            21,6 % do valor
# R$ 10 mil deixa de fora 95 % das pessoas e ainda cobre mais de um terco do
# dinheiro. Quem fica de fora continua nas listas, sem pagina propria.
PISO_FICHA_PF = 1000000     # R$ 10 mil, em centavos

FORN_POR_BLOCO = 120        # quantos fornecedores cabem bem num arquivo
FORN_CANDS_NA_FICHA = 100   # quantas candidaturas a ficha lista, das maiores
FORN_SINAIS_NA_FICHA = 20


def tem_ficha(doc, entrada, com_chave=None):
    """Se aquele fornecedor ganha pagina propria.

    Quem chama isto e tanto quem escreve a ficha quanto quem escreve link para
    ela: nome com link para pagina que nao existe e pior que nome sem link.
    """
    from .ident import tem_sal_de_verdade
    if len(doc) == 14:
        return True
    if com_chave is None:
        com_chave = tem_sal_de_verdade()
    return bool(com_chave) and entrada[0] >= PISO_FICHA_PF


def _n_blocos(quantos, por_bloco=FORN_POR_BLOCO, minimo=16):
    """Potencia de 2 que deixa o bloco no tamanho de uma tela, nao de um dump."""
    n = minimo
    while quantos / n > por_bloco and n < 8192:
        n *= 2
    return n


def escrever_fornecedores_fichas(nac, aggs, receita, cnae_nome, alarmes,
                                 destino, por_bloco=FORN_POR_BLOCO):
    """A ficha de quem recebeu dinheiro de campanha, em blocos.

    **Por que em blocos.** Sao 419 mil fornecedores no pais, e 92 % deles tem um
    unico lancamento. Um arquivo por fornecedor viraria 419 mil arquivos num
    artifact so, o que o Pages nao aguenta publicar duas vezes por dia. Cada
    bloco junta cerca de 120 fichas, o front calcula o bloco pelo identificador
    com a mesma conta do `ident.bloco`, e abrir uma ficha custa um pedido.

    **O que a ficha traz.** O que o TSE publica sobre o dinheiro (quanto,
    quantos lancamentos, quais candidaturas pagaram e quanto cada uma), o que a
    Receita publica sobre a empresa (situacao, abertura, natureza, porte e
    socios) e os sinais levantados que citam aquele fornecedor, cada um com o
    texto que o pipeline escreveu. Pessoa fisica nao tem cadastro nem socio: a
    ficha dela e so o dinheiro, com o documento mascarado.
    """
    from .ident import bloco, ident, tem_sal_de_verdade
    # Sem a chave do ambiente, o identificador de pessoa fisica e um HMAC com sal
    # declarado no codigo: quem tiver o identificador volta ao CPF por forca bruta
    # em segundos. Nessa condicao a ficha de pessoa fisica simplesmente nao sai,
    # e a tela declara quantas ficaram de fora. Empresa sai sempre: CNPJ e publico.
    com_chave = tem_sal_de_verdade()
    pessoas_fora = pessoas_pequenas = 0
    por_doc_alarme = {}
    for x in alarmes:
        if x.doc:
            por_doc_alarme.setdefault(x.doc, []).append(x)
    quantos = _n_blocos(len(nac.fornecedores), por_bloco)
    blocos = collections.defaultdict(dict)
    for doc, e in nac.fornecedores.items():
        if len(doc) != 14 and not com_chave:
            pessoas_fora += 1
            continue
        if not tem_ficha(doc, e, com_chave):
            pessoas_pequenas += 1
            continue
        i = ident(doc)
        pagantes = sorted(nac.forn_cands.get(doc, {}).items(),
                          key=lambda kv: -kv[1])
        cands = []
        for sq, valor in pagantes[:FORN_CANDS_NA_FICHA]:
            a = aggs.get(sq)
            if not a:
                continue
            cands.append([sq, a.nome, a.uf, a.cargo, a.partido, valor])
        ficha = {
            'id': i,
            'nome': curto(e[2] or 'Não informado', 60),
            'doc': mascara(doc),
            'pj': 1 if len(doc) == 14 else 0,
            'valor': e[0],
            'n_lanc': e[1],
            'n_camp': e[5],
            'cands': cands,
            'cands_fora': max(0, len(pagantes) - len(cands)),
        }
        nome_cnae = (cnae_nome.get(e[4]) or '')[:60] if e[4] else ''
        if nome_cnae:
            ficha['cnae'] = nome_cnae
        cad = receita.get(doc) if len(doc) == 14 else None
        if cad and 'erro' not in cad:
            ficha['cadastro'] = {
                'razao': (cad.get('razao_social') or '')[:80],
                'situacao': cad.get('situacao_cadastral') or '',
                'abertura': cad.get('data_inicio_atividade') or '',
                'natureza': (cad.get('natureza_juridica') or '')[:60],
                'porte': cad.get('porte_empresa') or '',
                'socios': list(cad.get('socios') or []),
            }
        sinais = por_doc_alarme.get(doc, [])
        if sinais:
            # a intensidade vai junto: sem ela o front desenhava todo selo no
            # grau mais fraco, lendo o sq da candidatura como se fosse gravidade
            ficha['sinais'] = [
                [x.codigo, x.sq, x.texto, x.grav]
                for x in sorted(sinais, key=lambda x: (-x.grav, -x.valor))
                [:FORN_SINAIS_NA_FICHA]]
        blocos[bloco(i, quantos)][i] = ficha
    total = escritas = 0
    for n, fichas in blocos.items():
        escritas += len(fichas)
        total += grava(os.path.join(destino, 'forn', f'{n}.json'),
                       {'b': n, 'n': len(fichas), 'f': fichas})
    # duas fichas no mesmo identificador seriam uma sobrescrevendo a outra em
    # silencio: a conta fecha ou a rodada avisa
    esperadas = len(nac.fornecedores) - pessoas_fora - pessoas_pequenas
    return {'blocos': quantos, 'arquivos': len(blocos),
            'fornecedores': escritas, 'esperadas': esperadas,
            'colisoes': esperadas - escritas,
            'pessoas_fora': pessoas_fora, 'pessoas_pequenas': pessoas_pequenas,
            'piso_pf': PISO_FICHA_PF, 'bytes': total}


def _chave_fora(chave, dpart):
    """A chave de quem ficou fora, no mesmo endereco que o front monta."""
    if isinstance(chave, str):
        return chave
    if chave[0] == 'p' and len(chave) == 2:
        return f'p:{dpart.id(chave[1])}'
    if chave[0] == 'c':
        return f'c:{chave[1]}'
    return f'p:{dpart.id(chave[1])}:c:{chave[3]}'


def escrever_forn_recorte(unidade, recorte, nac, dics, destino, com_chave=None):
    """Quem recebeu, na unidade e em cada recorte de partido e cargo.

    Uma entrada e [endereco, nome, documento, pj, valor, campanhas,
    lancamentos, tem_ficha]. O valor, as campanhas e os lancamentos sao os DO
    RECORTE; o nome, o documento e a ficha vem do cadastro nacional, que e onde
    o piso da ficha de pessoa fisica e medido.

    O partido entra pelo indice do dicionario do meta, o mesmo numero que a
    linha do ranking carrega: o front cruza os dois sem tabela no meio.
    """
    dpart = dics['partido']

    def entrada(doc, e):
        cad = nac.fornecedores.get(doc) or [0, 0, '']
        endereco, documento, pj, tem = _forn_publico(doc, cad, com_chave)
        return [endereco, curto(cad[2] or 'Não informado'), documento, pj,
                e[0], e[1], e[2], tem]

    def lista(itens):
        return [entrada(d, e) for d, e in itens]

    return grava(os.path.join(destino, 'forn-recorte', f'{unidade}.json'), {
        'uf': unidade,
        'geral': lista(recorte['geral']),
        'geral_por_camp': lista(recorte['geral_por_camp']),
        'partido': {str(dpart.id(p)): lista(v)
                    for p, v in recorte['partido'].items()},
        'cargo': {c: lista(v) for c, v in recorte['cargo'].items()},
        'celula': {f'{dpart.id(p)}:{c}': lista(v)
                   for (p, c), v in recorte['celula'].items()},
        'fora': {_chave_fora(k, dpart): v for k, v in recorte['fora'].items()},
    })


# As faixas sao lidas por gente, entao os cortes sao redondos em reais, nunca
# quantis: "de R$ 10 mil a R$ 100 mil" se entende, "terceiro decil" nao.
FAIXAS_CAND = [
    (0, 0, 'nada declarado'),
    (1, 1000000, 'até R$ 10 mil'),
    (1000000, 5000000, 'R$ 10 mil a R$ 50 mil'),
    (5000000, 25000000, 'R$ 50 mil a R$ 250 mil'),
    (25000000, 100000000, 'R$ 250 mil a R$ 1 mi'),
    (100000000, 500000000, 'R$ 1 mi a R$ 5 mi'),
    (500000000, None, 'acima de R$ 5 mi'),
]
FAIXAS_FORN = [
    (1, 100000, 'até R$ 1 mil'),
    (100000, 1000000, 'R$ 1 mil a R$ 10 mil'),
    (1000000, 10000000, 'R$ 10 mil a R$ 100 mil'),
    (10000000, 100000000, 'R$ 100 mil a R$ 1 mi'),
    (100000000, 1000000000, 'R$ 1 mi a R$ 10 mi'),
    (1000000000, None, 'acima de R$ 10 mi'),
]
TOPO_NA_FAIXA = 10
TOPO_NO_GRUPO = 5


def _mediana(valores):
    if not valores:
        return 0
    v = sorted(valores)
    meio = len(v) // 2
    return v[meio] if len(v) % 2 else (v[meio - 1] + v[meio]) // 2


def _grupo(chave, rotulo, lista):
    """Um recorte do panorama: quantos, quanto, a mediana e quem esta no topo."""
    com_gasto = [a for a in lista if a.contratado]
    topo = sorted(com_gasto, key=lambda a: -a.contratado)[:TOPO_NO_GRUPO]
    return {
        chave: rotulo,
        'n': len(lista),
        'com_gasto': len(com_gasto),
        'contratado': sum(a.contratado for a in lista),
        'pago': sum(a.pago for a in lista),
        'publico': sum(a.pago_publico for a in lista),
        'mediana': _mediana([a.contratado for a in com_gasto]),
        'topo': [[a.sq, a.nome, a.uf, a.contratado] for a in topo],
    }


def escrever_panorama(aggs, nac, destino):
    """A tela que nao fala de um candidato: partido, cargo, estado e faixa.

    O ranking responde "quem gastou mais". Esta visao responde as perguntas que
    vem antes dessa: quanto dinheiro cada partido moveu, quantas candidaturas
    ele tem, quanto gasta a candidatura tipica de cada cargo, e quanta gente
    recebeu pouco enquanto pouca gente recebeu muito. Cada recorte carrega os
    nomes do topo, para a tela nao virar tabela de agregado sem gente dentro.
    """
    por_partido = collections.defaultdict(list)
    por_cargo = collections.defaultdict(list)
    por_uf = collections.defaultdict(list)
    ocupacoes = collections.Counter()
    for a in aggs:
        por_partido[a.partido or 'sem partido'].append(a)
        por_cargo[a.cargo].append(a)
        por_uf[a.uf].append(a)
        if a.ocupacao:
            ocupacoes[a.ocupacao] += 1

    partidos = [_grupo('partido', p, l) for p, l in por_partido.items()]
    partidos.sort(key=lambda x: -x['contratado'])
    cargos = [_grupo('cargo', CARGOS.get(c, c), l) for c, l in por_cargo.items()]
    cargos.sort(key=lambda x: -x['contratado'])
    ufs = [_grupo('uf', NOME_UF.get(u, u), l) for u, l in por_uf.items()]
    ufs.sort(key=lambda x: -x['contratado'])
    for linha, (u, _) in zip(ufs, sorted(por_uf.items(),
                                         key=lambda kv: -sum(a.contratado
                                                             for a in kv[1]))):
        linha['sg'] = u

    faixas_cand = []
    for piso, teto, rotulo in FAIXAS_CAND:
        if piso == 0 and teto == 0:
            dentro = [a for a in aggs if not a.contratado]
        else:
            dentro = [a for a in aggs
                      if a.contratado >= piso and (teto is None or a.contratado < teto)]
        topo = sorted(dentro, key=lambda a: -a.contratado)[:TOPO_NA_FAIXA]
        faixas_cand.append({
            'faixa': rotulo, 'n': len(dentro),
            'soma': sum(a.contratado for a in dentro),
            'topo': [[a.sq, a.nome, a.uf, a.contratado] for a in topo],
        })

    from .ident import ident_publico as ident
    faixas_forn = []
    for piso, teto, rotulo in FAIXAS_FORN:
        dentro = [(d, e) for d, e in nac.fornecedores.items()
                  if e[0] >= piso and (teto is None or e[0] < teto)]
        topo = sorted(dentro, key=lambda de: -de[1][0])[:TOPO_NA_FAIXA]
        faixas_forn.append({
            'faixa': rotulo, 'n': len(dentro),
            'soma': sum(e[0] for _, e in dentro),
            'topo': [[ident(d) if tem_ficha(d, e) else '',
                      curto(e[2] or 'Não informado'), e[0], e[5],
                      1 if len(d) == 14 else 0] for d, e in topo],
        })
    # fornecedor com valor zero ou negativo nao cai em faixa nenhuma: a soma
    # das faixas tem de fechar com o total, senao a tela mente por omissao
    fora = len(nac.fornecedores) - sum(f['n'] for f in faixas_forn)
    if fora:
        faixas_forn.insert(0, {'faixa': 'sem valor declarado', 'n': fora,
                               'soma': 0, 'topo': []})

    return grava(os.path.join(destino, 'panorama.json'), {
        'partidos': partidos, 'cargos': cargos, 'ufs': ufs,
        'faixas_cand': faixas_cand, 'faixas_forn': faixas_forn,
        'ocupacoes': ocupacoes.most_common(40),
        'n_ocupacoes': len(ocupacoes),
    })


def escrever_fornecedores(nac, destino, topo=400):
    """Os maiores fornecedores da eleicao. Recorte que o TSE nao oferece."""
    from .ident import ident_publico

    def endereco(doc, e):
        """Link só para quem tem ficha: nome apontando para página que não
        existe é pior que nome sem link."""
        return ident_publico(doc) if tem_ficha(doc, e) else ''

    linhas = []
    for doc, e in sorted(nac.fornecedores.items(), key=lambda kv: -kv[1][0])[:topo]:
        linhas.append([mascara(doc), curto(e[2] or 'Não informado'), e[0], e[1],
                       e[5], 1 if len(doc) == 14 else 0, endereco(doc, e)])
    por_cand = sorted(nac.fornecedores.items(), key=lambda kv: -kv[1][5])[:topo]
    espalhados = [[mascara(d), curto(e[2] or 'Não informado'), e[0], e[1], e[5],
                   1 if len(d) == 14 else 0, endereco(d, e)] for d, e in por_cand]
    return grava(os.path.join(destino, 'fornecedores.json'),
                 {'por_valor': linhas, 'por_candidatos': espalhados,
                  'total': len(nac.fornecedores), 'topo': topo})


def escrever_meta(dics, contagens, ufs, cargos, gerado, tse, destino,
                  catalogo=None, gravidades=None, forn=None):
    """O meta carrega os dicionarios e o catalogo de sinais.

    O catalogo sai indexado PELO CODIGO, nao por posicao numa lista. A versao
    anterior era uma lista de frases, e o front tinha de casar a frase com o
    sinal pelo indice: bastava acrescentar um codigo no meio para a tela passar
    a mostrar a ressalva errada ao lado do sinal errado.
    """
    from .alarmes import CURTO, FAIXAS, FORA_DO_INDICE, PESO, QUANTOS_SOMAM
    sinais = {}
    for cod, (familia, nome, significa, nao_significa) in (catalogo or {}).items():
        sinais[cod] = {
            'familia': familia, 'nome': nome, 'curto': CURTO.get(cod, nome),
            'significa': significa, 'nao_significa': nao_significa,
            'no_indice': cod not in FORA_DO_INDICE,
        }
    return grava(os.path.join(destino, 'meta.json'), {
        'gerado_em': gerado,
        'tse': tse,
        'contagens': contagens,
        'ufs': ufs,
        'cargos': {k: CARGOS[k] for k in cargos},
        'nome_uf': {u: NOME_UF.get(u, u) for u in list(ufs) + ['BRASIL']},
        'dic': {k: d.lista for k, d in dics.items()},
        'sinais': sinais,
        'gravidades': gravidades or {},
        # quantos blocos a ficha de fornecedor tem: o front acha o bloco
        # pela mesma conta do ident.bloco, sem baixar indice nenhum
        'forn': forn or {},
        'indice': {
            'nome': 'índice de conferência',
            'o_que_e': 'Soma dos sinais levantados, pesada pela intensidade de '
                       'cada um e por quanto do dinheiro daquela campanha ele '
                       'alcança. Vai de 0 a 100 e serve para ordenar uma fila '
                       'de conferência.',
            'o_que_nao_e': 'Não é medida de irregularidade. Nenhum sinal afirma '
                           'ilícito, vários apontam padrão inteiramente legal, e '
                           'o índice não sabe nada que os sinais já não digam. '
                           'O número só quer dizer alguma coisa ao lado dos '
                           'sinais que o compõem.',
            'peso': {str(k): v for k, v in PESO.items()},
            'quantos_somam': QUANTOS_SOMAM,
            'fora': FORA_DO_INDICE,
            'faixas': [[c, n] for c, n in FAIXAS],
        },
        # mantido enquanto o front antigo existir; o que vale e `sinais`
        'avisos': [f'{c}: {v["significa"]} O que NAO significa: '
                   f'{v["nao_significa"]}' for c, v in sorted(sinais.items())],
    })
