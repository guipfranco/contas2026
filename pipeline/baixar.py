#!/usr/bin/env python3
"""Baixa as fontes do TSE, e diagnostica quando elas nao vem.

O CDN do TSE fica atras de Akamai. Em 17/09/2026, medido da maquina do
Guilherme, **toda** requisicao automatica levou 403: curl, urllib e
Invoke-WebRequest, com e sem sandbox, com qualquer User-Agent. So o Chrome
passou. Nao se sabe se o runner do GitHub Actions passa, e e isso que o
`spike` responde.

Caminhos, em ordem de preferencia:

1. rede: GET direto no CDN, em streaming para disco.
2. release: `gh release download fontes`, quando o 403 persiste e alguem
   espelhou os zips pelo navegador (ver ferramentas/espelhar.py).
3. local: --fonte-local aponta para uma pasta com os zips ja baixados.

Uso:
    python -m pipeline.baixar --spike
    python -m pipeline.baixar --destino /tmp/tse
"""
import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

CDN = 'https://cdn.tse.jus.br/estatistica/sead/odsele'

FONTES = {
    'candidatos': f'{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip',
    'consulta_cand': f'{CDN}/consulta_cand/consulta_cand_2026.zip',
    'cnpj_campanha': f'{CDN}/prestacao_contas/CNPJ_campanha_2026.zip',
    'orgaos': f'{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_orgaos_partidarios_2026.zip',
}

# O menor dos quatro: serve de canario, baixa em segundos.
CANARIO = 'cnpj_campanha'

UA_CHROME = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')
UA_CURL = 'curl/8.4.0'
UA_PY = None  # urllib default: Python-urllib/3.x

CABECALHO_NAVEGADOR = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
              'image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Connection': 'keep-alive',
}

TIMEOUT = 120
BLOCO = 1024 * 256


def _req(url, ua=UA_CHROME, extra=None, metodo='GET'):
    cab = {}
    if ua:
        cab['User-Agent'] = ua
    if extra:
        cab.update(extra)
    return urllib.request.Request(url, headers=cab, method=metodo)


def baixar(url, destino, ua=UA_CHROME, tentativas=3, navegador=True):
    """GET em streaming para disco. Devolve (caminho, last_modified, bytes).

    Retoma com Range quando o arquivo parcial ja existe. Levanta a excecao da
    ultima tentativa quando nao consegue.
    """
    extra = dict(CABECALHO_NAVEGADOR) if navegador else {}
    extra.pop('Accept-Encoding', None)  # zip ja vem comprimido; evita dupla camada
    parcial = str(destino) + '.parcial'
    erro = None
    for n in range(tentativas):
        jah = os.path.getsize(parcial) if os.path.exists(parcial) else 0
        cab = dict(extra)
        if jah:
            cab['Range'] = f'bytes={jah}-'
        try:
            with urllib.request.urlopen(_req(url, ua, cab), timeout=TIMEOUT) as r:
                lm = r.headers.get('Last-Modified') or ''
                modo = 'ab' if (jah and r.status == 206) else 'wb'
                if modo == 'wb':
                    jah = 0
                with open(parcial, modo) as f:
                    while True:
                        b = r.read(BLOCO)
                        if not b:
                            break
                        f.write(b)
            os.replace(parcial, destino)
            return destino, lm, os.path.getsize(destino)
        except Exception as e:  # noqa: BLE001 - o spike quer o motivo, seja qual for
            erro = e
            if n < tentativas - 1:
                time.sleep(2 ** n)
    raise erro


# ------------------------------------------------------------------- spike

def _tenta(nome, url, ua, extra=None, metodo='GET', faixa=None):
    """Uma sonda. Devolve dict com o que aconteceu, nunca levanta."""
    cab = dict(extra or {})
    if faixa:
        cab['Range'] = f'bytes=0-{faixa - 1}'
    t0 = time.time()
    r = {'sonda': nome, 'ua': ua or 'Python-urllib (padrao)', 'metodo': metodo}
    try:
        with urllib.request.urlopen(_req(url, ua, cab, metodo), timeout=60) as resp:
            corpo = resp.read() if metodo == 'GET' else b''
            r.update(status=resp.status, bytes=len(corpo),
                     last_modified=resp.headers.get('Last-Modified') or '',
                     content_length=resp.headers.get('Content-Length') or '',
                     server=resp.headers.get('Server') or '',
                     ok=True)
    except urllib.error.HTTPError as e:
        r.update(status=e.code, ok=False, erro=f'HTTP {e.code}',
                 server=e.headers.get('Server') if e.headers else '')
    except Exception as e:  # noqa: BLE001
        r.update(status=None, ok=False, erro=f'{type(e).__name__}: {e}')
    r['segundos'] = round(time.time() - t0, 2)
    return r


