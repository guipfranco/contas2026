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
# O irmao, para quem doou: mesmos topos, um campo a mais por entrada (o tipo).
LIMITE_DOADOR_RECORTE_MB = 2.0
TIPOS_DOADOR = ('partido', 'campanha', 'coletivo', 'empresa', 'pf')
# O cruzado multiplica fornecedores por tipos de despesa, entao ele cresce pelo
# produto dos dois eixos e nao pela soma. Se estourar, o primeiro corte e o da
# celula, em TOPO_CRUZADO_CELULA.
LIMITE_FORN_CRUZADO_MB = 2.0
# O tipo por candidatura no pais media 36 % do arquivo nacional, que tem teto
# de 4 MB: sozinho ele cabe com folga em 5.
LIMITE_TIPOS_MB = 5.0

# O fluxo longo tem quatro colunas de dez nomes por recorte, sem a celula: se ele
# crescer ate aqui, o topo de alguma coluna parou de cortar.
LIMITE_FLUXO_MB = 1.0
# eleitos/BRASIL.json tem umas 3.500 linhas curtas no pais: uns 250 KB.
LIMITE_ELEITOS_MB = 1.0
# Cadeiras da eleicao anterior, para conferir a contagem bruta de anteriores.
# Assembleias e Camara Legislativa somam 1.059 juntas.
CADEIRAS = (('2022', ('1',), 1), ('2022', ('3',), 27), ('2022', ('5',), 27),
            ('2022', ('6',), 513), ('2022', ('7', '8'), 1059), ('2018', ('5',), 54))
CHAVES_RECORTE = ('uf', 'geral', 'geral_por_camp', 'partido', 'cargo',
                  'celula', 'fora')
CHAVES_CRUZADO = ('uf', 'forn', 'tipo', 'fora', 'partido')


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


def _queixa_da_entrada(e, sem_pessoas, campos=8):
    """O que uma entrada do recorte de fornecedor ou de doador nao pode ser.

    Devolve a queixa em texto, ou vazio. A entrada e [endereco, nome,
    documento, pj, valor, campanhas, lancamentos, tem_ficha], e a de doador
    traz o tipo no nono campo.
    """
    if len(e) != campos:
        return f'entrada com {len(e)} campos, esperado {campos}'
    if campos == 9 and e[8] not in TIPOS_DOADOR:
        return f'tipo de doador {e[8]!r} fora de {TIPOS_DOADOR}'
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


def _checar_recorte(rel, d, n_part, cargos, sem_pessoas, campos=8):
    """Confere um arquivo de recorte de fornecedor.

    Devolve (erros, total), e o total e a soma do recorte inteiro: o que as
    listas mostram mais o que elas declaram ter deixado de fora. Ele tem de ser
    o mesmo somando por partido, por cargo ou por celula.
    """
    erros = []
    fora = d.get('fora') or {}
    # Uma entrada quebrada interrompe a contagem da lista dela, e a partir dai toda
    # comparacao de soma acusaria uma diferenca que e consequencia, nao causa: a queixa
    # de verdade ficaria enterrada sob quatro linhas de "por partido soma X".
    ruim = []

    def soma(itens, chave):
        total = 0
        for e in itens:
            queixa = _queixa_da_entrada(e, sem_pessoas, campos)
            if queixa:
                erros.append(f'{rel}: {queixa}')
                ruim.append(chave)
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
    if not ruim and por_camp != total:
        erros.append(f'{rel}: por campanhas soma {por_camp}, por valor {total}')
    somado = 0
    for pid, itens in d['partido'].items():
        if not valida(pid):
            erros.append(f'{rel}: partido {pid!r} fora do dicionario')
            break
        somado += soma(itens, f'p:{pid}')
    else:
        if not ruim and somado != total:
            erros.append(f'{rel}: por partido soma {somado}, o geral {total}')
    somado = 0
    for cargo, itens in d['cargo'].items():
        if cargo not in cargos:
            erros.append(f'{rel}: cargo {cargo!r} fora do meta')
            break
        somado += soma(itens, f'c:{cargo}')
    else:
        if not ruim and somado != total:
            erros.append(f'{rel}: por cargo soma {somado}, o geral {total}')
    somado = 0
    for chave, itens in d['celula'].items():
        pid, _, cargo = chave.partition(':')
        if not valida(pid) or cargo not in cargos:
            erros.append(f'{rel}: celula {chave!r} invalida')
            break
        somado += soma(itens, f'p:{pid}:c:{cargo}')
    else:
        if not ruim and somado != total:
            erros.append(f'{rel}: por celula soma {somado}, o geral {total}')
    return erros, total


