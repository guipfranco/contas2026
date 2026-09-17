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
import json
import os

from .agregar import CARGOS, NOME_UF
from .alarmes import faixa, indice
from .carregar import mascara

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
    """Uma linha por candidato da UF, para o ranking."""
    dtipo, dpart, dfed, dalarme = dics['tipo'], dics['partido'], dics['fed'], dics['alarme']
    linhas = []
    for a in sorted(aggs, key=lambda x: -x.contratado):
        al = alarmes_por_sq.get(a.sq, ())
        if not a.movimento and not al:
            # candidato sem nenhum movimento: cabecalho enxuto, para a busca
            linhas.append([a.sq, a.nome, a.nr, dpart.id(a.partido), a.cargo,
                           dfed.id(a.fed),
                           0, 0, 0, 0, 0, [], [], 0, 0])
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
        ])
    return grava(os.path.join(destino, 'uf', f'{uf}.json'),
                 {'uf': uf, 'n': len(linhas), 'c': linhas})


def _forn_linha(doc, e, alarmes_do_forn, cnae_nome):
    return [mascara(doc), (e[2] or 'Não informado')[:48], e[0], e[1],
            1 if len(doc) == 14 else 0,
            (cnae_nome.get(e[4]) or '')[:44],
            sorted(alarmes_do_forn)]


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
        'doadores': [[mascara(d), (e[2] or 'Não informado')[:48], e[0], e[1], e[3]]
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
    """
    dpart, dfed, dalarme = dics['partido'], dics['fed'], dics['alarme']
    dtipo = dics['tipo']
    linhas = []
    for a in sorted(aggs, key=lambda x: -x.contratado):
        # A visao nacional e sobre dinheiro. Quem nao declarou nada continua
        # achavel pela busca e pela propria UF, mas nao entra num ranking de
        # 20 mil linhas onde so ocuparia espaco.
        if not a.movimento:
            continue
        al = alarmes_por_sq.get(a.sq, ())
        linhas.append([
            a.sq, a.nome, a.nr, dpart.id(a.partido), a.cargo, dfed.id(a.fed),
            a.contratado, a.pago, a.receita, a.pago_publico,
            len(a.por_forn),
            [[dtipo.id(t), v] for t, v in a.por_tipo.most_common() if v],
            [[dalarme.id(x.codigo), x.grav] for x in al],
            1 if (a.genero or '').upper().startswith('F') else 0,
            indice(a.contratado, al),
            a.uf,
        ])
    sem_movimento = sum(1 for a in aggs if not a.movimento)
    return grava(os.path.join(destino, 'uf', 'BRASIL.json'),
                 {'uf': 'BRASIL', 'n': len(linhas),
                  'sem_movimento': sem_movimento, 'c': linhas})


def escrever_indice(aggs, dics, destino):
    """A busca nacional. Um array por candidato, o menor que da."""
    dpart = dics['partido']
    linhas = [[a.sq, a.nome, a.uf, a.cargo, dpart.id(a.partido), a.nr,
               1 if a.movimento else 0]
              for a in aggs]
    linhas.sort(key=lambda l: l[1])
    return grava(os.path.join(destino, 'indice.json'), {'c': linhas})


# C2 (nada declarado) e fato de ficha, nao item de fila: sao milhares de
# candidaturas sem movimento, e listar todas empurra para baixo o que importa.
FORA_DA_LISTA_NACIONAL = ('C2',)


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


def escrever_fornecedores(nac, destino, topo=400):
    """Os maiores fornecedores da eleicao. Recorte que o TSE nao oferece."""
    linhas = []
    for doc, e in sorted(nac.fornecedores.items(), key=lambda kv: -kv[1][0])[:topo]:
        linhas.append([mascara(doc), (e[2] or 'Não informado')[:48], e[0], e[1],
                       e[5], 1 if len(doc) == 14 else 0])
    por_cand = sorted(nac.fornecedores.items(), key=lambda kv: -kv[1][5])[:topo]
    espalhados = [[mascara(d), (e[2] or 'Não informado')[:48], e[0], e[1], e[5],
                   1 if len(d) == 14 else 0] for d, e in por_cand]
    return grava(os.path.join(destino, 'fornecedores.json'),
                 {'por_valor': linhas, 'por_candidatos': espalhados})


def escrever_meta(dics, contagens, ufs, cargos, gerado, tse, destino,
                  catalogo=None, gravidades=None):
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