def _curl(url):
    """A mesma pergunta pelo curl do sistema, que tem TLS diferente do Python."""
    try:
        p = subprocess.run(
            ['curl', '-sS', '-o', os.devnull, '-D', '-', '--max-time', '60',
             '--range', '0-1023', '-A', UA_CHROME, url],
            capture_output=True, text=True, timeout=90)
        linha = (p.stdout or '').splitlines()
        return {'sonda': 'curl do sistema', 'saida': linha[0] if linha else '',
                'ok': ' 200' in (linha[0] if linha else '') or ' 206' in (linha[0] if linha else ''),
                'erro': (p.stderr or '').strip()[:200]}
    except Exception as e:  # noqa: BLE001
        return {'sonda': 'curl do sistema', 'ok': False, 'erro': str(e)[:200]}


def spike():
    """Descobre se daqui da para baixar do TSE, e por qual caminho.

    Imprime um relatorio legivel e devolve 0 quando algum caminho serve.
    """
    print('=' * 72)
    print('SPIKE: o CDN do TSE responde a cliente automatico deste runner?')
    print(f'python {sys.version.split()[0]} | openssl {ssl.OPENSSL_VERSION}')
    print('=' * 72)

    relatorio = {'sondas': [], 'veredito': None}
    url = FONTES[CANARIO]

    print(f'\n-- 1. tres User-Agents no canario ({CANARIO}, 1 KB)')
    for rotulo, ua, extra in (
            ('UA de Chrome + cabecalho de navegador', UA_CHROME, CABECALHO_NAVEGADOR),
            ('UA de curl, sem mais nada', UA_CURL, None),
            ('UA padrao do urllib', UA_PY, None)):
        r = _tenta(rotulo, url, ua, extra, faixa=1024)
        relatorio['sondas'].append(r)
        print(f'   {"OK " if r["ok"] else "NAO"} {rotulo}: '
              f'status={r.get("status")} {r.get("erro", "")} '
              f'servidor={r.get("server", "")!r} ({r["segundos"]}s)')

    print('\n-- 2. curl do sistema no canario')
    r = _curl(url)
    relatorio['sondas'].append(r)
    print(f'   {"OK " if r["ok"] else "NAO"} {r.get("saida") or r.get("erro")}')

    print('\n-- 3. HEAD em cada uma das quatro fontes')
    for nome, u in FONTES.items():
        r = _tenta(f'HEAD {nome}', u, UA_CHROME, CABECALHO_NAVEGADOR, metodo='HEAD')
        r['fonte'] = nome
        relatorio['sondas'].append(r)
        tam = r.get('content_length') or '?'
        if tam.isdigit():
            tam = f'{int(tam) / 1e6:.1f} MB'
        print(f'   {"OK " if r["ok"] else "NAO"} {nome}: status={r.get("status")} '
              f'tamanho={tam} last-modified={r.get("last_modified") or "?"} '
              f'{r.get("erro", "")}')

    print('\n-- 4. download inteiro do canario, com teste de integridade')
    destino = os.path.join(os.environ.get('RUNNER_TEMP', '.'), 'canario.zip')
    try:
        t0 = time.time()
        _, lm, tam = baixar(url, destino)
        dt = max(time.time() - t0, 0.01)
        with zipfile.ZipFile(destino) as z:
            ruim = z.testzip()
            membros = z.namelist()[:5]
        ok = ruim is None
        print(f'   {"OK " if ok else "NAO"} {tam / 1e6:.1f} MB em {dt:.0f}s '
              f'({tam / 1e6 / dt:.1f} MB/s), last-modified={lm}')
        print(f'   membros: {membros}')
        relatorio['sondas'].append({'sonda': 'download do canario', 'ok': ok,
                                    'bytes': tam, 'last_modified': lm,
                                    'membros': membros})
        os.remove(destino)
    except Exception as e:  # noqa: BLE001
        print(f'   NAO falhou: {type(e).__name__}: {e}')
        relatorio['sondas'].append({'sonda': 'download do canario', 'ok': False,
                                    'erro': f'{type(e).__name__}: {e}'})

    print('\n-- 5. DivulgaCandContas (caminho alternativo, so para saber)')
    r = _tenta('divulgacandcontas', 'https://divulgacandcontas.tse.jus.br/divulga/rest/v1/'
               'eleicao/eleicao-atual', UA_CHROME, CABECALHO_NAVEGADOR)
    relatorio['sondas'].append(r)
    print(f'   {"OK " if r["ok"] else "NAO"} status={r.get("status")} '
          f'{r.get("bytes", 0)} bytes {r.get("erro", "")}')

    # ------------------------------------------------------------- veredito
    baixou = any(s.get('sonda') == 'download do canario' and s.get('ok')
                 for s in relatorio['sondas'])
    algum_ua = [s for s in relatorio['sondas'][:3] if s.get('ok')]
    heads = [s for s in relatorio['sondas'] if str(s.get('sonda', '')).startswith('HEAD')]
    heads_ok = [s for s in heads if s.get('ok')]

    print('\n' + '=' * 72)
    if baixou and len(heads_ok) == len(heads):
        veredito = ('PLANO A: o runner baixa do TSE direto. Seguir com baixar() '
                    'no workflow diario.')
    elif baixou or heads_ok:
        veredito = ('PLANO A PARCIAL: parte das fontes responde. Ver quais '
                    'falharam acima e tratar caso a caso antes do M1.')
    elif algum_ua:
        veredito = ('PLANO A COM RESSALVA: o HEAD passou em algum UA mas o '
                    'download nao. Provavel limite de taxa ou tamanho.')
    else:
        veredito = ('PLANO B: 403 em tudo, como na maquina local. Espelhar os '
                    'zips pelo navegador e servir por Release '
                    '(ferramentas/espelhar.py).')
    relatorio['veredito'] = veredito
    print(veredito)
    print('=' * 72)

    saida = os.environ.get('GITHUB_STEP_SUMMARY')
    if saida:
        with open(saida, 'a', encoding='utf-8') as f:
            f.write(f'## Spike do TSE\n\n**{veredito}**\n\n```json\n'
                    f'{json.dumps(relatorio, ensure_ascii=False, indent=2)}\n```\n')
    return 0 if (baixou or heads_ok) else 1