def _checar_tipos_doador(rel, d, n_part, cargos, sem_pessoas, total):
    """As listas de cada tipo de doador, que existem para a pessoa fisica aparecer.

    Cada tipo soma o mesmo pelo geral, por partido e por cargo, cada entrada traz
    o proprio tipo, e os tipos juntos somam o recorte inteiro.
    """
    erros = []
    tipos = d.get('tipos')
    if not isinstance(tipos, dict):
        return [f'{rel}: sem a chave \'tipos\'']
    soma_tipos = 0
    for tipo, r in tipos.items():
        if tipo not in TIPOS_DOADOR:
            erros.append(f'{rel}: tipo {tipo!r} fora de {TIPOS_DOADOR}')
            continue
        fora = r.get('fora') or {}
        somas = {}
        for chave, grupos in (('geral', {'': r.get('geral') or []}),
                              ('partido', r.get('partido') or {}),
                              ('cargo', r.get('cargo') or {})):
            s = 0
            for k, itens in grupos.items():
                if chave == 'partido' and not (k.isdigit() and int(k) < n_part):
                    erros.append(f'{rel}: tipos.{tipo}: partido {k!r} fora do dicionario')
                if chave == 'cargo' and k not in cargos:
                    erros.append(f'{rel}: tipos.{tipo}: cargo {k!r} fora do meta')
                for e in itens:
                    queixa = _queixa_da_entrada(e, sem_pessoas, 9)
                    if not queixa and e[8] != tipo:
                        queixa = f'entrada de tipo {e[8]!r} na lista de {tipo!r}'
                    if queixa:
                        erros.append(f'{rel}: tipos.{tipo}: {queixa}')
                        return erros
                    s += e[4]
                sobra = fora.get('geral' if chave == 'geral' else
                                 (f'p:{k}' if chave == 'partido' else f'c:{k}'))
                if sobra:
                    s += sobra[1]
            somas[chave] = s
        if len(set(somas.values())) != 1:
            erros.append(f'{rel}: tipos.{tipo} soma {somas}')
        soma_tipos += somas.get('geral', 0)
    if soma_tipos != total:
        erros.append(f'{rel}: os tipos somam {soma_tipos}, o recorte {total}')
    return erros


def _checar_fluxo(rel, d, n_part, cargos, sem_pessoas):
    """O fluxo longo de uma unidade. Devolve (erros, tot do recorte geral).

    As duas metades nao somam o mesmo dinheiro, e cada uma tem de fechar com o
    proprio total: a da receita pelas duas primeiras ligacoes, a do gasto pela
    terceira. O partido entrega a candidatura o que recebeu dos doadores.
    """
    erros = []
    for k in ('uf', 'd', 'f', 'c', 'r'):
        if k not in d:
            return [f'{rel}: sem a chave {k!r}'], None
    for e in d['d']:
        if len(e) != 4 or e[2] not in TIPOS_DOADOR or e[3] not in (0, 1) \
                or bool(e[0]) != bool(e[3]) or _cpf_no_texto(e[1]):
            return [f'{rel}: doador fora da forma: {e!r}'], None
        if sem_pessoas and e[0].startswith('p'):
            return [f'{rel}: pessoa fisica com endereco sem a chave: {e[0]!r}'], None
    for e in d['f']:
        if len(e) != 4 or e[2] not in (0, 1) or e[3] not in (0, 1) \
                or bool(e[0]) != bool(e[3]) or _cpf_no_texto(e[1]):
            return [f'{rel}: fornecedor fora da forma: {e!r}'], None
    for e in d['c']:
        if len(e) != 4 or not (0 <= e[2] < n_part) or e[3] not in cargos:
            return [f'{rel}: candidatura fora da forma: {e!r}'], None
    tamanhos = (len(d['d']), n_part, len(d['c']), len(d['f']))
    for nome, r in d['r'].items():
        cols, ligs, tot = r.get('col'), r.get('lig'), r.get('tot')
        if not (isinstance(cols, list) and len(cols) == 4 and isinstance(ligs, list)
                and len(ligs) == 3 and isinstance(tot, list) and len(tot) == 2):
            erros.append(f'{rel}: recorte {nome} fora da forma')
            continue
        if any(not (0 <= i < tamanhos[c]) for c in range(4) for i in cols[c]):
            erros.append(f'{rel}: recorte {nome} aponta fora do dicionario')
            continue
        somas, entra, sai = [], {}, {}
        for g, L in enumerate(ligs):
            s = 0
            for a, b, v in L:
                # -3 e o repasse do proprio partido, e so existe na origem da
                # primeira ligacao, a dos doadores
                piso_a = -3 if g == 0 else -2
                if not (piso_a <= a < len(cols[g])) or not (-2 <= b < len(cols[g + 1])) or v <= 0:
                    erros.append(f'{rel}: recorte {nome}, ligacao {g} invalida: {[a, b, v]}')
                    break
                s += v
                if g == 0:
                    entra[b] = entra.get(b, 0) + v
                if g == 1:
                    sai[a] = sai.get(a, 0) + v
            somas.append(s)
        if len(somas) == 3:
            if somas[0] != tot[0] or somas[1] != tot[0]:
                erros.append(f'{rel}: recorte {nome}, a receita soma {somas[:2]}, o total {tot[0]}')
            if somas[2] != tot[1]:
                erros.append(f'{rel}: recorte {nome}, o gasto soma {somas[2]}, o total {tot[1]}')
            if entra != sai:
                erros.append(f'{rel}: recorte {nome}, partido entrega diferente do que recebe')
    geral = (d['r'].get('geral') or {}).get('tot')
    if geral is None:
        erros.append(f'{rel}: sem o recorte geral')
    return erros, geral


