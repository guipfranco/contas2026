#!/usr/bin/env python3
"""Coletor da base publica de CNPJ, para a camada 3 da A0b.

Consulta um dos tres espelhos publicos dos dados abertos da Receita Federal e
grava a resposta em JSONL, ja normalizada para um formato unico.

Retomavel: rele o JSONL de saida e pula o id que ja foi coletado com sucesso.
Nao grava no tracker, nao pontua, nao julga. Quem grava e o enriquecer.py.

Uso:
    python .claude/skills/orgs-pontuar/receita.py \
        territorio-dados/17-mosc-9-zonas.csv <saida.jsonl> \
        [--provedor opencnpj|minhareceita|brasilapi] [--threads 6] [--rps 4]
        [--limite 3000] [--so-sem-email]

Medido em 20/08/2026, e o motivo de existirem tres provedores:

- opencnpj    e o unico que devolve **e-mail**. Bloqueia por volume: depois de
              cerca de 540 consultas veio 429 com Retry-After de 3408 s
              (Cloudflare 1015). O limite anunciado de 50/s nao e o real.
- minhareceita e brasilapi devolvem telefone, QSA, natureza juridica, situacao
              cadastral e CNAE, mas o campo de e-mail vem sempre nulo.

Por isso: colher o grosso nos dois ultimos, e completar o e-mail no opencnpj em
ritmo baixo, com --so-sem-email.

Armadilha: urllib com User-Agent padrao leva 403 no opencnpj. UA de cliente
conhecido resolve.
"""
import csv, json, os, queue, re, sys, threading, time, urllib.error, urllib.request

UA = 'curl/8.4.0'
TIMEOUT = 30
MAX_TENTATIVAS = 3
RETRY_AFTER_MAX = 120     # acima disso nao adianta esperar: aborta e reporta

PROVEDORES = {
    'opencnpj': 'https://api.opencnpj.org/',
    'minhareceita': 'https://minhareceita.org/',
    'brasilapi': 'https://brasilapi.com.br/api/cnpj/v1/',
}

_parar = threading.Event()
_motivo_parada = []


# ------------------------------------------------------------- normalizacao

def _fone_junto(s):
    """DDD e numero vem colados. '1146617431' -> ddd 11, numero 46617431.

    O DDD pode vir com zero a esquerda ('01138721957'), e ha numero gravado sem
    DDD nenhum. Com 10 ou 11 digitos uteis, os dois primeiros sao o DDD; com 8
    ou 9, nao ha DDD, e inventar um seria dado sem procedencia.
    """
    s = re.sub(r'\D', '', (s or '')).lstrip('0')
    if len(s) in (10, 11):
        return {'ddd': s[:2], 'numero': s[2:], 'is_fax': False}
    if len(s) in (8, 9):
        return {'ddd': '', 'numero': s, 'is_fax': False}
    return None


def normaliza(provedor, d):
    """Converte a resposta de qualquer provedor para o formato do opencnpj."""
    if provedor == 'opencnpj':
        return d

    tels = [t for t in (_fone_junto(d.get('ddd_telefone_1')),
                        _fone_junto(d.get('ddd_telefone_2'))) if t]
    sec = []
    for c in d.get('cnaes_secundarios') or []:
        cod = c.get('codigo') if isinstance(c, dict) else c
        if cod and str(cod) != '0':
            sec.append(str(cod).zfill(7))
    qsa = []
    for s in d.get('qsa') or []:
        qsa.append({
            'nome_socio': s.get('nome_socio') or '',
            'cnpj_cpf_socio': s.get('cnpj_cpf_do_socio') or '',
            'qualificacao_socio': s.get('qualificacao_socio') or '',
            'data_entrada_sociedade': s.get('data_entrada_sociedade') or '',
            'faixa_etaria': s.get('faixa_etaria') or '',
        })
    sit = (d.get('descricao_situacao_cadastral') or '').strip()
    return {
        'cnpj': d.get('cnpj') or '',
        'razao_social': d.get('razao_social') or '',
        'nome_fantasia': d.get('nome_fantasia') or '',
        'situacao_cadastral': sit.capitalize() if sit else '',
        'data_situacao_cadastral': d.get('data_situacao_cadastral') or '',
        'data_inicio_atividade': d.get('data_inicio_atividade') or '',
        'cnae_principal': str(d.get('cnae_fiscal') or '').zfill(7),
        'cnaes_secundarios': sec,
        'natureza_juridica': d.get('natureza_juridica') or '',
        'porte_empresa': d.get('porte') or '',
        'capital_social': str(d.get('capital_social') or ''),
        'email': (d.get('email') or '').strip(),
        'telefones': tels,
        'bairro': d.get('bairro') or '',
        'cep': d.get('cep') or '',
        'QSA': qsa,
    }


# ------------------------------------------------------------------ consulta