# ------------------------------------------------------- caminho de producao

def _do_release(nome, destino_dir):
    """Puxa o zip espelhado do Release `fontes`. Devolve caminho ou None."""
    alvo = os.path.join(destino_dir, f'{nome}.zip')
    try:
        p = subprocess.run(
            ['gh', 'release', 'download', 'fontes', '--pattern', f'{nome}.zip',
             '--dir', destino_dir, '--clobber'],
            capture_output=True, text=True, timeout=1800)
        if p.returncode == 0 and os.path.exists(alvo):
            return alvo
        print(f'   release nao serviu para {nome}: {(p.stderr or "").strip()[:200]}')
    except Exception as e:  # noqa: BLE001
        print(f'   release falhou para {nome}: {type(e).__name__}: {e}')
    return None


def baixar_fontes(destino_dir, fonte_local=None, quais=None):
    """Garante os zips em disco. Devolve {nome: (caminho, last_modified)}.

    fonte_local: pasta com os zips ja baixados (teste e plano C).
    """
    os.makedirs(destino_dir, exist_ok=True)
    quais = quais or list(FONTES)
    out = {}
    for nome in quais:
        if fonte_local:
            for cand in (os.path.join(fonte_local, f'{nome}.zip'),
                         os.path.join(fonte_local, os.path.basename(FONTES[nome]))):
                if os.path.exists(cand):
                    out[nome] = (cand, '')
                    print(f'   {nome}: local, {os.path.getsize(cand) / 1e6:.1f} MB')
                    break
            else:
                raise FileNotFoundError(f'{nome}.zip nao esta em {fonte_local}')
            continue
        destino = os.path.join(destino_dir, f'{nome}.zip')
        try:
            caminho, lm, tam = baixar(FONTES[nome], destino)
            print(f'   {nome}: rede, {tam / 1e6:.1f} MB, last-modified={lm}')
            out[nome] = (caminho, lm)
        except Exception as e:  # noqa: BLE001
            print(f'   {nome}: rede falhou ({type(e).__name__}), tentando o Release')
            caminho = _do_release(nome, destino_dir)
            if not caminho:
                raise RuntimeError(
                    f'{nome}: nao veio nem da rede nem do Release. '
                    f'Motivo da rede: {type(e).__name__}: {e}') from e
            out[nome] = (caminho, '')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spike', action='store_true', help='so diagnostica o acesso')
    p.add_argument('--destino', default='tmp/tse')
    p.add_argument('--fonte-local', default=None)
    a = p.parse_args(argv)
    if a.spike:
        return spike()
    baixar_fontes(a.destino, a.fonte_local)
    return 0


if __name__ == '__main__':
    sys.exit(main())