def _checar_tipos_brasil(rel, d, linhas_br, n_tipo):
    """O gasto por tipo de cada candidatura do pais, no arquivo a parte.

    Duas contas para a mesma candidatura na mesma tela nao podem divergir: a
    soma dos tipos dela aqui tem de ser o contratado que a linha do ranking
    declara.
    """
    erros = []
    c = d.get('c')
    if not isinstance(c, dict) or not c:
        return [f'{rel}: sem o mapa "c"']
    contratado = {l[0]: l[6] for l in linhas_br}
    com_gasto = {sq for sq, v in contratado.items() if v}
    if set(c) != com_gasto:
        sobra = sorted(set(c) - com_gasto)[:1]
        falta = sorted(com_gasto - set(c))[:1]
        erros.append(f'{rel}: candidaturas fora do ranking {sobra}, '
                     f'sem tipo {falta}')
    for sq, pares in c.items():
        if sq not in contratado:
            continue
        soma = 0
        for par in pares:
            if len(par) != 2:
                erros.append(f'{rel}: par com {len(par)} campos em {sq}')
                break
            tid, valor = par
            if not (0 <= tid < n_tipo):
                erros.append(f'{rel}: id de tipo {tid} fora do dicionario')
                break
            soma += valor
        else:
            if soma != contratado[sq]:
                erros.append(f'{rel}: {sq} soma {soma} em tipos, e a linha do '
                             f'ranking diz {contratado[sq]}')
    return erros


def _queixa_do_forn(e, sem_pessoas):
    """O que uma entrada de `forn` do cruzado nao pode ser.

    A entrada e [endereco, nome, pj, tem_ficha]. Nao ha documento aqui, nem
    mascarado, entao o que se confere e o nome e a coerencia do link.
    """
    if len(e) != 4:
        return f'entrada de forn com {len(e)} campos, esperado 4'
    endereco, nome, pj, tem = e
    if pj not in (0, 1) or tem not in (0, 1):
        return f'pj {pj!r} ou tem_ficha {tem!r} fora de 0 e 1'
    if bool(endereco) != bool(tem):
        return f'tem_ficha {tem} com endereco {endereco!r}'
    if pj and not tem:
        return f'empresa sem ficha: {nome!r}'
    if not pj and endereco and not endereco.startswith('p'):
        return f'pessoa fisica com endereco de empresa: {endereco!r}'
    if not pj and tem and sem_pessoas:
        return ('pessoa fisica com ficha, e o meta diz que nenhuma foi '
                f'escrita: {endereco!r}')
    if _cpf_no_texto(nome):
        return f'CPF inteiro em campo de texto: {nome!r}'
    return ''


