#!/usr/bin/env python3
"""Confere o que vai ao ar. Aponta, nunca conserta.

Roda depois de escrever e antes de publicar. Se apontar qualquer coisa, a
rodada falha e o site de ontem continua no ar, que e melhor do que publicar
numero errado.
"""
import json
import os
import re
import sys

LIMITE_UF_MB = 3.0
LIMITE_BRASIL_MB = 4.0
LIMITE_INDICE_MB = 3.0
# Sentinela do corte do recorte de fornecedor: sem os topos, o arquivo do pais
# passaria de 34 MB. Se ele crescer ate aqui, o corte parou de funcionar.
LIMITE_RECORTE_MB = 2.0

CHAVES_RECORTE = ('uf', 'geral', 'geral_por_camp', 'partido', 'cargo',
                  'celula', 'fora')


def _le(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def _cpf_no_texto(texto):
    """O primeiro CPF de verdade dentro de um texto, ou vazio.

    So campo de texto passa por aqui, nunca o arquivo cru: um valor de R$ 100
    milhoes em centavos tem onze digitos e seria lido como CPF.
    """
    from .carregar import cpf_valido
    for corrida in re.findall(r'(?<!\d)\d{11}(?!\d)', texto or ''):
        if cpf_valido(corrida):
            return corrida
    return ''


def _queixa_da_entrada(e, sem_pessoas):
    """O que uma entrada do recorte de fornecedor nao pode ser.

    Devolve a queixa em texto, ou vazio. A entrada e [endereco, nome,
    documento, pj, valor, campanhas, lancamentos, tem_ficha].
    """
    if len(e) != 8:
        return f'entrada com {len(e)} campos, esperado 8'
    endereco, nome, doc, pj, tem = e[0], e[1], e[2], e[3], e[7]
    if pj not in (0, 1) or tem not in (0, 1):
        return f'pj {pj!r} ou tem_ficha {tem!r} fora de 0 e 1'
    if bool(endereco) != bool(tem):
        return f'tem_ficha {tem} com endereco {endereco!r}'
    digitos = ''.join(ch for ch in (doc or '') if ch.isdigit())
    if pj:
        if not tem:
            return f'empresa {doc!r} sem ficha'
        if len(digitos) != 14:
            return f'documento de empresa com {len(digitos)} digitos: {doc!r}'
    else:
        if '*' not in (doc or ''):
            return f'documento de pessoa fisica sem mascara: {doc!r}'
        if endereco and not endereco.startswith('p'):
            return f'pessoa fisica com endereco de empresa: {endereco!r}'
        if sem_pessoas and tem:
            return ('pessoa fisica com ficha, e o meta diz que nenhuma foi '
                    f'escrita: {endereco!r}')
    for campo in (nome, doc):
        if _cpf_no_texto(campo):
            return f'CPF inteiro em campo de texto: {campo!r}'
    return ''


def _checar_recorte(rel, d, n_part, cargos, sem_pessoas):
    """Confere um arquivo de recorte de fornecedor.

    Devolve (erros, total), e o total e a soma do recorte inteiro: o que as
    listas mostram mais o que elas declaram ter deixado de fora. Ele tem de ser
    o mesmo somando por partido, por cargo ou por celula.
    """
    erros = []
    fora = d.get('fora') or {}

    def soma(itens, chave):
        total = 0
        for e in itens:
            queixa = _queixa_da_entrada(e, sem_pessoas)
            if queixa:
                erros.append(f'{rel}: {queixa}')
                break
            total += e[4]
        sobra = fora.get(chave)
        if sobra is None:
            return total
        if len(sobra) != 2 or sobra[0] <= 0:
            erros.append(f'{rel}: fora[{chave!r}] = {sobra!r}')
            return total
        return total + sobra[1]

    def valida(pid):
        return pid.isdigit() and int(pid) < n_part

    total = soma(d['geral'], 'geral')
    por_camp = soma(d['geral_por_camp'], 'geral_por_camp')
    if por_camp != total:
        erros.append(f'{rel}: por campanhas soma {por_camp}, por valor {total}')
    somado = 0
    for pid, itens in d['partido'].items():
        if not valida(pid):
            erros.append(f'{rel}: partido {pid!r} fora do dicionario')
            break
        somado += soma(itens, f'p:{pid}')
    else:
        if somado != total:
            erros.append(f'{rel}: por partido soma {somado}, o geral {total}')
    somado = 0
    for cargo, itens in d['cargo'].items():
        if cargo not in cargos:
            erros.append(f'{rel}: cargo {cargo!r} fora do meta')
            break
        somado += soma(itens, f'c:{cargo}')
    else:
        if somado != total:
            erros.append(f'{rel}: por cargo soma {somado}, o geral {total}')
    somado = 0
    for chave, itens in d['celula'].items():
        pid, _, cargo = chave.partition(':')
        if not valida(pid) or cargo not in cargos:
            erros.append(f'{rel}: celula {chave!r} invalida')
            break
        somado += soma(itens, f'p:{pid}:c:{cargo}')
    else:
        if somado != total:
            erros.append(f'{rel}: por celula soma {somado}, o geral {total}')
    return erros, total


def validar(pasta):
    erros = []

    def falta(caminho):
        if not os.path.exists(os.path.join(pasta, caminho)):
            erros.append(f'{caminho} nao foi escrito')
            return True
        return False

    for obrigatorio in ('meta.json', 'indice.json', 'alarmes.json'):
        falta(obrigatorio)
    if erros:
        return erros

    meta = _le(os.path.join(pasta, 'meta.json'))
    dic = meta.get('dic', {})
    for chave in ('tipo', 'partido', 'fed', 'alarme'):
        if chave not in dic:
            erros.append(f'meta.dic sem "{chave}"')
    if not meta.get('ufs'):
        erros.append('meta.ufs vazio')
    c = meta.get('contagens', {})
    if not c.get('candidaturas'):
        erros.append('meta.contagens.candidaturas e zero')
    if c.get('contratado', 0) < 0:
        erros.append('total contratado negativo')

    n_tipo, n_part, n_fed, n_al = (len(dic.get(k, [])) for k in
                                   ('tipo', 'partido', 'fed', 'alarme'))
    total_linhas = 0
    for uf in sorted(meta.get('ufs', {})):
        caminho = os.path.join(pasta, 'uf', f'{uf}.json')
        if falta(os.path.join('uf', f'{uf}.json')):
            continue
        mb = os.path.getsize(caminho) / 1e6
        if mb > LIMITE_UF_MB:
            erros.append(f'uf/{uf}.json tem {mb:.1f} MB, acima de {LIMITE_UF_MB}')
        d = _le(caminho)
        linhas = d.get('c', [])
        total_linhas += len(linhas)
        if len(linhas) != meta['ufs'][uf]['n']:
            erros.append(f'uf/{uf}.json tem {len(linhas)} linhas, meta diz '
                         f'{meta["ufs"][uf]["n"]}')
        soma = 0
        for l in linhas:
            if len(l) != 16:
                erros.append(f'uf/{uf}.json: linha com {len(l)} campos, esperado 16')
                break
            if not (0 <= l[3] < n_part):
                erros.append(f'uf/{uf}.json: id de partido {l[3]} fora do dicionario')
                break
            if not (0 <= l[5] < n_fed):
                erros.append(f'uf/{uf}.json: id de federacao {l[5]} fora do dicionario')
                break
            for tid, v in l[11]:
                if not (0 <= tid < n_tipo):
                    erros.append(f'uf/{uf}.json: id de tipo {tid} fora do dicionario')
                    break
            for aid, grav in l[12]:
                if not (0 <= aid < n_al) or grav not in (1, 2, 3):
                    erros.append(f'uf/{uf}.json: alarme {aid}/{grav} invalido')
                    break
            soma += l[6]
        if soma != meta['ufs'][uf]['contratado']:
            erros.append(f'uf/{uf}.json: soma {soma} != meta {meta["ufs"][uf]["contratado"]}')

    indice = _le(os.path.join(pasta, 'indice.json')).get('c', [])
    if len(indice) != total_linhas:
        erros.append(f'indice tem {len(indice)} candidatos, as UFs somam {total_linhas}')
    mb = os.path.getsize(os.path.join(pasta, 'indice.json')) / 1e6
    if mb > LIMITE_INDICE_MB:
        erros.append(f'indice.json tem {mb:.1f} MB, acima de {LIMITE_INDICE_MB}')

    if not falta(os.path.join('uf', 'BRASIL.json')):
        caminho = os.path.join(pasta, 'uf', 'BRASIL.json')
        mb = os.path.getsize(caminho) / 1e6
        if mb > LIMITE_BRASIL_MB:
            erros.append(f'uf/BRASIL.json tem {mb:.1f} MB, acima de '
                         f'{LIMITE_BRASIL_MB}')
        br = _le(caminho).get('c', [])
        ufs_conhecidas = set(meta.get('ufs', {}))
        for l in br[:500]:
            if len(l) != 17:
                erros.append(f'uf/BRASIL.json: linha com {len(l)} campos, '
                             f'esperado 17')
                break
            if l[16] not in ufs_conhecidas:
                erros.append(f'uf/BRASIL.json: UF {l[16]!r} fora de meta.ufs')
                break
        com_movimento = sum(v['com_gasto'] for v in meta.get('ufs', {}).values())
        if len(br) < com_movimento:
            erros.append(f'uf/BRASIL.json tem {len(br)} linhas, menos que as '
                         f'{com_movimento} com gasto')

    # recorte de fornecedor: fora da ficha, e a unica peca do site que carrega
    # nome de fornecedor. Duas coisas se conferem aqui: a soma fecha com o que
    # as UFs declararam, e nenhum CPF sai inteiro em campo de texto.
    n_part = len(dic.get('partido', []))
    cargos_meta = set(meta.get('cargos', {}))
    sem_pessoas = bool((meta.get('forn') or {}).get('pessoas_fora'))
    total_recorte = {}
    for unidade in sorted(meta.get('ufs', {})) + ['BRASIL']:
        rel = os.path.join('forn-recorte', f'{unidade}.json')
        if falta(rel):
            continue
        caminho = os.path.join(pasta, rel)
        mb = os.path.getsize(caminho) / 1e6
        if mb > LIMITE_RECORTE_MB:
            erros.append(f'{rel} tem {mb:.1f} MB, acima de {LIMITE_RECORTE_MB}')
        d = _le(caminho)
        if d.get('uf') != unidade:
            erros.append(f'{rel}: cabecalho diz {d.get("uf")!r}')
        faltam = [k for k in CHAVES_RECORTE if k not in d]
        if faltam:
            erros.append(f'{rel}: sem a chave {faltam[0]!r}')
            continue
        do_arquivo, total = _checar_recorte(rel, d, n_part, cargos_meta,
                                            sem_pessoas)
        erros.extend(do_arquivo)
        total_recorte[unidade] = total
        if unidade != 'BRASIL':
            # e menor ou igual, nunca igual: em RR, 660 linhas de despesa nao
            # trazem documento de fornecedor e somam R$ 7.643,40 que existem no
            # contratado e nao tem a quem ser atribuidos
            contratado = meta['ufs'][unidade].get('contratado', 0)
            if total > contratado:
                erros.append(f'{rel}: fornecedores somam {total}, acima do '
                             f'contratado {contratado}')
    if 'BRASIL' in total_recorte:
        soma_ufs = sum(v for u, v in total_recorte.items() if u != 'BRASIL')
        if total_recorte['BRASIL'] != soma_ufs:
            erros.append(f'forn-recorte/BRASIL.json soma '
                         f'{total_recorte["BRASIL"]}, as UFs somam {soma_ufs}')
        # e quem a lista diz ter ficha tem de ter ficha: nome com link para
        # pagina que nao existe e pior que nome sem link
        blocos_forn = (meta.get('forn') or {}).get('blocos') or 0
        if blocos_forn:
            from .ident import bloco as bloco_de
            d = _le(os.path.join(pasta, 'forn-recorte', 'BRASIL.json'))
            lidos, sem_ficha = {}, 0
            for e in [x for x in d['geral'] if len(x) == 8 and x[7]][:20]:
                n = bloco_de(e[0], blocos_forn)
                if n not in lidos:
                    p = os.path.join(pasta, 'forn', f'{n}.json')
                    lidos[n] = _le(p).get('f', {}) if os.path.exists(p) else {}
                if e[0] not in lidos[n]:
                    sem_ficha += 1
            if sem_ficha:
                erros.append(f'forn-recorte/BRASIL.json: {sem_ficha} '
                             f'fornecedores marcados com ficha nao tem ficha')

    al = _le(os.path.join(pasta, 'alarmes.json')).get('a', [])
    for linha in al[:2000]:
        if len(linha) != 9:
            erros.append(f'alarmes.json: linha com {len(linha)} campos, esperado 9')
            break
        if not linha[8] or not any(ch.isdigit() for ch in linha[8]):
            erros.append(f'alarmes.json: texto sem numero: {linha[8][:60]!r}')
            break

    # panorama: os agregados tem de fechar com o que as UFs somam
    if not falta('panorama.json'):
        pan = _le(os.path.join(pasta, 'panorama.json'))
        total_uf = sum(v['contratado'] for v in meta.get('ufs', {}).values())
        for grupo in ('partidos', 'cargos', 'ufs'):
            if not pan.get(grupo):
                erros.append(f'panorama.json: {grupo} vazio')
                continue
            soma = sum(x['contratado'] for x in pan[grupo])
            if soma != total_uf:
                erros.append(f'panorama.json: {grupo} soma {soma}, as UFs somam '
                             f'{total_uf}')
        n_cand = sum(f['n'] for f in pan.get('faixas_cand', []))
        if n_cand != c.get('candidaturas'):
            erros.append(f'panorama.json: faixas cobrem {n_cand} candidaturas, '
                         f'o meta diz {c.get("candidaturas")}')
        n_forn = sum(f['n'] for f in pan.get('faixas_forn', []))
        if n_forn != c.get('fornecedores'):
            erros.append(f'panorama.json: faixas cobrem {n_forn} fornecedores, '
                         f'o meta diz {c.get("fornecedores")}')

    # fichas de fornecedor: o front acha o bloco pela conta do ident, entao o
    # numero de blocos declarado no meta tem de bater com o que foi escrito, e
    # nenhuma ficha de pessoa fisica pode trazer documento sem mascara
    blocos = (meta.get('forn') or {}).get('blocos') or 0
    if not blocos:
        erros.append('meta.forn.blocos ausente: o front nao acha a ficha')
    else:
        pasta_forn = os.path.join(pasta, 'forn')
        if not os.path.isdir(pasta_forn):
            erros.append('forn/ nao foi escrito')
        else:
            arquivos = [x for x in os.listdir(pasta_forn) if x.endswith('.json')]
            if not arquivos:
                erros.append('forn/ esta vazio')
            from .ident import bloco as bloco_de
            for nome in sorted(arquivos)[:3]:
                d = _le(os.path.join(pasta_forn, nome))
                n = int(nome[:-5])
                if d.get('b') != n:
                    erros.append(f'forn/{nome}: cabecalho diz bloco {d.get("b")}')
                    break
                # o front acha o bloco refazendo esta conta: ficha no arquivo
                # errado e ficha que nunca abre
                fora = [k for k in list(d.get('f', {}))[:50] if bloco_de(k, blocos) != n]
                if fora:
                    erros.append(f'forn/{nome}: {len(fora)} fichas no bloco errado '
                                 f'(ex.: {fora[0]})')
                    break
                for chave, f in list(d.get('f', {}).items())[:50]:
                    if not f.get('nome') or f.get('valor') is None:
                        erros.append(f'forn/{nome}: ficha {chave} incompleta')
                        break
                    if not f.get('pj') and not chave.startswith('p'):
                        erros.append(f'forn/{nome}: pessoa fisica com '
                                     f'identificador {chave!r}')
                        break
                    doc = f.get('doc') or ''
                    if not f.get('pj') and doc and '*' not in doc:
                        erros.append(f'forn/{nome}: documento sem mascara')
                        break

    # amostra de fichas: existe o arquivo de quem tem movimento?
    faltando = 0
    for uf in sorted(meta.get('ufs', {}))[:3]:
        d = _le(os.path.join(pasta, 'uf', f'{uf}.json'))
        for l in d.get('c', [])[:40]:
            if l[6] and not os.path.exists(os.path.join(pasta, 'cand', f'{l[0]}.json')):
                faltando += 1
    if faltando:
        erros.append(f'{faltando} fichas de candidatos com gasto nao foram escritas')

    return erros


def main(argv=None):
    pasta = (argv or sys.argv[1:] or ['site/dados'])[0]
    erros = validar(pasta)
    if erros:
        print(f'{len(erros)} problemas em {pasta}:')
        for e in erros:
            print(f'   {e}')
        return 1
    print(f'{pasta}: limpo')
    return 0


if __name__ == '__main__':
    sys.exit(main())