def consulta(provedor, cnpj):
    """Devolve (dict normalizado, None) ou (None, motivo)."""
    url = PROVEDORES[provedor] + cnpj
    req = urllib.request.Request(
        url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    espera = 1.0
    ultimo = 'esgotou as tentativas'
    for _ in range(MAX_TENTATIVAS):
        if _parar.is_set():
            return None, 'coleta abortada'
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
                return normaliza(provedor, json.load(f)), None
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                return None, 'nao encontrado na Receita'
            if e.code == 429:
                ra = e.headers.get('Retry-After')
                try:
                    ra = int(ra)
                except (TypeError, ValueError):
                    ra = 0
                if ra > RETRY_AFTER_MAX:
                    _motivo_parada.append(
                        f'{provedor}: 429 com Retry-After de {ra}s. '
                        'Limite de volume do provedor, nao adianta esperar.')
                    _parar.set()
                    return None, f'429 Retry-After {ra}s'
                time.sleep(max(ra, espera))
                espera *= 2
                ultimo = 'HTTP 429'
                continue
            if e.code in (500, 502, 503, 504):
                ultimo = f'HTTP {e.code}'
                time.sleep(espera)
                espera *= 2
                continue
            return None, f'HTTP {e.code}'
        except Exception as e:
            ultimo = f'{type(e).__name__}: {e}'
            time.sleep(espera)
            espera *= 2
    return None, ultimo


def coletar(pares, saida, provedor, threads=6, rps=0, checkpoint=500):
    feitos, sem_email = set(), set()
    if os.path.exists(saida):
        with open(saida, encoding='utf-8') as f:
            for linha in f:
                try:
                    r = json.loads(linha)
                except Exception:
                    continue
                if 'dados' in r:
                    feitos.add(r['id'])
                    if not (r['dados'].get('email') or '').strip():
                        sem_email.add(r['id'])
        print(f'retomando: {len(feitos)} ja coletados, '
              f'{len(sem_email)} deles sem e-mail', flush=True)

    fila = queue.Queue()
    for oid, cnpj in pares:
        if oid not in feitos:
            fila.put((oid, cnpj))
    total = fila.qsize()
    print(f'provedor {provedor}: a coletar {total} de {len(pares)}', flush=True)
    if not total:
        return 0, 0

    trava = threading.Lock()
    contas = {'ok': 0, 'falha': 0}
    t0 = time.time()
    intervalo = (threads / rps) if rps else 0

    with open(saida, 'a', encoding='utf-8') as out:
        def worker():
            while not _parar.is_set():
                try:
                    oid, cnpj = fila.get_nowait()
                except queue.Empty:
                    return
                ini = time.time()
                d, motivo = consulta(provedor, cnpj)
                reg = {'id': oid, 'cnpj': cnpj, 'fonte': provedor}
                if d is None:
                    reg['erro'] = motivo
                else:
                    reg['dados'] = d
                with trava:
                    out.write(json.dumps(reg, ensure_ascii=False) + '\n')
                    contas['ok' if d is not None else 'falha'] += 1
                    n = contas['ok'] + contas['falha']
                    if n % checkpoint == 0:
                        out.flush()
                        os.fsync(out.fileno())
                        dt = time.time() - t0
                        print(f'  {n}/{total} em {dt:.0f}s '
                              f'({n/max(dt,1):.1f}/s, {contas["falha"]} falhas)',
                              flush=True)
                sobra = intervalo - (time.time() - ini)
                if sobra > 0:
                    time.sleep(sobra)

        ts = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        out.flush()
        os.fsync(out.fileno())

    dt = time.time() - t0
    print(f'fim: {contas["ok"]} respondidos, {contas["falha"]} falhas, '
          f'{dt:.0f}s ({(contas["ok"]+contas["falha"])/max(dt,1):.1f}/s)', flush=True)
    for m in _motivo_parada[:1]:
        print(f'PAROU: {m}', flush=True)
    return contas['ok'], contas['falha']


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    entrada, saida = sys.argv[1], sys.argv[2]

    def opt(nome, padrao, tipo=int):
        return tipo(sys.argv[sys.argv.index(nome) + 1]) if nome in sys.argv else padrao

    provedor = opt('--provedor', 'brasilapi', str)
    if provedor not in PROVEDORES:
        print(f'provedor desconhecido: {provedor}. Use um de {list(PROVEDORES)}')
        return 2
    threads, rps, limite = opt('--threads', 6), opt('--rps', 0), opt('--limite', 0)
    so_sem_email = '--so-sem-email' in sys.argv

    with open(entrada, newline='', encoding='utf-8') as f:
        linhas = list(csv.DictReader(f))
    pares = [(r['id'], (r['cnpj'] or '').strip()) for r in linhas
             if (r.get('cnpj') or '').strip()]

    if so_sem_email:
        # relê o jsonl e reenfileira quem esta la sem e-mail, para o opencnpj
        alvo, tem = set(), set()
        if os.path.exists(saida):
            with open(saida, encoding='utf-8') as f:
                for linha in f:
                    try:
                        r = json.loads(linha)
                    except Exception:
                        continue
                    if 'dados' not in r:
                        continue
                    if (r['dados'].get('email') or '').strip():
                        tem.add(r['id'])
                    else:
                        alvo.add(r['id'])
        alvo -= tem
        pares = [(i, c) for i, c in pares if i in alvo]
        print(f'--so-sem-email: {len(tem)} ja tem e-mail, '
              f'{len(pares)} a tentar', flush=True)
        saida = saida.replace('.jsonl', f'.{provedor}-email.jsonl')

    if limite:
        pares = pares[:limite]
    print(f'{len(linhas)} linhas em {entrada}, {len(pares)} alvos', flush=True)
    coletar(pares, saida, provedor, threads=threads, rps=rps)
    return 0


if __name__ == '__main__':
    sys.exit(main())