def _checar_forn_cruzado(rel, d, n_part, n_tipo, cargos, sem_pessoas,
                         total_do_tipo, ficha_do_endereco):
    """Confere um arquivo de fornecedor cruzado.

    Tres travas. As somas por partido, por cargo e por celula fecham com o
    geral dentro de cada tipo; nenhuma lista declara mais do que aquele tipo
    gastou no ranking; e o que a tela diz ter ficha tem de ter ficha tambem no
    recorte da mesma unidade, senao o mesmo nome abre pagina numa tela e nao
    abre na outra.
    """
    erros = []
    forn = d.get('forn') or []
    for e in forn:
        queixa = _queixa_do_forn(e, sem_pessoas)
        if queixa:
            erros.append(f'{rel}: {queixa}')
            break
    for e in forn:
        if len(e) == 4 and e[0] and e[0] in ficha_do_endereco:
            if e[3] != ficha_do_endereco[e[0]]:
                erros.append(f'{rel}: {e[0]} tem ficha {e[3]} aqui e '
                             f'{ficha_do_endereco[e[0]]} no recorte')
                break

    def chave_valida(chave):
        if chave == 'geral':
            return True
        partes = chave.split(':')
        if len(partes) % 2:
            return False
        for marca, valor in zip(partes[0::2], partes[1::2]):
            if marca == 'p':
                if not (valor.isdigit() and int(valor) < n_part):
                    return False
            elif marca == 'c':
                if valor not in cargos:
                    return False
            elif marca == 't':
                if not (valor.isdigit() and int(valor) < n_tipo):
                    return False
            else:
                return False
        return True

    por_tipo = d.get('tipo') or {}
    fora = d.get('fora') or {}
    if 'geral' not in por_tipo:
        return erros + [f'{rel}: sem o recorte geral']
    for chave in list(por_tipo) + list(fora) + list(d.get('partido') or {}):
        if not chave_valida(chave):
            erros.append(f'{rel}: recorte {chave!r} invalido')
            return erros

    def soma(chave, tid):
        lista = (por_tipo.get(chave) or {}).get(tid) or []
        for par in lista:
            if len(par) != 2 or not (0 <= par[0] < len(forn)):
                erros.append(f'{rel}: par {par!r} em {chave}/{tid}')
                return None
        sobra = ((fora.get(chave) or {}).get(tid) or [0, 0])
        if len(sobra) != 2 or sobra[0] < 0:
            erros.append(f'{rel}: fora[{chave!r}][{tid!r}] = {sobra!r}')
            return None
        return sum(v for _, v in lista) + sobra[1]

    chaves = list(por_tipo)
    for tid in por_tipo['geral']:
        geral = soma('geral', tid)
        if geral is None:
            return erros
        teto = total_do_tipo.get(int(tid))
        if teto is not None and geral > teto:
            erros.append(f'{rel}: tipo {tid} soma {geral}, acima do '
                         f'contratado {teto} do ranking')
        for prefixo, quais in (
                ('por partido', [k for k in chaves
                                 if k.startswith('p:') and ':c:' not in k]),
                ('por cargo', [k for k in chaves if k.startswith('c:')]),
                ('por celula', [k for k in chaves if ':c:' in k])):
            parcial = 0
            for k in quais:
                v = soma(k, tid)
                if v is None:
                    return erros
                parcial += v
            if parcial != geral:
                erros.append(f'{rel}: tipo {tid} soma {parcial} {prefixo} e '
                             f'{geral} no geral')
                break

    for chave, lista in (d.get('partido') or {}).items():
        marca = chave.split(':')
        do_tipo = {}
        if marca[0] == 't':
            do_tipo = {e[0]: e[1] for e in
                       (por_tipo['geral'].get(marca[1]) or [])}
        for entrada in lista:
            if len(entrada) != 2 or not (0 <= entrada[0] < len(forn)):
                erros.append(f'{rel}: fluxo {chave} com entrada {entrada!r}')
                break
            i_forn, pares = entrada
            total = 0
            for par in pares:
                if len(par) != 2 or not (0 <= par[0] < n_part) or par[1] <= 0:
                    erros.append(f'{rel}: fluxo {chave} com divisao {par!r}')
                    break
                total += par[1]
            else:
                if i_forn in do_tipo and total != do_tipo[i_forn]:
                    erros.append(f'{rel}: fluxo {chave} divide {total} e a '
                                 f'lista do tipo diz {do_tipo[i_forn]}')
                    break
                continue
            break
    return erros


