#!/usr/bin/env python3
"""Pergunta a Receita Federal o que ela sabe sobre cada CNPJ fornecedor.

Sem isto, dois dos sinais mais uteis nao existem: CNPJ aberto ha poucos dias e
CNPJ que a Receita nao registra como ativo.

**A fila e curta, e isso foi medido.** Sao 45.348 CNPJ fornecedores no pais,
mas 4.817 deles concentram 80 % do valor. A 2,5 consultas por segundo, o topo
sai em meia hora e a base inteira em cinco. Nao precisa do dump de 5 GB da
Receita: a API resolve, com cache commitado entre as rodadas.

**O cache guarda so o que os sinais usam.** A resposta crua tem QSA, CNAE
secundario e endereco, e sao dezenas de KB por empresa. Aqui ficam sete campos.
"""
import json
import os
import threading
import time

from . import receita

CAMPOS = ('razao_social', 'situacao_cadastral', 'data_situacao_cadastral',
          'data_inicio_atividade', 'cnae_principal', 'natureza_juridica',
          'porte_empresa')
DIAS_PARA_TENTAR_DE_NOVO = 7
PROVEDOR = 'minhareceita'      # o unico dos tres que devolve QSA sem bloquear
PROVEDOR_RESERVA = 'brasilapi'


def _iso(s):
    """A Receita devolve AAAA-MM-DD; alguns espelhos devolvem DD/MM/AAAA."""
    s = (s or '').strip()
    if len(s) == 10 and s[2] == '/':
        return f'{s[6:]}-{s[3:5]}-{s[:2]}'
    return s


def enxugar(d):
    saida = {c: (d.get(c) or '') for c in CAMPOS}
    saida['data_inicio_atividade'] = _iso(saida['data_inicio_atividade'])
    saida['data_situacao_cadastral'] = _iso(saida['data_situacao_cadastral'])
    socios = []
    for s in (d.get('QSA') or [])[:8]:
        nome = (s.get('nome_socio') or '').strip()
        if nome:
            socios.append(nome)
    if socios:
        saida['socios'] = socios
    return saida


def carregar_cache(caminho):
    """cnpj -> dados enxutos. Linha de erro entra como dict com 'erro'."""
    cache = {}
    if not os.path.exists(caminho):
        return cache
    with open(caminho, encoding='utf-8') as f:
        for linha in f:
            try:
                r = json.loads(linha)
            except ValueError:
                continue
            doc = r.get('cnpj') or r.get('id')
            if doc:
                cache[doc] = r.get('dados') or {'erro': r.get('erro', '?'),
                                                'quando': r.get('quando', '')}
    return cache


def fila_prioridade(nac, cache, hoje=''):
    """Quem consultar primeiro: quem recebeu mais dinheiro.

    Um CNPJ ja respondido nunca volta. Um que deu erro volta depois de uma
    semana, porque espelho fora do ar e coisa passageira.
    """
    fila = []
    for doc, e in nac.fornecedores.items():
        if len(doc) != 14:
            continue
        antes = cache.get(doc)
        if antes is not None and 'erro' not in antes:
            continue
        if antes and hoje:
            quando = antes.get('quando', '')
            if quando and _dias_desde(quando, hoje) < DIAS_PARA_TENTAR_DE_NOVO:
                continue
        fila.append((e[0], e[5], doc))
    fila.sort(reverse=True)
    return [doc for _, _, doc in fila]


def _dias_desde(d1, d2):
    from datetime import date
    try:
        a = date(int(d1[:4]), int(d1[5:7]), int(d1[8:10]))
        b = date(int(d2[:4]), int(d2[5:7]), int(d2[8:10]))
    except (ValueError, IndexError):
        return 999
    return (b - a).days


def enriquecer(fila, caminho_cache, orcamento_s=4800, rps=2.5, threads=5,
               hoje='', provedor=PROVEDOR):
    """Consulta ate o orcamento de tempo acabar. Grava linha a linha."""
    os.makedirs(os.path.dirname(caminho_cache) or '.', exist_ok=True)
    receita._parar.clear()
    parada = threading.Timer(orcamento_s, receita._parar.set)
    parada.daemon = True
    parada.start()
    t0 = time.time()
    feitos = [0]
    trava = threading.Lock()
    fila_iter = iter(list(fila))

    with open(caminho_cache, 'a', encoding='utf-8') as out:
        def trabalhador():
            while not receita._parar.is_set():
                with trava:
                    doc = next(fila_iter, None)
                if doc is None:
                    return
                ini = time.time()
                d, motivo = receita.consulta(provedor, doc)
                if d is None and motivo and '429' not in str(motivo):
                    d, motivo = receita.consulta(PROVEDOR_RESERVA, doc)
                reg = {'cnpj': doc, 'quando': hoje}
                if d is None:
                    reg['erro'] = motivo
                else:
                    reg['dados'] = enxugar(d)
                    reg['dados']['quando'] = hoje
                with trava:
                    out.write(json.dumps(reg, ensure_ascii=False) + '\n')
                    feitos[0] += 1
                    if feitos[0] % 500 == 0:
                        out.flush()
                        os.fsync(out.fileno())
                        dt = time.time() - t0
                        print(f'      {feitos[0]:,}/{len(fila):,} em {dt:.0f}s '
                              f'({feitos[0] / max(dt, 1):.1f}/s)', flush=True)
                sobra = (threads / rps) - (time.time() - ini)
                if sobra > 0:
                    time.sleep(sobra)

        ts = [threading.Thread(target=trabalhador, daemon=True) for _ in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        out.flush()
        os.fsync(out.fileno())
    parada.cancel()
    receita._parar.clear()
    return feitos[0]