def _checar_eleitos(d, n_part, n_fed, completo, mb=0.0):
    """A forma das linhas de eleitos/BRASIL.json e, no pais inteiro, a contagem
    dos eleitos de antes contra as cadeiras. Ate 2 % abaixo passa (cassacao,
    eleicao anulada); mais que isso, ou acima, e a ligacao que quebrou."""
    rel = 'eleitos/BRASIL.json'
    erros = []
    if mb > LIMITE_ELEITOS_MB:
        erros.append(f'{rel} tem {mb:.1f} MB, acima de {LIMITE_ELEITOS_MB}')
    cargos_antes = {'', '1', '3', '5', '6', '7', '8'}
    cargos_agora = cargos_antes | {'2', '4', '9', '10'}
    sqs = set()
    for l in d.get('c', []):
        if len(l) != 13:
            erros.append(f'{rel}: linha com {len(l)} campos, esperado 13')
            break
        nome, _, cargo_a, part_a, ano_a, destino, _, cargo_g, part_g, desf, sq, gen, mudou = l
        if not nome:
            erros.append(f'{rel}: linha sem nome')
            break
        if cargo_a not in cargos_antes or cargo_g not in cargos_agora:
            erros.append(f'{rel}: cargo {cargo_a!r}/{cargo_g!r} fora dos contados')
            break
        if not (-1 <= part_a < n_part) or not (-1 <= part_g < n_part):
            erros.append(f'{rel}: id de partido {part_a}/{part_g} fora do dicionario')
            break
        if ano_a not in (0, 2018, 2022) or not (0 <= destino <= 6) \
                or (ano_a == 0) != (destino == 0):
            erros.append(f'{rel}: destino {destino!r} com ano anterior {ano_a!r}')
            break
        if not (0 <= desf <= 4):
            erros.append(f'{rel}: desfecho {desf!r} fora de 0..4')
            break
        if gen not in ('', 'F', 'M') or mudou not in (0, 1):
            erros.append(f'{rel}: genero {gen!r} ou mudou {mudou!r} invalido')
            break
        if sq:
            if sq in sqs:
                erros.append(f'{rel}: sq {sq} repetido')
                break
            sqs.add(sq)
    for p, f in d.get('fed', {}).items():
        if not (0 <= int(p) < n_part) or not (0 <= f < n_fed):
            erros.append(f'{rel}: federacao {p}->{f} fora do dicionario')
            break
    # senadores de 2018 lidos pelo registro de 2022: UF de 2 letras -> n > 0
    absorvidos = d.get('absorvidos', {})
    if not isinstance(absorvidos, dict) or any(
            not re.fullmatch(r'[A-Z]{2}', uf) or type(n) is not int or n <= 0
            for uf, n in absorvidos.items()):
        erros.append(f'{rel}: absorvidos fora da forma UF -> inteiro positivo')
    if completo:
        ant = d.get('anteriores', {})
        for ano, cargos, cadeiras in CADEIRAS:
            achado = sum(ant.get(ano, {}).get(c, 0) for c in cargos)
            if achado > cadeiras or achado < cadeiras - cadeiras // 50:
                erros.append(f'{rel}: {achado} eleitos em {ano} no cargo '
                             f'{"+".join(cargos)}, esperado perto de {cadeiras}')
    return erros


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
    for chave in ('tem_desfecho', 'desfecho_em', 'desfecho_desconhecidos'):
        if chave not in meta:
            erros.append(f'meta sem "{chave}"')
    c = meta.get('contagens', {})
    if not c.get('candidaturas'):
        erros.append('meta.contagens.candidaturas e zero')
    if c.get('contratado', 0) < 0:
        erros.append('total contratado negativo')

    n_tipo, n_part, n_fed, n_al = (len(dic.get(k, [])) for k in
                                   ('tipo', 'partido', 'fed', 'alarme'))
    total_linhas = 0
    # quanto cada tipo de despesa gastou em cada unidade, somado das linhas do
    # ranking: e o teto que o cruzado de fornecedor nao pode passar
    tipos_por_unidade = {}
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
        do_tipo = tipos_por_unidade.setdefault(uf, {})
        for l in linhas:
            if len(l) == 17:
                for tid, v in l[11]:
                    do_tipo[tid] = do_tipo.get(tid, 0) + v
            if len(l) != 17:
                erros.append(f'uf/{uf}.json: linha com {len(l)} campos, esperado 17')
                break
            if not (0 <= l[16] <= 4):
                erros.append(f'uf/{uf}.json: desfecho {l[16]!r} fora de 0..4')
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
            if len(l) != 18:
                erros.append(f'uf/BRASIL.json: linha com {len(l)} campos, '
                             f'esperado 18')
                break
            if l[16] not in ufs_conhecidas:
                erros.append(f'uf/BRASIL.json: UF {l[16]!r} fora de meta.ufs')
                break
            if not (0 <= l[17] <= 4):
                erros.append(f'uf/BRASIL.json: desfecho {l[17]!r} fora de 0..4')
                break
        com_movimento = sum(v['com_gasto'] for v in meta.get('ufs', {}).values())
        if len(br) < com_movimento:
            erros.append(f'uf/BRASIL.json tem {len(br)} linhas, menos que as '
                         f'{com_movimento} com gasto')

        # o tipo por candidatura no pais: a linha do arquivo nacional nao o
        # carrega, e a visao geral cruza tipo com todas as outras dimensoes
        rel = os.path.join('tipos', 'BRASIL.json')
        if not falta(rel):
            caminho = os.path.join(pasta, rel)
            mb = os.path.getsize(caminho) / 1e6
            if mb > LIMITE_TIPOS_MB:
                erros.append(f'{rel} tem {mb:.1f} MB, acima de {LIMITE_TIPOS_MB}')
            d = _le(caminho)
            erros.extend(_checar_tipos_brasil(rel, d, br, n_tipo))
            do_tipo = tipos_por_unidade.setdefault('BRASIL', {})
            for pares in (d.get('c') or {}).values():
                for par in pares:
                    if len(par) == 2:
                        do_tipo[par[0]] = do_tipo.get(par[0], 0) + par[1]

    # recorte de fornecedor: fora da ficha, e a unica peca do site que carrega
    # nome de fornecedor. Duas coisas se conferem aqui: a soma fecha com o que
    # as UFs declararam, e nenhum CPF sai inteiro em campo de texto.
    n_part = len(dic.get('partido', []))
    cargos_meta = set(meta.get('cargos', {}))
    sem_pessoas = bool((meta.get('forn') or {}).get('pessoas_fora'))
    total_recorte = {}
    fichas_por_unidade = {}
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
        # o que o recorte diz ter ficha, para o cruzado da mesma unidade dizer
        # a mesma coisa sobre o mesmo endereco
        alvo = fichas_por_unidade.setdefault(unidade, {})
        for e in d['geral']:
            if len(e) == 8 and e[0]:
                alvo[e[0]] = e[7]
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

    # recorte de doador: a mesma conferencia do de fornecedor, com o tipo. Nao
    # ha teto pelo contratado aqui, porque a doacao estimavel nao entra na
    # receita do meta; o que se confere e o pais somar as UFs.
    total_doador = {}
    for unidade in sorted(meta.get('ufs', {})) + ['BRASIL']:
        rel = os.path.join('doador-recorte', f'{unidade}.json')
        if falta(rel):
            continue
        caminho = os.path.join(pasta, rel)
        mb = os.path.getsize(caminho) / 1e6
        if mb > LIMITE_DOADOR_RECORTE_MB:
            erros.append(f'{rel} tem {mb:.1f} MB, acima de '
                         f'{LIMITE_DOADOR_RECORTE_MB}')
        d = _le(caminho)
        if d.get('uf') != unidade:
            erros.append(f'{rel}: cabecalho diz {d.get("uf")!r}')
        faltam = [k for k in CHAVES_RECORTE if k not in d]
        if faltam:
            erros.append(f'{rel}: sem a chave {faltam[0]!r}')
            continue
        do_arquivo, total = _checar_recorte(rel, d, n_part, cargos_meta,
                                            sem_pessoas, campos=9)
        erros.extend(do_arquivo)
        erros.extend(_checar_tipos_doador(rel, d, n_part, cargos_meta,
                                          sem_pessoas, total))
        total_doador[unidade] = total
        # o mesmo endereco nao pode ter ficha numa lista e nao ter na outra
        alvo = fichas_por_unidade.setdefault(unidade, {})
        for e in d['geral']:
            if len(e) == 9 and e[0] and alvo.get(e[0], e[7]) != e[7]:
                erros.append(f'{rel}: {e[0]} com tem_ficha diferente do '
                             f'recorte de fornecedor')
                break
    if 'BRASIL' in total_doador:
        soma_ufs = sum(v for u, v in total_doador.items() if u != 'BRASIL')
        if total_doador['BRASIL'] != soma_ufs:
            erros.append(f'doador-recorte/BRASIL.json soma '
                         f'{total_doador["BRASIL"]}, as UFs somam {soma_ufs}')

    # o fluxo longo: cada unidade fecha consigo, e o pais soma as unidades
    tot_fluxo = {}
    for unidade in sorted(meta.get('ufs', {})) + ['BRASIL']:
        rel = os.path.join('fluxo', f'{unidade}.json')
        if falta(rel):
            continue
        caminho = os.path.join(pasta, rel)
        mb = os.path.getsize(caminho) / 1e6
        if mb > LIMITE_FLUXO_MB:
            erros.append(f'{rel} tem {mb:.1f} MB, acima de {LIMITE_FLUXO_MB}')
        d = _le(caminho)
        do_arquivo, tot = _checar_fluxo(rel, d, n_part, cargos_meta, sem_pessoas)
        erros.extend(do_arquivo)
        if tot:
            tot_fluxo[unidade] = tot
            if unidade != 'BRASIL' and tot[1] != meta['ufs'][unidade].get('contratado'):
                erros.append(f'{rel}: o gasto soma {tot[1]}, o meta diz '
                             f'{meta["ufs"][unidade].get("contratado")}')
    if 'BRASIL' in tot_fluxo:
        soma = [sum(t[i] for u, t in tot_fluxo.items() if u != 'BRASIL') for i in (0, 1)]
        if soma != tot_fluxo['BRASIL']:
            erros.append(f'fluxo/BRASIL.json soma {tot_fluxo["BRASIL"]}, as UFs {soma}')

    # fornecedor cruzado: quem recebeu por tipo de despesa, e de que partidos
    # saiu o dinheiro que chegou a ele. Sao as duas contas da visao geral que o
    # front nao tem como refazer a partir das linhas do ranking.
    for unidade in sorted(meta.get('ufs', {})) + ['BRASIL']:
        rel = os.path.join('forn-cruzado', f'{unidade}.json')
        if falta(rel):
            continue
        caminho = os.path.join(pasta, rel)
        mb = os.path.getsize(caminho) / 1e6
        if mb > LIMITE_FORN_CRUZADO_MB:
            erros.append(f'{rel} tem {mb:.1f} MB, acima de '
                         f'{LIMITE_FORN_CRUZADO_MB}')
        d = _le(caminho)
        if d.get('uf') != unidade:
            erros.append(f'{rel}: cabecalho diz {d.get("uf")!r}')
        faltam = [k for k in CHAVES_CRUZADO if k not in d]
        if faltam:
            erros.append(f'{rel}: sem a chave {faltam[0]!r}')
            continue
        erros.extend(_checar_forn_cruzado(
            rel, d, n_part, n_tipo, cargos_meta, sem_pessoas,
            tipos_por_unidade.get(unidade) or {},
            fichas_por_unidade.get(unidade) or {}))

    al = _le(os.path.join(pasta, 'alarmes.json')).get('a', [])
    for linha in al[:2000]:
        if len(linha) != 9:
            erros.append(f'alarmes.json: linha com {len(linha)} campos, esperado 9')
            break
        if not linha[8] or not any(ch.isdigit() for ch in linha[8]):
            erros.append(f'alarmes.json: texto sem numero: {linha[8][:60]!r}')
            break

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

    if meta.get('eleitos'):
        rel = os.path.join('eleitos', 'BRASIL.json')
        if not falta(rel):
            caminho = os.path.join(pasta, rel)
            # a contagem de cadeiras so vale quando a rodada leu o pais inteiro
            completo = len([u for u in meta.get('ufs', {}) if u != 'BR']) >= 27
            erros.extend(_checar_eleitos(_le(caminho), n_part, n_fed, completo,
                                         os.path.getsize(caminho) / 1e6))

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
