# Eleitos antes e agora: plano de implementação

> **Para quem executa:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam caixa de seleção (`- [ ]`) para acompanhamento.

**Objetivo:** uma entrada nova na barra, **Eleitos**, com um Sankey de duas colunas que liga a mesma pessoa entre a eleição anterior (2022; 2018 no Senado) e 2026, por partido, filtrável por cargo, UF, partido e federação.

**Arquitetura:** uma ferramenta que roda uma vez no Actions (`ferramentas/anteriores.py`) lê os eleitos de 2018 e 2022 e grava `anteriores.json` na branch `dados`, com cada pessoa identificada por HMAC (nunca CPF). A rodada diária (`pipeline/eleitos.py`) cruza esse arquivo com o `consulta_cand_2026` que já baixa e grava `eleitos/BRASIL.json`, uma linha por pessoa. O front agrega essas cerca de 3.500 linhas sob os filtros e desenha com o `fluxoDuasColunas` que já existe.

**Stack:** Python 3.12, só biblioteca padrão; `unittest`; HTML/JS sem biblioteca em `site/index.html`; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-06-eleitos-sankey-design.md`. Leia antes de começar; este plano argumenta a partir dela.

**Onde trabalhar:** worktree `D:\repos\contas2026-eleitos`, branch `eleitos-sankey`. Nunca no checkout `D:\repos\contas2026`, que tem trabalho de outra sessão.

## Restrições globais

- Python só com biblioteca padrão. Front sem CDN, sem biblioteca, sem fonte externa.
- **CPF nunca vai para arquivo nenhum**, nem para `anteriores.json`, nem para `eleitos/BRASIL.json`, nem para log. A data de nascimento também não. Os dois só entram em HMAC com a `CONTAS_SAL`.
- Sem `CONTAS_SAL` no ambiente, `ferramentas/anteriores.py` para sem gravar.
- Português do Brasil com acento correto em toda string de interface. **Nunca use travessão.** Nenhuma palavra de `PROIBIDAS` (`pipeline/alarmes/__init__.py`).
- "Eleita em 2022", nunca "deputada atual" ou "no mandato". "Sem candidatura registrada em 2026", nunca "desistiu". "Mudou de partido" só quando o partido novo não é o sucessor do antigo.
- Nenhuma cor por partido.
- Cargos contados: `'1'` Presidência, `'3'` governo, `'5'` Senado, `'6'` Câmara, `'7'` Assembleia, `'8'` Câmara Legislativa. Vice e suplência: `'2'`, `'4'`, `'9'`, `'10'`.
- Senado compara com 2018; os outros cargos com 2022.
- Linha de `eleitos/BRASIL.json`, 13 campos, nesta ordem: `[nome, uf_antes, cargo_antes, partido_antes, ano_antes, destino, uf_agora, cargo_agora, partido_agora, desfecho, sq, genero, mudou]`. Partido é índice de `meta.dic.partido` ou `-1`; cargo é o código em texto ou `''`; `ano_antes` é 2018, 2022 ou 0; `destino` é 0..6; `desfecho` é 0..4; `genero` é `'F'`, `'M'` ou `''`; `mudou` é 0 ou 1.
- Destinos: 1 eleita de novo no mesmo cargo e UF; 2 eleita para outro cargo ou UF; 3 2º turno; 4 concorreu a vice ou suplência; 5 concorreu e não se elegeu; 6 sem candidatura em 2026.
- Nunca grave código com barra invertida por heredoc de shell: escreva arquivo com a ferramenta de edição (`TestHigieneDoFonte` reprova caractere de controle).
- Commit em português, no estilo do repositório (frase que diz o que muda), terminando com:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EtPkSBzjFZktWzZFpobrgo
  ```
- Push, merge no `main` e disparo de workflow só com OK explícito do Guilherme.

## Foco da revisão

1. **Pessoa sem CPF num dos anos.** Deve ser ligada pela chave de nome e nascimento, e contada em `ligados_por_nome`; nunca duplicada nos dois lados. Teste na Tarefa 3 (`test_liga_pelo_nome_e_nascimento_quando_falta_cpf`).
2. **Duas candidaturas da mesma pessoa em 2026.** Uma linha só, pela candidatura de melhor desfecho. Teste na Tarefa 3 (`test_candidatura_dupla_vira_uma_linha`).
3. **Partido de 2022 que não existe em 2026 e não está na tabela de sucessão.** A rodada deve avisar com a sigla, e não chamar de mudança em silêncio. Teste na Tarefa 3 (`test_sigla_sem_par_e_avisada`).
4. **Recorte sem ninguém** (UF `BR` com cargo de deputado, DF com Assembleia). A tela mostra uma frase, e não um desenho vazio ou um erro de JS. Conferência visual na Tarefa 5, passo 9.
5. **`CONTAS_SAL` trocada depois de `anteriores.json` gravado.** A rodada segue sem a aba e avisa, em vez de ligar ninguém a ninguém. Teste na Tarefa 1 (`test_ler_anteriores_recusa_sal_diferente`).

## Mapa de arquivos

| Arquivo | O que muda |
|---|---|
| `pipeline/baixar.py` | `FONTES` ganha `consulta_cand_2018` e `consulta_cand_2022` |
| `pipeline/carregar.py` | `candidaturas(z, uf, ano)` lê qualquer ano; `COLUNAS_CAND_2018` sem as colunas de federação |
| `pipeline/eleitos.py` (novo) | chaves HMAC, eleitos de antes, sucessão, cruzamento, leitura e gravação de `anteriores.json` |
| `ferramentas/anteriores.py` (novo) | baixa 2018 e 2022, grava `anteriores.json`, congela fixture |
| `.github/workflows/anteriores.yml` (novo) | roda a ferramenta à mão e grava na branch `dados` |
| `dados/sucessao-partidos.csv` (novo) | partido antigo, sucessor, data, ato |
| `pipeline/escrever.py` | `escrever_eleitos`; `escrever_meta(..., eleitos=None)` |
| `pipeline/validar.py` | `_checar_eleitos`, `LIMITE_ELEITOS_MB` |
| `pipeline/rodar.py` | chama o cruzamento quando há desfecho |
| `site/index.html` | botão, estado, carregamento, desenho, frase, tabela, lista da faixa |
| `tests/test_eleitos.py` (novo) | testes das Tarefas 1 a 4 |
| `tests/fixtures/tse-rr/consulta_cand_2018.zip`, `consulta_cand_2022.zip` (novos) | fatia real de Roraima |
| `CLAUDE.md` | o que a spec manda registrar |

---

### Tarefa 1: ler os anos antigos e gravar `anteriores.json`

**Arquivos:**
- Modificar: `pipeline/baixar.py:34-39` (`FONTES`)
- Modificar: `pipeline/carregar.py:64-71` (`COLUNAS_CAND`) e `pipeline/carregar.py:313-329` (`candidaturas`)
- Criar: `pipeline/eleitos.py`
- Criar: `ferramentas/anteriores.py`
- Criar: `.github/workflows/anteriores.yml`
- Teste: `tests/test_eleitos.py`

**Interfaces:**
- Produz, em `pipeline/carregar.py`: `COLUNAS_CAND_2018: list[str]`; `candidaturas(z, uf=None, ano=2026) -> Iterator[Cand]`.
- Produz, em `pipeline/eleitos.py`: `CARGOS_CONTADOS`, `CARGOS_VICE`, `SENADO`, `ARQUIVO = 'anteriores.json'`; `normaliza_nome(nome) -> str`; `chave_cpf(cpf) -> str`; `chave_nasc(nome, nascimento_iso) -> str`; `sal_marca() -> str`; `genero(ds_genero) -> 'F'|'M'|''`; `linhas_anteriores(cands, ano) -> list[dict]` (chaves `chave, chave_nasc, ano, cargo, uf, partido, nome_urna, genero`); `gravar_anteriores(estado, linhas) -> str`; `ler_anteriores(estado) -> (list[dict], motivo)`, com motivo `''`, `'falta'` ou `'sal'`.
- Produz, em `ferramentas/anteriores.py`: `main(argv) -> int`.

- [ ] **Passo 1: escrever os testes que falham**

Criar `tests/test_eleitos.py`:

```python
#!/usr/bin/env python3
"""Quem foi eleito antes e quem e eleito agora.

Os testes de cruzamento usam candidaturas montadas aqui, porque a fixture de
2026 e de antes da eleicao e nao tem desfecho. Os de leitura usam a fatia real
de Roraima de 2018 e 2022, congelada em tests/fixtures/tse-rr.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import carregar as C   # noqa: E402
from pipeline import eleitos as EL   # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(AQUI, 'fixtures', 'tse-rr')


class ComSal(unittest.TestCase):
    """Todo teste daqui roda com uma CONTAS_SAL de teste, e devolve a de antes."""

    def setUp(self):
        self.antes = os.environ.get('CONTAS_SAL')
        os.environ['CONTAS_SAL'] = 'chave-de-teste'
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        if self.antes is None:
            os.environ.pop('CONTAS_SAL', None)
        else:
            os.environ['CONTAS_SAL'] = self.antes
        shutil.rmtree(self.tmp, ignore_errors=True)


def cand(**kw):
    base = dict(uf='RR', ue='RR', cargo='6', ds_cargo='DEPUTADO FEDERAL', sq='1',
                nr='1010', nome='MARIA DA SILVA', urna='MARIA', cpf='',
                situacao='APTO', nr_partido='10', partido='PAB', nm_partido='',
                nr_fed='', fed='', comp_fed='', genero='FEMININO', cor_raca='',
                ocupacao='', nascimento='1970-01-01', sit_turno='')
    base.update(kw)
    return C.Cand(**base)


def zip_cand(caminho, ano, uf, linhas):
    """Um consulta_cand de mentira, com o cabecalho de verdade daquele ano."""
    cols = C.COLUNAS_CAND if ano >= 2022 else C.COLUNAS_CAND_2018
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', quoting=csv.QUOTE_ALL, lineterminator='\n')
    w.writerow(cols)
    for l in linhas:
        w.writerow([l.get(c, '#NULO') for c in cols])
    with zipfile.ZipFile(caminho, 'w') as z:
        z.writestr(f'consulta_cand_{ano}_{uf}.csv', buf.getvalue().encode('latin-1'))


def linha_csv(cargo, cpf, nome, urna, partido, sit, nasc='01/01/1970', uf='RR', sq='1'):
    return {'SG_UF': uf, 'SG_UE': uf, 'CD_CARGO': cargo, 'SQ_CANDIDATO': sq,
            'NM_CANDIDATO': nome, 'NM_URNA_CANDIDATO': urna,
            'NR_CPF_CANDIDATO': cpf, 'SG_PARTIDO': partido, 'DS_GENERO': 'FEMININO',
            'DT_NASCIMENTO': nasc, 'DS_SIT_TOT_TURNO': sit}


class TestLeituraDeAnoAntigo(unittest.TestCase):
    def test_2018_nao_tem_coluna_de_federacao(self):
        self.assertNotIn('NM_FEDERACAO', C.COLUNAS_CAND_2018)
        self.assertIn('DS_SIT_TOT_TURNO', C.COLUNAS_CAND_2018)

    def test_le_2018_sem_federacao(self):
        tmp = tempfile.mkdtemp()
        try:
            z = os.path.join(tmp, 'c.zip')
            zip_cand(z, 2018, 'RR', [linha_csv('5', '11144477735', 'ANA', 'ANA',
                                               'PSC', 'ELEITO')])
            cs = list(C.candidaturas(zipfile.ZipFile(z), 'RR', ano=2018))
            self.assertEqual(len(cs), 1)
            self.assertEqual(cs[0].fed, '')
            self.assertEqual(cs[0].nascimento, '1970-01-01')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_2026_continua_igual(self):
        zk = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand.zip'))
        self.assertTrue(next(C.candidaturas(zk, 'RR')).sq)


class TestChaves(ComSal):
    def test_cpf_vira_hmac_e_some(self):
        k = EL.chave_cpf('11144477735')
        self.assertTrue(k.startswith('p'))
        self.assertNotIn('11144477735', k)
        self.assertEqual(EL.chave_cpf(''), '')

    def test_chave_de_nome_ignora_acento_caixa_e_espaco(self):
        a = EL.chave_nasc('José  da Silva', '1970-01-01')
        b = EL.chave_nasc('JOSE DA SILVA', '1970-01-01')
        self.assertEqual(a, b)
        self.assertNotEqual(a, EL.chave_nasc('JOSE DA SILVA', '1970-01-02'))
        self.assertEqual(EL.chave_nasc('JOSE', ''), '')

    def test_a_marca_do_sal_muda_com_o_sal(self):
        m1 = EL.sal_marca()
        os.environ['CONTAS_SAL'] = 'outra-chave'
        self.assertNotEqual(m1, EL.sal_marca())


class TestAnteriores(ComSal):
    def test_guarda_so_eleito_nos_cargos_contados(self):
        cs = [cand(sit_turno='ELEITO', cpf='11144477735'),
              cand(sit_turno='SUPLENTE', cpf='22255588846'),
              cand(sit_turno='ELEITO', cargo='4', cpf='33366699957')]
        ls = EL.linhas_anteriores(cs, 2022)
        self.assertEqual(len(ls), 1)
        self.assertEqual(ls[0]['cargo'], '6')
        self.assertEqual(ls[0]['genero'], 'F')

    def test_2018_so_senado(self):
        cs = [cand(sit_turno='ELEITO', cargo='5', cpf='11144477735'),
              cand(sit_turno='ELEITO', cargo='6', cpf='22255588846')]
        self.assertEqual([l['cargo'] for l in EL.linhas_anteriores(cs, 2018)], ['5'])

    def test_gravar_e_ler(self):
        ls = EL.linhas_anteriores([cand(sit_turno='ELEITO', cpf='11144477735')], 2022)
        EL.gravar_anteriores(self.tmp, ls)
        lidas, motivo = EL.ler_anteriores(self.tmp)
        self.assertEqual((len(lidas), motivo), (1, ''))

    def test_ler_anteriores_sem_arquivo(self):
        self.assertEqual(EL.ler_anteriores(self.tmp), ([], 'falta'))

    def test_ler_anteriores_recusa_sal_diferente(self):
        EL.gravar_anteriores(self.tmp, [])
        os.environ['CONTAS_SAL'] = 'outra-chave'
        self.assertEqual(EL.ler_anteriores(self.tmp), ([], 'sal'))


class TestFerramentaAnteriores(ComSal):
    def _fontes(self):
        fontes = os.path.join(self.tmp, 'fontes')
        os.makedirs(fontes)
        zip_cand(os.path.join(fontes, 'consulta_cand_2022.zip'), 2022, 'RR', [
            linha_csv('6', '11144477735', 'ANA DE SOUZA', 'ANA', 'PSC', 'ELEITO POR QP'),
            linha_csv('6', '22255588846', 'BIA', 'BIA', 'PT', 'NÃO ELEITO', sq='2'),
        ])
        zip_cand(os.path.join(fontes, 'consulta_cand_2018.zip'), 2018, 'RR', [
            linha_csv('5', '33366699957', 'CIDA', 'CIDA', 'PTB', 'ELEITO', sq='3'),
            linha_csv('6', '44477700068', 'DORA', 'DORA', 'PT', 'ELEITO', sq='4'),
        ])
        return fontes

    def test_grava_sem_cpf_nem_nascimento(self):
        from ferramentas import anteriores
        est = os.path.join(self.tmp, 'estado')
        r = anteriores.main(['--estado', est, '--fonte-local', self._fontes(),
                             '--uf', 'RR', '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 0)
        texto = open(os.path.join(est, EL.ARQUIVO), encoding='utf-8').read()
        for cpf in ('11144477735', '33366699957'):
            self.assertNotIn(cpf, texto)
        self.assertNotIn('1970-01-01', texto)
        self.assertNotIn('01/01/1970', texto)
        linhas, motivo = EL.ler_anteriores(est)
        self.assertEqual(motivo, '')
        self.assertEqual(sorted((l['ano'], l['cargo']) for l in linhas),
                         [(2018, '5'), (2022, '6')])

    def test_sem_sal_para_sem_gravar(self):
        from ferramentas import anteriores
        os.environ.pop('CONTAS_SAL')
        est = os.path.join(self.tmp, 'estado')
        r = anteriores.main(['--estado', est, '--fonte-local', self._fontes(),
                             '--uf', 'RR', '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 1)
        self.assertFalse(os.path.exists(os.path.join(est, EL.ARQUIVO)))

    def test_congela_a_fatia_da_uf(self):
        from ferramentas import anteriores
        saida = os.path.join(self.tmp, 'fixture')
        anteriores.main(['--estado', os.path.join(self.tmp, 'e'), '--fonte-local',
                         self._fontes(), '--uf', 'RR', '--congelar', 'RR',
                         '--saida-fixture', saida, '--destino', os.path.join(self.tmp, 'd')])
        for ano in (2018, 2022):
            z = zipfile.ZipFile(os.path.join(saida, f'consulta_cand_{ano}.zip'))
            self.assertEqual(z.namelist(), [f'consulta_cand_{ano}_RR.csv'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [ ] **Passo 2: rodar e ver falhar**

Run: `python -m unittest tests.test_eleitos -v`
Expected: ERROR em todos, com `ImportError: cannot import name 'eleitos' from 'pipeline'`.

- [ ] **Passo 3: `FONTES` e `candidaturas` por ano**

Em `pipeline/baixar.py`, dentro de `FONTES`, depois de `'consulta_cand'`:

```python
    # Os dois anos de antes, para a aba de eleitos. Nao mudam: quem os le e
    # ferramentas/anteriores.py, uma vez, e nunca a rodada diaria.
    'consulta_cand_2018': f'{CDN}/consulta_cand/consulta_cand_2018.zip',
    'consulta_cand_2022': f'{CDN}/consulta_cand/consulta_cand_2022.zip',
```

Em `pipeline/carregar.py`, logo depois de `COLUNAS_CAND`:

```python
# Federacao partidaria existe desde 2022: o arquivo de 2018 nao tem as colunas.
COLUNAS_CAND_2018 = [c for c in COLUNAS_CAND if 'FEDERACAO' not in c]
```

Trocar a função `candidaturas` inteira por:

```python
def candidaturas(z, uf=None, ano=2026):
    esperado = COLUNAS_CAND if ano >= 2022 else COLUNAS_CAND_2018
    nome = 'consulta_cand' if ano == 2026 else f'consulta_cand {ano}'
    for r in _dicts(z, _membro(z, f'consulta_cand_{ano}', uf), esperado, nome):
        yield Cand(
            uf=limpo(r['SG_UF']), ue=limpo(r['SG_UE']), cargo=limpo(r['CD_CARGO']),
            ds_cargo=limpo(r['DS_CARGO']), sq=limpo(r['SQ_CANDIDATO']),
            nr=limpo(r['NR_CANDIDATO']), nome=limpo(r['NM_CANDIDATO']),
            urna=limpo(r['NM_URNA_CANDIDATO']) or limpo(r['NM_CANDIDATO']),
            cpf=documento(r['NR_CPF_CANDIDATO']),
            situacao=limpo(r['DS_SITUACAO_CANDIDATURA']),
            nr_partido=limpo(r['NR_PARTIDO']), partido=limpo(r['SG_PARTIDO']),
            nm_partido=limpo(r['NM_PARTIDO']), nr_fed=limpo(r.get('NR_FEDERACAO')),
            fed=limpo(r.get('NM_FEDERACAO')),
            comp_fed=limpo(r.get('DS_COMPOSICAO_FEDERACAO')),
            genero=limpo(r['DS_GENERO']), cor_raca=limpo(r['DS_COR_RACA']),
            ocupacao=limpo(r['DS_OCUPACAO']), nascimento=data(r['DT_NASCIMENTO']),
            sit_turno=limpo(r['DS_SIT_TOT_TURNO']))
```

- [ ] **Passo 4: criar `pipeline/eleitos.py` com a parte de antes**

```python
#!/usr/bin/env python3
"""Quem foi eleito antes e quem e eleito agora, ligando a mesma pessoa.

**A eleicao de comparacao.** O Senado de 2026 renova as cadeiras eleitas em
2018; os outros cargos comparam com 2022. "Eleito antes" e quem foi eleito em
2022 para um dos cargos contados, mais quem foi eleito senador em 2018.

**A ligacao e pelo CPF, que nunca sai daqui.** O SQ_CANDIDATO muda a cada
eleicao. O CPF vira HMAC com a CONTAS_SAL, como em ident.py. Quando o CPF falta
no arquivo antigo, a ligacao usa o nome completo normalizado e a data de
nascimento, tambem por HMAC. Nem CPF nem data vao para arquivo nenhum.

**anteriores.json mora na branch dados.** E feito uma vez, por
ferramentas/anteriores.py no Actions, e carrega a marca do sal com que foi
feito: se a CONTAS_SAL mudar, a rodada recusa o arquivo em vez de ligar
ninguem a ninguem.
"""
import csv
import hashlib
import hmac
import json
import os
import re
import unicodedata

from . import desfecho as D
from .ident import ident, sal

CARGOS_CONTADOS = ('1', '3', '5', '6', '7', '8')
CARGOS_VICE = ('2', '4', '9', '10')
SENADO = '5'
ARQUIVO = 'anteriores.json'


def normaliza_nome(nome):
    s = unicodedata.normalize('NFKD', nome or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).strip().upper()


def _hmac(texto):
    return 'p' + hmac.new(sal(), texto.encode('utf-8'),
                          hashlib.sha256).hexdigest()[:16]


def chave_cpf(cpf):
    return ident(cpf) if cpf and len(cpf) == 11 else ''


def chave_nasc(nome, nascimento):
    n = normaliza_nome(nome)
    if not n or not nascimento:
        return ''
    return _hmac(n + '|' + nascimento)


def sal_marca():
    """Oito hex que mudam quando a CONTAS_SAL muda, e nao a revelam."""
    return _hmac('anteriores')[1:9]


def genero(ds):
    s = normaliza_nome(ds)
    if s.startswith('FEM'):
        return 'F'
    return 'M' if s.startswith('MASC') else ''


def linhas_anteriores(cands, ano):
    """Os eleitos de um ano anterior nos cargos contados. Em 2018, so o Senado."""
    out = []
    for c in cands:
        if D.codigo(c.sit_turno) != D.ELEITA or c.cargo not in CARGOS_CONTADOS:
            continue
        if ano == 2018 and c.cargo != SENADO:
            continue
        out.append({'chave': chave_cpf(c.cpf),
                    'chave_nasc': chave_nasc(c.nome, c.nascimento),
                    'ano': ano, 'cargo': c.cargo, 'uf': c.uf,
                    'partido': c.partido, 'nome_urna': c.urna,
                    'genero': genero(c.genero)})
    return out


def gravar_anteriores(estado, linhas):
    os.makedirs(estado, exist_ok=True)
    caminho = os.path.join(estado, ARQUIVO)
    with open(caminho + '.tmp', 'w', encoding='utf-8') as f:
        json.dump({'sal_marca': sal_marca(), 'linhas': linhas}, f,
                  ensure_ascii=False, separators=(',', ':'))
    os.replace(caminho + '.tmp', caminho)
    return caminho


def ler_anteriores(estado):
    """(linhas, motivo). Motivo '' quando serve, 'falta' ou 'sal' quando nao."""
    caminho = os.path.join(estado, ARQUIVO)
    if not os.path.exists(caminho):
        return [], 'falta'
    with open(caminho, encoding='utf-8') as f:
        d = json.load(f)
    if d.get('sal_marca') != sal_marca():
        return [], 'sal'
    return d.get('linhas', []), ''
```

- [ ] **Passo 5: criar `ferramentas/anteriores.py`**

```python
#!/usr/bin/env python3
"""Os eleitos de 2018 (Senado) e de 2022 (todos os cargos contados).

Roda a mao no GitHub Actions, pelo workflow anteriores.yml, porque da maquina
local o CDN do TSE devolve 403. Os dois anos nao mudam: o arquivo e feito uma
vez e so precisa ser refeito se a CONTAS_SAL mudar.

    python -m ferramentas.anteriores --estado estado
    python -m ferramentas.anteriores --estado estado --congelar RR --saida-fixture fixture
"""
import argparse
import os
import re
import sys
import zipfile
from collections import Counter

from pipeline import carregar as C
from pipeline import eleitos as EL
from pipeline.baixar import baixar_fontes
from pipeline.ident import tem_sal_de_verdade

ANOS = (2018, 2022)


def ufs_do_zip(z, ano):
    """O arquivo BRASIL quando existe; senao, cada arquivo de UF."""
    try:
        C.membro_brasil(z, f'consulta_cand_{ano}')
        return [None]
    except C.LayoutMudou:
        padrao = re.compile(rf'consulta_cand_{ano}_([A-Z]{{2}})\.csv$')
        return sorted({m.group(1) for m in map(padrao.search, z.namelist()) if m})


def congelar(z, ano, uf, saida):
    os.makedirs(saida, exist_ok=True)
    membro = C.membro_uf(z, f'consulta_cand_{ano}', uf)
    alvo = os.path.join(saida, f'consulta_cand_{ano}.zip')
    with zipfile.ZipFile(alvo, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr(os.path.basename(membro), z.read(membro))
    print(f'   fixture: {alvo}, {os.path.getsize(alvo) / 1e6:.2f} MB')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--estado', default='estado')
    p.add_argument('--destino', default=os.environ.get('RUNNER_TEMP', 'tmp') + '/tse')
    p.add_argument('--fonte-local', default=None)
    p.add_argument('--uf', default='', help='so esta UF (teste)')
    p.add_argument('--congelar', default='', help='UF que vira fixture')
    p.add_argument('--saida-fixture', default='fixture')
    a = p.parse_args(argv)

    if not tem_sal_de_verdade():
        print('CONTAS_SAL nao esta no ambiente. Sem ela a chave de cada pessoa')
        print('seria reversivel, e o arquivo vai para uma branch publica.')
        print('Nada foi gravado.')
        return 1

    fontes = baixar_fontes(a.destino, a.fonte_local,
                           quais=[f'consulta_cand_{ano}' for ano in ANOS])
    linhas, vistas = [], set()
    for ano in ANOS:
        z = zipfile.ZipFile(fontes[f'consulta_cand_{ano}'][0])
        if a.congelar:
            congelar(z, ano, a.congelar, a.saida_fixture)
        ufs = [a.uf] if a.uf else ufs_do_zip(z, ano)
        doano, sem_cpf = [], 0
        for uf in ufs:
            for l in EL.linhas_anteriores(C.candidaturas(z, uf, ano=ano), ano):
                # a Presidencia pode aparecer em mais de um arquivo de UF
                k = (l['chave'] or l['chave_nasc'] or l['nome_urna'], ano,
                     l['cargo'], l['uf'])
                if k in vistas:
                    continue
                vistas.add(k)
                doano.append(l)
                sem_cpf += not l['chave']
        por_cargo = Counter(l['cargo'] for l in doano)
        print(f'{ano}: {len(doano)} eleitos, {sem_cpf} sem CPF no arquivo do TSE')
        for cargo, n in sorted(por_cargo.items()):
            print(f'   cargo {cargo}: {n}')
        linhas.extend(doano)
    caminho = EL.gravar_anteriores(a.estado, linhas)
    print(f'{len(linhas)} eleitos gravados em {caminho}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Passo 6: rodar os testes**

Run: `python -m unittest tests.test_eleitos -v`
Expected: tudo PASS.

Run: `python -m unittest discover -s tests`
Expected: OK, sem falha nova.

- [ ] **Passo 7: criar `.github/workflows/anteriores.yml`**

```yaml
name: eleitos de antes

# Le os eleitos de 2018 (Senado) e de 2022 (todos os cargos contados) e grava
# anteriores.json na branch dados. Roda a mao: os dois anos nao mudam, e o
# arquivo so precisa ser refeito se a CONTAS_SAL mudar.

on:
  workflow_dispatch:
    inputs:
      congelar:
        description: UF cujos arquivos de 2018 e 2022 viram fixture (vazio = nenhuma)
        default: ''
      gravar:
        description: gravar anteriores.json na branch dados
        type: boolean
        default: false

# o mesmo grupo da rodada diaria: as duas escrevem na branch dados
concurrency:
  group: rodada
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  anteriores:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4

      - name: buscar o estado
        uses: actions/checkout@v4
        continue-on-error: true
        with:
          ref: dados
          path: estado-repo

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: ler 2018 e 2022
        env:
          CONTAS_SAL: ${{ secrets.CONTAS_SAL }}
        run: |
          mkdir -p estado
          python -m ferramentas.anteriores --estado estado --destino "$RUNNER_TEMP/tse" \
            ${{ inputs.congelar != '' && format('--congelar {0} --saida-fixture fixture', inputs.congelar) || '' }}

      - uses: actions/upload-artifact@v4
        if: inputs.congelar != ''
        with:
          name: fixture-anteriores
          path: fixture

      - name: gravar na branch dados
        if: inputs.gravar
        run: |
          cd estado-repo
          mkdir -p estado
          cp ../estado/anteriores.json estado/
          git config user.name "rodada automatica"
          git config user.email "noreply@github.com"
          git add estado/anteriores.json
          git diff --quiet --cached || git commit -m "eleitos de antes, $(date -I)"
          git pull --rebase --autostash origin dados || true
          git push origin HEAD:dados
```

- [ ] **Passo 8: commit**

```bash
git add pipeline/baixar.py pipeline/carregar.py pipeline/eleitos.py ferramentas/anteriores.py .github/workflows/anteriores.yml tests/test_eleitos.py
git commit -m "Os eleitos de 2018 e 2022 passam a ser lidos, sem CPF, por uma ferramenta que roda uma vez"
```

---

### Tarefa 2: conferir no Actions e congelar a fixture real

Esta tarefa depende do Guilherme: cada push e cada disparo pede o OK dele. Não há código novo além de um teste e da tabela de sucessão.

**Arquivos:**
- Criar: `tests/fixtures/tse-rr/consulta_cand_2018.zip`, `tests/fixtures/tse-rr/consulta_cand_2022.zip`
- Criar: `dados/sucessao-partidos.csv`
- Teste: `tests/test_eleitos.py` (classe nova `TestAnterioresReais`)

**Interfaces:**
- Consome: `ferramentas.anteriores.main`, `pipeline.eleitos.ler_anteriores` (Tarefa 1).
- Produz: a fixture real; `dados/sucessao-partidos.csv` com o cabeçalho `antigo,sucessor,data,ato`.

- [ ] **Passo 1: pedir OK e publicar a ferramenta**

Pedir ao Guilherme, numa mensagem só: (a) push da branch `eleitos-sankey`; (b) levar o commit da Tarefa 1 para o `main`. O motivo do (b): `workflow_dispatch` só dispara um workflow que exista no branch padrão. O commit só acrescenta arquivos e um parâmetro com valor padrão em `candidaturas`; a rodada diária não muda. Com o OK:

```bash
git push -u origin eleitos-sankey
cd /d/repos/contas2026 && git fetch origin && git log --oneline -1 origin/main
```

Para levar ao `main` sem tocar no checkout principal (que tem trabalho de outra sessão), usar uma worktree temporária:

```bash
git -C /d/repos/contas2026 worktree add /d/repos/contas2026-main-tmp origin/main
cd /d/repos/contas2026-main-tmp && git switch -c leva-anteriores
git cherry-pick <sha do commit da Tarefa 1>
python -m unittest discover -s tests
git push origin leva-anteriores:main
cd /d/repos/contas2026-eleitos && git -C /d/repos/contas2026 worktree remove /d/repos/contas2026-main-tmp
```

- [ ] **Passo 2: inspecionar o layout de 2018 e 2022**

```bash
gh workflow run inspecionar.yml --ref eleitos-sankey -f quais=consulta_cand_2018,consulta_cand_2022 -f contar=DS_SIT_TOT_TURNO
gh run watch
gh run view --log | grep -E "consulta_cand_20(18|22)|DS_SIT_TOT_TURNO|NR_CPF|BRASIL" | head -80
```

Anotar: (a) se existe `consulta_cand_<ano>_BRASIL.csv`; (b) as grafias de `DS_SIT_TOT_TURNO` (todas devem cair na tabela de `pipeline/desfecho.py`; grafia nova entra lá, com teste em `TestDesfecho`); (c) se `NR_CPF_CANDIDATO` vem preenchido na amostra; (d) se alguma coluna de `COLUNAS_CAND_2018` falta em 2018 (o `carregar` falha alto listando).

**Se o CPF vier vazio ou mascarado em massa, pare e volte ao Guilherme**: a spec diz que nesse caso ela volta para conversa.

- [ ] **Passo 3: rodar a ferramenta sem gravar, congelando Roraima**

```bash
gh workflow run anteriores.yml --ref eleitos-sankey -f congelar=RR -f gravar=false
gh run watch
gh run view --log | grep -E "^.*(2018|2022): |cargo |sem CPF|gravados" | head -40
gh run download --name fixture-anteriores --dir /tmp/fixture-anteriores
```

Conferir no log: 2022 com cargo 6 = 513, cargo 3 = 27, cargo 5 = 27, cargo 1 = 1, cargo 7 + cargo 8 = 1059; 2018 com cargo 5 = 54. Anotar quantos vieram sem CPF.

- [ ] **Passo 4: copiar a fixture e escrever o teste real**

```bash
cp /tmp/fixture-anteriores/consulta_cand_2018.zip /tmp/fixture-anteriores/consulta_cand_2022.zip tests/fixtures/tse-rr/
```

Acrescentar a `tests/test_eleitos.py`, antes do `if __name__`:

```python
class TestAnterioresReais(ComSal):
    """A fatia real de Roraima. As contagens sao fato: RR tem 8 cadeiras na
    Camara, 24 na Assembleia, 3 no Senado (1 eleita em 2022, 2 em 2018)."""

    def test_contagem_de_roraima(self):
        from ferramentas import anteriores
        est = os.path.join(self.tmp, 'estado')
        r = anteriores.main(['--estado', est, '--fonte-local', FIX, '--uf', 'RR',
                             '--destino', os.path.join(self.tmp, 'd')])
        self.assertEqual(r, 0)
        linhas, _ = EL.ler_anteriores(est)
        por = {}
        for l in linhas:
            por[(l['ano'], l['cargo'])] = por.get((l['ano'], l['cargo']), 0) + 1
        self.assertEqual(por, {(2022, '6'): 8, (2022, '7'): 24, (2022, '3'): 1,
                               (2022, '5'): 1, (2018, '5'): 2})
```

Run: `python -m unittest tests.test_eleitos.TestAnterioresReais -v`
Expected: PASS. Se falhar, o número é fato sobre o TSE: leia o que veio antes de mexer no teste.

- [ ] **Passo 5: a tabela de sucessão**

Criar `dados/sucessao-partidos.csv`. As siglas são como o TSE grava em `SG_PARTIDO`. **Antes do commit**, confira cada sigla de sucessor contra o `consulta_cand_2026` (`gh workflow run inspecionar.yml -f quais=consulta_cand -f contar=SG_PARTIDO`) e as siglas antigas contra o log de 2022 (`-f quais=consulta_cand_2022 -f contar=SG_PARTIDO`). Confira também cada data e cada ato na página de partidos do TSE (tse.jus.br, "Partidos políticos registrados no TSE", histórico de fusões e incorporações). Linha cujo ato você não achou não entra:

```csv
antigo,sucessor,data,ato
PROS,SOLIDARIEDADE,2023-02-14,conferir: TSE aprovou a incorporação do PROS ao Solidariedade
PSC,PODE,2023-06-13,conferir: TSE aprovou a incorporação do PSC ao Podemos
PTB,PRD,2023-11-07,conferir: TSE aprovou a fusão de PTB e Patriota no PRD
PATRIOTA,PRD,2023-11-07,conferir: TSE aprovou a fusão de PTB e Patriota no PRD
```

Troque cada `conferir: …` pelo número e data da resolução ou do acórdão que achou. Toda sigla de 2022 que não aparece em 2026 precisa estar aqui ou ter explicação anotada no commit.

- [ ] **Passo 6: rodar a suíte e commitar**

Run: `python -m unittest discover -s tests`
Expected: OK.

```bash
git add tests/fixtures/tse-rr/consulta_cand_2018.zip tests/fixtures/tse-rr/consulta_cand_2022.zip tests/test_eleitos.py dados/sucessao-partidos.csv
git commit -m "A fatia real de Roraima de 2018 e 2022 congelada, e a tabela de partidos sucessores"
```

---

### Tarefa 3: cruzar antes e agora

**Arquivos:**
- Modificar: `pipeline/eleitos.py` (acrescentar no fim)
- Teste: `tests/test_eleitos.py` (classes novas `TestSucessao`, `TestCruzamento`)

**Interfaces:**
- Consome: tudo de `pipeline/eleitos.py` da Tarefa 1.
- Produz: constantes `MESMO_CARGO=1, OUTRO_CARGO=2, SEGUNDO_TURNO=3, VICE=4, NAO_ELEITA=5, SEM_CANDIDATURA=6`; `carregar_sucessao(caminho) -> dict[str, str]`; `sucessor(sigla, tabela) -> str`; `cruzar(anteriores, cands, sucessao, ufs=None) -> (list[dict], dict)`. Cada pessoa é um dict com `nome, uf_antes, cargo_antes, partido_antes, ano_antes, destino, uf_agora, cargo_agora, partido_agora, desfecho, sq, genero, mudou`. As estatísticas: `{'anteriores': {'2022': {cargo: n}, '2018': {cargo: n}}, 'ligados_por_nome': n, 'siglas_sem_par': [..], 'fed': {sigla: nome_fed}}`.

- [ ] **Passo 1: escrever os testes que falham**

Acrescentar a `tests/test_eleitos.py`, antes do `if __name__`:

```python
def antes(cpf='11144477735', ano=2022, cargo='6', uf='RR', partido='PAB',
          nome='MARIA DA SILVA', nasc='1970-01-01'):
    return {'chave': EL.chave_cpf(cpf), 'chave_nasc': EL.chave_nasc(nome, nasc),
            'ano': ano, 'cargo': cargo, 'uf': uf, 'partido': partido,
            'nome_urna': nome.split()[0], 'genero': 'F'}


class TestSucessao(unittest.TestCase):
    def test_transitiva_e_sem_laco(self):
        t = {'A': 'B', 'B': 'C', 'X': 'Y', 'Y': 'X'}
        self.assertEqual(EL.sucessor('A', t), 'C')
        self.assertEqual(EL.sucessor('Z', t), 'Z')
        self.assertIn(EL.sucessor('X', t), ('X', 'Y'))

    def test_le_o_csv(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, 's.csv')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('antigo,sucessor,data,ato\nPSC,PODE,2023-06-13,ato\n')
            self.assertEqual(EL.carregar_sucessao(p), {'PSC': 'PODE'})
            self.assertEqual(EL.carregar_sucessao(os.path.join(tmp, 'nao')), {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCruzamento(ComSal):
    def um(self, anteriores, cands, suc=None):
        pessoas, est = EL.cruzar(anteriores, cands, suc or {})
        return pessoas, est

    def test_reeleita_no_mesmo_cargo(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', sit_turno='ELEITO', sq='9')])
        self.assertEqual(len(ps), 1)
        p = ps[0]
        self.assertEqual((p['destino'], p['ano_antes'], p['sq'], p['mudou']),
                         (EL.MESMO_CARGO, 2022, '9', 0))

    def test_mesmo_cargo_em_outra_uf_e_outro_destino(self):
        ps, _ = self.um([antes(uf='AM')], [cand(cpf='11144477735', sit_turno='ELEITO')])
        self.assertEqual(ps[0]['destino'], EL.OUTRO_CARGO)

    def test_eleita_para_outro_cargo(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='5', sit_turno='ELEITO')])
        self.assertEqual((ps[0]['destino'], ps[0]['cargo_agora']), (EL.OUTRO_CARGO, '5'))

    def test_segundo_turno(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='3', sit_turno='2º TURNO')])
        self.assertEqual(ps[0]['destino'], EL.SEGUNDO_TURNO)

    def test_vice(self):
        ps, _ = self.um([antes()], [cand(cpf='11144477735', cargo='4', sit_turno='ELEITO')])
        self.assertEqual(ps[0]['destino'], EL.VICE)

    def test_concorreu_e_nao_se_elegeu_inclui_suplente_e_sem_desfecho(self):
        for sit in ('SUPLENTE', 'NÃO ELEITO', '#NULO'):
            ps, _ = self.um([antes()], [cand(cpf='11144477735', sit_turno=sit)])
            self.assertEqual(ps[0]['destino'], EL.NAO_ELEITA, sit)

    def test_sem_candidatura(self):
        ps, _ = self.um([antes()], [])
        p = ps[0]
        self.assertEqual((p['destino'], p['sq'], p['cargo_agora']), (EL.SEM_CANDIDATURA, '', ''))

    def test_novata_eleita_entra_e_nao_eleita_nao(self):
        ps, _ = self.um([], [cand(cpf='22255588846', sit_turno='ELEITO', sq='1'),
                             cand(cpf='33366699957', sit_turno='NÃO ELEITO', sq='2')])
        self.assertEqual([(p['sq'], p['destino'], p['ano_antes']) for p in ps], [('1', 0, 0)])

    def test_mudanca_por_sucessao_nao_conta(self):
        ps, _ = self.um([antes(partido='PSC')],
                        [cand(cpf='11144477735', partido='PODE', sit_turno='ELEITO')],
                        {'PSC': 'PODE'})
        self.assertEqual(ps[0]['mudou'], 0)

    def test_mudanca_sem_sucessao_conta(self):
        ps, _ = self.um([antes(partido='PSC')],
                        [cand(cpf='11144477735', partido='PT', sit_turno='ELEITO')],
                        {'PSC': 'PODE'})
        self.assertEqual(ps[0]['mudou'], 1)

    def test_liga_pelo_nome_e_nascimento_quando_falta_cpf(self):
        ps, est = self.um([antes(cpf='', nome='José da Silva')],
                          [cand(cpf='11144477735', nome='JOSE DA SILVA', sit_turno='ELEITO')])
        self.assertEqual(len(ps), 1)
        self.assertEqual(ps[0]['destino'], EL.MESMO_CARGO)
        self.assertEqual(est['ligados_por_nome'], 1)

    def test_candidatura_dupla_vira_uma_linha(self):
        ps, _ = self.um([antes()], [
            cand(cpf='11144477735', sit_turno='NÃO ELEITO', sq='1'),
            cand(cpf='11144477735', cargo='5', sit_turno='ELEITO', sq='2')])
        self.assertEqual([(p['sq'], p['destino']) for p in ps], [('2', EL.OUTRO_CARGO)])

    def test_2022_vence_2018_para_a_mesma_pessoa(self):
        ps, est = self.um([antes(ano=2018, cargo='5'), antes(ano=2022, cargo='3')], [])
        self.assertEqual([(p['ano_antes'], p['cargo_antes']) for p in ps], [(2022, '3')])
        # a contagem bruta continua com as duas eleicoes
        self.assertEqual(est['anteriores'], {'2018': {'5': 1}, '2022': {'3': 1}})

    def test_sigla_sem_par_e_avisada(self):
        _, est = self.um([antes(partido='PSC'), antes(cpf='22255588846', partido='PTB')],
                         [cand(cpf='33366699957', partido='PODE', sit_turno='ELEITO')],
                         {'PSC': 'PODE'})
        self.assertEqual(est['siglas_sem_par'], ['PTB'])

    def test_filtro_de_uf(self):
        ps, _ = EL.cruzar([antes(uf='AM'), antes(cpf='22255588846')], [], {}, ufs=['RR'])
        self.assertEqual([p['uf_antes'] for p in ps], ['RR'])

    def test_federacao_de_2026(self):
        _, est = self.um([], [cand(cpf='22255588846', partido='PT', fed='FEDERAÇÃO BRASIL DA ESPERANÇA', sit_turno='ELEITO')])
        self.assertEqual(est['fed'], {'PT': 'FEDERAÇÃO BRASIL DA ESPERANÇA'})
```

- [ ] **Passo 2: rodar e ver falhar**

Run: `python -m unittest tests.test_eleitos.TestSucessao tests.test_eleitos.TestCruzamento -v`
Expected: ERROR com `AttributeError: module 'pipeline.eleitos' has no attribute 'sucessor'` (e `cruzar`).

- [ ] **Passo 3: implementar no fim de `pipeline/eleitos.py`**

```python
MESMO_CARGO, OUTRO_CARGO, SEGUNDO_TURNO, VICE, NAO_ELEITA, SEM_CANDIDATURA = range(1, 7)


def carregar_sucessao(caminho):
    """Partido antigo -> sucessor, de dados/sucessao-partidos.csv. Sem o
    arquivo, ninguem tem sucessor, e a rodada avisa as siglas sem par."""
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding='utf-8', newline='') as f:
        return {r['antigo'].strip(): r['sucessor'].strip()
                for r in csv.DictReader(f) if (r.get('antigo') or '').strip()}


def sucessor(sigla, tabela):
    """Transitivo: se A virou B e B virou C, A vira C."""
    vistos = set()
    while sigla in tabela and sigla not in vistos:
        vistos.add(sigla)
        sigla = tabela[sigla]
    return sigla


def _prioridade(c):
    """Qual das candidaturas de 2026 de uma pessoa decide o destino dela."""
    d = D.codigo(c.sit_turno)
    if c.cargo in CARGOS_CONTADOS and d == D.ELEITA:
        return 0
    if c.cargo in CARGOS_CONTADOS and d == D.SEGUNDO_TURNO:
        return 1
    if c.cargo in CARGOS_VICE:
        return 2
    return 3


def _destino(a, c):
    if c is None:
        return SEM_CANDIDATURA
    d = D.codigo(c.sit_turno)
    if c.cargo in CARGOS_CONTADOS and d == D.ELEITA:
        mesmo = c.cargo == a['cargo'] and c.uf == a['uf']
        return MESMO_CARGO if mesmo else OUTRO_CARGO
    if c.cargo in CARGOS_CONTADOS and d == D.SEGUNDO_TURNO:
        return SEGUNDO_TURNO
    if c.cargo in CARGOS_VICE:
        return VICE
    return NAO_ELEITA


def _pessoa(a, c, suc):
    return {
        'nome': (c.urna if c else '') or (a or {}).get('nome_urna', ''),
        'uf_antes': a['uf'] if a else '',
        'cargo_antes': a['cargo'] if a else '',
        'partido_antes': a['partido'] if a else '',
        'ano_antes': a['ano'] if a else 0,
        'destino': _destino(a, c) if a else 0,
        'uf_agora': c.uf if c else '',
        'cargo_agora': c.cargo if c else '',
        'partido_agora': c.partido if c else '',
        'desfecho': D.codigo(c.sit_turno) if c else 0,
        'sq': c.sq if c else '',
        'genero': genero(c.genero) if c else (a or {}).get('genero', ''),
        'mudou': int(bool(a and c and c.partido
                          and sucessor(a['partido'], suc) != c.partido)),
    }


def cruzar(anteriores, cands, suc, ufs=None):
    """Uma linha por pessoa: todo eleito de antes, e toda candidatura de 2026
    eleita ou no 2o turno nos cargos contados. Devolve (pessoas, estatisticas)."""
    ufs = set(ufs or ())
    brutas = {}
    antes = {}
    for a in anteriores:
        if ufs and a['uf'] not in ufs:
            continue
        doano = brutas.setdefault(str(a['ano']), {})
        doano[a['cargo']] = doano.get(a['cargo'], 0) + 1
        k = a['chave'] or a['chave_nasc'] or 'sem:' + a['nome_urna'] + a['uf']
        # quem foi eleito em 2018 e de novo em 2022 e lido pelo registro de 2022
        if k not in antes or a['ano'] > antes[k]['ano']:
            antes[k] = a

    agora, fed = {}, {}
    for c in cands:
        if ufs and c.uf not in ufs:
            continue
        if c.cargo not in CARGOS_CONTADOS and c.cargo not in CARGOS_VICE:
            continue
        if c.partido and c.fed:
            fed[c.partido] = c.fed
        k = chave_cpf(c.cpf) or chave_nasc(c.nome, c.nascimento) or 'sq:' + c.sq
        if k not in agora or _prioridade(c) < _prioridade(agora[k]):
            agora[k] = c
    por_nasc = {}
    for k, c in agora.items():
        kn = chave_nasc(c.nome, c.nascimento)
        if kn:
            por_nasc.setdefault(kn, k)

    pessoas, usados, por_nome = [], set(), 0
    for a in antes.values():
        ka = None
        if a['chave'] and a['chave'] in agora:
            ka = a['chave']
        elif not a['chave'] and a['chave_nasc'] in por_nasc:
            ka = por_nasc[a['chave_nasc']]
            por_nome += 1
        if ka:
            usados.add(ka)
        pessoas.append(_pessoa(a, agora.get(ka) if ka else None, suc))
    for k, c in agora.items():
        if k in usados or c.cargo not in CARGOS_CONTADOS:
            continue
        if D.codigo(c.sit_turno) in (D.ELEITA, D.SEGUNDO_TURNO):
            pessoas.append(_pessoa(None, c, suc))

    siglas_agora = {c.partido for c in cands if c.partido}
    sem_par = sorted({a['partido'] for a in antes.values()
                      if a['partido'] and a['partido'] not in siglas_agora
                      and a['partido'] not in suc})
    return pessoas, {'anteriores': brutas, 'ligados_por_nome': por_nome,
                     'siglas_sem_par': sem_par, 'fed': fed}
```

- [ ] **Passo 4: rodar os testes**

Run: `python -m unittest tests.test_eleitos -v`
Expected: tudo PASS.

- [ ] **Passo 5: commit**

```bash
git add pipeline/eleitos.py tests/test_eleitos.py
git commit -m "O cruzamento liga cada eleito de antes ao que aconteceu com ele em 2026"
```

---

### Tarefa 4: escrever, validar e ligar na rodada

**Arquivos:**
- Modificar: `pipeline/escrever.py` (função nova depois de `grava`; `escrever_meta` em `pipeline/escrever.py:824`)
- Modificar: `pipeline/validar.py` (constante perto da linha 32; função nova antes de `def validar`; chamada antes da "amostra de fichas", perto da linha 776)
- Modificar: `pipeline/rodar.py` (bloco novo logo antes de `E.escrever_meta(`, perto da linha 304)
- Teste: `tests/test_eleitos.py` (classes novas `TestEscritaEValidacao`, `TestRodadaComDesfecho`)

**Interfaces:**
- Consome: `EL.cruzar`, `EL.ler_anteriores`, `EL.carregar_sucessao` (Tarefas 1 e 3); `E.Dic`, `E.grava`.
- Produz: `E.escrever_eleitos(pessoas, est, dics, destino) -> int` (bytes); `escrever_meta(..., eleitos=None)` grava `meta['eleitos']` (`None` ou `{'n': int, 'ligados_por_nome': int}`); `V._checar_eleitos(d, n_part, n_fed, completo, mb=0.0) -> list[str]`; `V.LIMITE_ELEITOS_MB = 1.0`; `V.CADEIRAS`.

- [ ] **Passo 1: escrever os testes que falham**

Acrescentar a `tests/test_eleitos.py`, antes do `if __name__`:

```python
from pipeline import escrever as E   # noqa: E402
from pipeline import validar as V    # noqa: E402


def linha_ok(**kw):
    base = dict(nome='MARIA', uf_a='RR', cargo_a='6', part_a=0, ano_a=2022, destino=1,
                uf_g='RR', cargo_g='6', part_g=0, desf=1, sq='9', gen='F', mudou=0)
    base.update(kw)
    return [base[k] for k in ('nome', 'uf_a', 'cargo_a', 'part_a', 'ano_a', 'destino',
                              'uf_g', 'cargo_g', 'part_g', 'desf', 'sq', 'gen', 'mudou')]


class TestEscritaEValidacao(ComSal):
    def test_escreve_linhas_de_13_campos_com_indice_de_partido(self):
        ps, est = EL.cruzar([antes(partido='PSC')],
                            [cand(cpf='11144477735', partido='PODE', sit_turno='ELEITO', sq='9'),
                             cand(cpf='22255588846', partido='PT', fed='FED X', sit_turno='ELEITO', sq='8')],
                            {'PSC': 'PODE'})
        dics = {k: E.Dic() for k in ('partido', 'fed')}
        E.escrever_eleitos(ps, est, dics, self.tmp)
        d = json.load(open(os.path.join(self.tmp, 'eleitos', 'BRASIL.json'), encoding='utf-8'))
        self.assertTrue(all(len(l) == 13 for l in d['c']))
        por_sq = {l[10]: l for l in d['c']}
        self.assertEqual(dics['partido'].lista[por_sq['9'][3]], 'PSC')
        self.assertEqual(dics['partido'].lista[por_sq['9'][8]], 'PODE')
        self.assertEqual(por_sq['8'][3], -1)
        self.assertEqual(d['fed'], {str(dics['partido'].idx['PT']): dics['fed'].idx['FED X']})
        self.assertEqual(V._checar_eleitos(d, len(dics['partido'].lista),
                                           len(dics['fed'].lista), False), [])

    def test_validador_reprova_forma(self):
        for ruim, trecho in ((linha_ok()[:12], '13'),
                             (linha_ok(destino=7), 'destino'),
                             (linha_ok(ano_a=0), 'destino'),
                             (linha_ok(part_g=5), 'partido'),
                             (linha_ok(desf=5), 'desfecho'),
                             (linha_ok(cargo_a='9'), 'cargo')):
            erros = V._checar_eleitos({'c': [ruim]}, 1, 0, False)
            self.assertTrue(erros and trecho in erros[0], (ruim, erros))

    def test_validador_reprova_sq_repetido(self):
        erros = V._checar_eleitos({'c': [linha_ok(), linha_ok()]}, 1, 0, False)
        self.assertTrue(any('repetido' in e for e in erros))

    def test_cadeiras_so_no_pais_inteiro(self):
        cheio = {'2022': {'1': 1, '3': 27, '5': 27, '6': 513, '7': 1035, '8': 24},
                 '2018': {'5': 54}}
        self.assertEqual(V._checar_eleitos({'c': [], 'anteriores': cheio}, 1, 0, True), [])
        pouco = dict(cheio, **{'2022': dict(cheio['2022'], **{'6': 400})})
        self.assertTrue(V._checar_eleitos({'c': [], 'anteriores': pouco}, 1, 0, True))
        self.assertEqual(V._checar_eleitos({'c': [], 'anteriores': pouco}, 1, 0, False), [])
        demais = dict(cheio, **{'2018': {'5': 55}})
        self.assertTrue(V._checar_eleitos({'c': [], 'anteriores': demais}, 1, 0, True))


class TestRodadaComDesfecho(ComSal):
    """A rodada da fixture com um desfecho escrito a mao no consulta_cand de 2026:
    reelege quem foi eleito deputado federal em 2022 e concorre de novo."""

    def _fonte_com_desfecho(self):
        fonte = os.path.join(self.tmp, 'fonte')
        shutil.copytree(FIX, fonte)
        # os CPF dos deputados federais eleitos em RR em 2022
        z22 = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand_2022.zip'))
        eleitos22 = {c.cpf for c in C.candidaturas(z22, 'RR', ano=2022)
                     if c.cargo == '6' and EL.D.codigo(c.sit_turno) == 1 and c.cpf}
        caminho = os.path.join(fonte, 'consulta_cand.zip')
        z = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand.zip'))
        membro = C.membro_uf(z, 'consulta_cand_2026', 'RR')
        texto = z.read(membro).decode('latin-1')
        leitor = list(csv.reader(io.StringIO(texto), delimiter=';'))
        cab = [c.lstrip('\ufeff').strip('"').strip() for c in leitor[0]]
        i_cpf, i_sit, i_cargo = (cab.index(k) for k in
                                 ('NR_CPF_CANDIDATO', 'DS_SIT_TOT_TURNO', 'CD_CARGO'))
        reeleitos = 0
        for l in leitor[1:]:
            if len(l) == len(cab) and l[i_cargo] == '6'                     and C.documento(l[i_cpf]) in eleitos22:
                l[i_sit] = 'ELEITO'
                reeleitos += 1
        buf = io.StringIO()
        csv.writer(buf, delimiter=';', quoting=csv.QUOTE_ALL,
                   lineterminator='\n').writerows(leitor)
        os.remove(caminho)
        with zipfile.ZipFile(caminho, 'w') as out:
            out.writestr(membro, buf.getvalue().encode('latin-1'))
        return fonte, reeleitos

    def test_rodada_escreve_eleitos_e_o_validador_aprova(self):
        from ferramentas import anteriores
        from pipeline import rodar
        fonte, reeleitos = self._fonte_com_desfecho()
        self.assertGreater(reeleitos, 0, 'nenhum deputado de 2022 concorre de novo '
                           'na fixture, ou o CPF nao veio em um dos anos')
        est = os.path.join(self.tmp, 'estado')
        anteriores.main(['--estado', est, '--fonte-local', FIX, '--uf', 'RR',
                         '--destino', os.path.join(self.tmp, 'd')])
        site = os.path.join(self.tmp, 'site')
        rodar.main(['--fonte-local', fonte, '--ufs', 'RR', '--sem-receita',
                    '--site', site, '--estado', est,
                    '--dados', os.path.join(self.tmp, 'sem-dados'),
                    '--hoje', '2026-10-06'])
        self.assertEqual(V.validar(site), [])
        meta = json.load(open(os.path.join(site, 'meta.json'), encoding='utf-8'))
        self.assertTrue(meta['tem_desfecho'])
        self.assertTrue(meta['eleitos'])
        d = json.load(open(os.path.join(site, 'eleitos', 'BRASIL.json'), encoding='utf-8'))
        destinos = [l[5] for l in d['c'] if l[2] == '6']
        self.assertEqual(destinos.count(EL.MESMO_CARGO), reeleitos)
        self.assertEqual(len(destinos), 8)
        texto = open(os.path.join(site, 'eleitos', 'BRASIL.json'), encoding='utf-8').read()
        for cpf in list(self._cpfs_2022())[:20]:
            self.assertNotIn(cpf, texto)

    def _cpfs_2022(self):
        z22 = zipfile.ZipFile(os.path.join(FIX, 'consulta_cand_2022.zip'))
        return {c.cpf for c in C.candidaturas(z22, 'RR', ano=2022) if c.cpf}
```

E em `tests/test_pipeline.py`, no `test_rodada_inteira_em_roraima` (`TestPontaAPonta`), logo depois de `self.assertEqual(meta['desfecho_desconhecidos'], [])`:

```python
            # sem desfecho nao ha eleitos: nem o arquivo nem a aba
            self.assertIsNone(meta['eleitos'])
            self.assertFalse(os.path.exists(os.path.join(site, 'eleitos')))
```

- [ ] **Passo 2: rodar e ver falhar**

Run: `python -m unittest tests.test_eleitos.TestEscritaEValidacao tests.test_eleitos.TestRodadaComDesfecho tests.test_pipeline.TestPontaAPonta -v`
Expected: ERROR com `AttributeError: module 'pipeline.escrever' has no attribute 'escrever_eleitos'`, e `KeyError: 'eleitos'` no ponta a ponta.

- [ ] **Passo 3: `escrever_eleitos` e o meta**

Em `pipeline/escrever.py`, logo depois da função `grava`:

```python
def escrever_eleitos(pessoas, est, dics, destino):
    """eleitos/BRASIL.json: uma linha de 13 campos por pessoa.

    Partido vai como indice do dicionario do meta, como na linha do ranking, e
    -1 quando o lado nao existe. A sigla de 2022 que sumiu em 2026 entra no
    dicionario do mesmo jeito. Nenhum documento, nem mascarado.
    """
    def pid(sigla):
        return dics['partido'].id(sigla) if sigla else -1

    linhas = []
    for p in sorted(pessoas, key=lambda p: (p['nome'], p['sq'], p['uf_antes'])):
        linhas.append([p['nome'], p['uf_antes'], p['cargo_antes'],
                       pid(p['partido_antes']), p['ano_antes'], p['destino'],
                       p['uf_agora'], p['cargo_agora'], pid(p['partido_agora']),
                       p['desfecho'], p['sq'], p['genero'], p['mudou']])
    fed = {str(dics['partido'].id(sg)): dics['fed'].id(nome)
           for sg, nome in sorted(est['fed'].items())}
    return grava(os.path.join(destino, 'eleitos', 'BRASIL.json'), {
        'anteriores': est['anteriores'],
        'ligados_por_nome': est['ligados_por_nome'],
        'fed': fed, 'c': linhas})
```

Em `escrever_meta`, acrescentar o parâmetro `eleitos=None` ao fim da assinatura (`..., forn=None, desfecho=None, eleitos=None):`) e, no dicionário gravado, junto de `'tem_desfecho'`:

```python
        # A aba de eleitos existe so quando a rodada gravou eleitos/BRASIL.json:
        # depois do desfecho e com anteriores.json valido no estado.
        'eleitos': eleitos,
```

- [ ] **Passo 4: `_checar_eleitos` no validador**

Em `pipeline/validar.py`, depois de `LIMITE_FLUXO_MB`:

```python
# eleitos/BRASIL.json tem umas 3.500 linhas curtas no pais: uns 250 KB.
LIMITE_ELEITOS_MB = 1.0
# Cadeiras da eleicao anterior, para conferir a contagem bruta de anteriores.
# Assembleias e Camara Legislativa somam 1.059 juntas.
CADEIRAS = (('2022', ('1',), 1), ('2022', ('3',), 27), ('2022', ('5',), 27),
            ('2022', ('6',), 513), ('2022', ('7', '8'), 1059), ('2018', ('5',), 54))
```

Antes de `def validar(pasta):`:

```python
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
    if completo:
        ant = d.get('anteriores', {})
        for ano, cargos, cadeiras in CADEIRAS:
            achado = sum(ant.get(ano, {}).get(c, 0) for c in cargos)
            if achado > cadeiras or achado < cadeiras - cadeiras // 50:
                erros.append(f'{rel}: {achado} eleitos em {ano} no cargo '
                             f'{"+".join(cargos)}, esperado perto de {cadeiras}')
    return erros
```

Dentro de `validar`, logo antes do comentário `# amostra de fichas: existe o arquivo de quem tem movimento?`:

```python
    if meta.get('eleitos'):
        rel = os.path.join('eleitos', 'BRASIL.json')
        if not falta(rel):
            caminho = os.path.join(pasta, rel)
            # a contagem de cadeiras so vale quando a rodada leu o pais inteiro
            completo = len([u for u in meta.get('ufs', {}) if u != 'BR']) >= 27
            erros.extend(_checar_eleitos(_le(caminho), n_part, n_fed, completo,
                                         os.path.getsize(caminho) / 1e6))
```

- [ ] **Passo 5: ligar na rodada**

Em `pipeline/rodar.py`, acrescentar aos imports do topo, em ordem alfabética, depois de `from . import desfecho as D`:

```python
from . import eleitos as EL
```

Logo antes da linha `E.escrever_meta(dics, contagens, ...`:

```python
    # Quem foi eleito antes e quem e eleito agora. So existe depois do desfecho
    # e com anteriores.json valido no estado; sem ele a rodada segue, porque
    # nada mais do site depende disso.
    eleitos_meta = None
    if tem_desfecho:
        anteriores, motivo = EL.ler_anteriores(a.estado)
        if motivo == 'falta':
            print('::warning::   aviso: anteriores.json nao esta no estado; rode o '
                  'workflow "eleitos de antes". A aba de eleitos fica de fora.')
        elif motivo == 'sal':
            print('::warning::   aviso: anteriores.json foi feito com outra CONTAS_SAL; '
                  'rode o workflow "eleitos de antes" de novo. A aba fica de fora.')
        else:
            suc = EL.carregar_sucessao(os.path.join(a.dados, 'sucessao-partidos.csv'))
            pessoas, est = EL.cruzar(anteriores, cands, suc, ufs=ufs_pedidas or None)
            b_ele = E.escrever_eleitos(pessoas, est, dics, a.site)
            n_ant = sum(sum(v.values()) for v in est['anteriores'].values())
            if est['siglas_sem_par']:
                print('::warning::   aviso: partidos de antes sem par em 2026 nem na '
                      'tabela de sucessao: ' + ', '.join(est['siglas_sem_par']))
            if n_ant and est['ligados_por_nome'] > 0.05 * n_ant:
                print(f'::warning::   aviso: {est["ligados_por_nome"]} de {n_ant} '
                      'eleitos de antes ligados pelo nome, sem CPF')
            eleitos_meta = {'n': len(pessoas),
                            'ligados_por_nome': est['ligados_por_nome']}
            passo(t0, f'eleitos: {len(pessoas):,} pessoas, {b_ele / 1e3:.0f} KB')
```

E na chamada `E.escrever_meta(...)`, acrescentar `eleitos=eleitos_meta,` junto de `desfecho=desfecho,`.

- [ ] **Passo 6: rodar os testes**

Run: `python -m unittest discover -s tests`
Expected: OK. Se `TestRodadaComDesfecho` falhar no `assertGreater`, a fixture não tem deputado de 2022 concorrendo de novo, ou um dos anos veio sem CPF: leia antes de mexer.

- [ ] **Passo 7: a rodada da fixture continua limpa**

```bash
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita --sem-chave --site site/dados --estado "$TMP/estado-ele"
python -m pipeline.validar site/dados
```
Expected: `site/dados: limpo`, e nenhum `eleitos/` (a fixture é de antes da eleição).

- [ ] **Passo 8: commit**

```bash
git add pipeline/escrever.py pipeline/validar.py pipeline/rodar.py tests/test_eleitos.py tests/test_pipeline.py
git commit -m "A rodada grava eleitos/BRASIL.json depois do desfecho, e o validador confere as cadeiras"
```

---

### Tarefa 5: a aba Eleitos no front

**Arquivos:**
- Modificar: `site/index.html` (CSS perto da linha 669; botão perto da linha 950; `DIMS`/`ROT_DIM` na linha 1055; `erros` na linha 1197; `foraDaDimensao` na linha 1605; `renderChips` nas linhas 1698 e 1725; `fluxoDuasColunas` na linha 2686; bloco novo depois de `ligarFluxo`; `render` na linha 4557; cliques)

**Interfaces:**
- Consome: `eleitos/BRASIL.json` e `meta.eleitos` (Tarefa 4); `fluxoDuasColunas`, `quantosNos`, `hashCom`, `esc`, `inteiro`, `cargoCurto`, `fedCurta`, `ondeUF`, `ufDaTela`, `rotuloDesfecho`, `painelErro`, `skCartao`, `get`.
- Produz: `fluxoDuasColunas(esq, dir, ligs, id, fmt)`, com `fmt` opcional (`{curto, cheio, coluna}`), nó `fixo` que nunca desce para o "outros", e `chaves` somadas no "outros" quando um nó desce; `temEleitos()`, `carregarEleitos()`, `viewEleitos()`.

O front não tem teste de JS. Os testes de redação de `tests/test_pipeline.py` (`TestRedacaoDoSite`) leem toda string do arquivo: acento correto, sem travessão, nenhuma palavra de `PROIBIDAS`.

- [ ] **Passo 1: `fluxoDuasColunas` aceita contagem**

Na assinatura: `function fluxoDuasColunas(esq, dir, ligs, id, fmt){` e, na primeira linha do corpo:

```js
  /* A medida é dinheiro em todo fluxo, menos no de eleitos, que conta pessoas. */
  fmt = fmt || {curto:moeda, cheio:moedaCheia, coluna:'Valor'};
```

Dentro de `podar`, trocar `if(i !== io && !nos[i].outros && medida(nos[i]) * k < 9) some.push(i);` por:

```js
      /* o nó fixo é um destino (perdeu, não concorreu), e não um partido: ele nunca
         desce para o "outros partidos", senão o nome do nó mentiria */
      if(i !== io && !nos[i].outros && !nos[i].fixo && medida(nos[i]) * k < 9) some.push(i);
```

E, no mesmo `podar`, logo depois de `nos[io].valor += nos[i].valor;`:

```js
        if(nos[io].chaves && nos[i].chaves) nos[io].chaves = nos[io].chaves.concat(nos[i].chaves);
```

Trocar as quatro ocorrências de dinheiro dentro de `fluxoDuasColunas`: `esc(moedaCheia(l[2]))` (no `<title>` da faixa e na tabela) por `esc(fmt.cheio(l[2]))`; `esc(moeda(n.valor))` por `esc(fmt.curto(n.valor))`; `moedaCheia(n.valor)` no título do nó por `fmt.cheio(n.valor)`; `'<th scope="col">Valor</th>'` por `'<th scope="col">' + esc(fmt.coluna) + '</th>'`. No título do nó, trocar `(n.href ? '' : '. Sem ficha própria')` por `(n.href || n.fixo ? '' : '. Sem ficha própria')`.

Conferir que a visão geral continua igual: as duas chamadas existentes não passam `fmt`.

- [ ] **Passo 2: CSS**

Depois de `.tabfx summary::after{top:20px}`:

```css
.fluxo.fixo:not(.hl) path{opacity:.07}
.fluxo.fixo:not(.hl) path.sel{opacity:.55}
.ele{display:flex;flex-direction:column}
.ele .tit-ele,.ele .frase-ele{order:0}
.ele #fxele{order:1}
.ele #elelista{order:2}
.ele .eletab{order:3}
.ele .nota-ele{order:4}
@media(max-width:559px){.ele .eletab{order:0}}
.tit-ele{margin:14px var(--gut) 4px;font-size:17px}
.frase-ele{margin:6px var(--gut);line-height:1.5}
.tit-faixa{margin:14px var(--gut) 6px;font-size:15px}
.lista-ele{list-style:none;margin:0;padding:0 var(--gut) 10px}
.lista-ele li{padding:7px 0;border-bottom:1px solid var(--b);line-height:1.45}
.lista-ele .sub{display:block;color:var(--mut);font-size:13px}
.ele .fluxo path{cursor:pointer}
```

- [ ] **Passo 3: botão, estado e dimensão**

Depois de `<button id="ab-doador" data-act="aba" data-v="doador">Doador</button>`:

```html
    <button id="ab-eleitos" data-act="aba" data-v="eleitos" hidden>Eleitos</button>
```

Em `DIMS`, acrescentar `eleitos:1`; em `ROT_DIM`, `eleitos:'eleitos'`. Em `var erros = {...}`, acrescentar `ele:null`.

Em `foraDaDimensao`, como primeira linha do corpo:

```js
  /* na aba de eleitos a medida é gente, e a linha não carrega sinal, tipo nem
     desfecho de candidatura: os três chips ficam desligados */
  if(S.v === 'eleitos') return 'sinal,tipo,desf';
```

- [ ] **Passo 4: chips**

Em `renderChips`, trocar o chip de cargo:

```js
    if(ufDaTela() !== 'BR'){
      /* na aba de eleitos o cargo nunca fica vazio: sem escolha, vale a Câmara */
      var cgv = S.v === 'eleitos' ? cargoEleitos() : S.cargo;
      h += chip('f-cargo','Cargo', cgv ? cargoCurto(META.cargos[cgv] || cgv) : '',
                !!cgv, false);
    }
```

E no laço de `.abas button`, depois de `b.disabled = ...`:

```js
    if(v === 'eleitos') b.hidden = !temEleitos();
```

- [ ] **Passo 5: o bloco de eleitos**

Depois de `function quantosNos(){ ... }`:

```js
/* ---------- eleitos: quem foi eleito antes e quem é eleito agora ---------- */
/* Uma linha por pessoa, 13 campos: nome, uf, cargo, partido e ano de antes, destino,
   uf, cargo e partido de agora, desfecho, sq, gênero, mudou. Quem decide se a pessoa
   mudou de partido é o pipeline, que conhece a tabela de sucessão. */
var ELE = null, eleEmVoo = false;
var CARGOS_ELEITOS = ['6', '5', '3', '7', '8', '1'];
var CARGO_FRASE = {'1':'a Presidência', '3':'o governo', '5':'o Senado',
                   '6':'a Câmara dos Deputados', '7':'as Assembleias Legislativas',
                   '8':'a Câmara Legislativa do DF'};
var SAIDA_ELEITOS = {x2:'eleitos para outro cargo ou estado',
                     x3:'2º turno, a decidir em 25/10',
                     x4:'concorreram a vice ou suplência',
                     x5:'concorreram e não se elegeram',
                     x6:'sem candidatura em 2026'};
var FMT_PESSOAS = {curto:function(v){ return inteiro(v); },
                   cheio:function(v){ return inteiro(v) + (v === 1 ? ' pessoa' : ' pessoas'); },
                   coluna:'Pessoas'};
function temEleitos(){ return !!(META && META.eleitos); }
function carregarEleitos(){
  if(ELE || eleEmVoo || !temEleitos()) return;
  eleEmVoo = true; erros.ele = null;
  get('eleitos/BRASIL.json').then(function(d){
    eleEmVoo = false; ELE = d; if(META) render();
  })['catch'](function(e){
    eleEmVoo = false; erros.ele = {s:(e && e.status === 404) ? 404 : 0}; render();
  });
}
function cargoEleitos(){
  if(ufDaTela() === 'BR') return '1';
  var c = String(S.cargo || '');
  return CARGOS_ELEITOS.indexOf(c) >= 0 ? c : '6';
}
/* O Senado de 2026 renova as cadeiras eleitas em 2018 */
function anoAntes(cargo){ return cargo === '5' ? 2018 : 2022; }
function siglaDe(i){ return i >= 0 ? (META.dic.partido[i] || '?') : 'sem partido'; }
function ladoEleitos(l, cargo, uf){
  var naEsq = l[2] === cargo && l[4] === anoAntes(cargo) && (!uf || l[1] === uf);
  var naDir = l[7] === cargo && (l[9] === 1 || l[9] === 4) && (!uf || l[6] === uf);
  if(!naEsq && !naDir) return null;
  var saida = 'x' + (l[5] === 1 ? 2 : l[5]);
  return {esq: naEsq ? 'p' + l[3] : (l[4] ? 'xoutra' : 'xnovo'),
          dir: naDir ? (l[9] === 4 ? 'x3' : 'p' + l[8]) : saida,
          naEsq: naEsq, naDir: naDir && l[9] === 1};
}
function destacaEleitos(chave){
  if(chave.charAt(0) !== 'p') return false;
  var i = +chave.slice(1);
  if(S.partido) return siglaDe(i) === S.partido;
  if(S.fed){
    var f = META.dic.fed.indexOf(S.fed);
    return f >= 0 && !!ELE.fed && ELE.fed[String(i)] === f;
  }
  return false;
}
function montaEleitos(cargo, uf){
  var pessoas = [], cEsq = {}, cDir = {};
  ELE.c.forEach(function(l){
    var lado = ladoEleitos(l, cargo, uf);
    if(!lado) return;
    pessoas.push({l:l, lado:lado});
    cEsq[lado.esq] = (cEsq[lado.esq] || 0) + 1;
    cDir[lado.dir] = (cDir[lado.dir] || 0) + 1;
  });
  return {pessoas:pessoas, cEsq:cEsq, cDir:cDir};
}
function nosEleitos(cont, saidas, n){
  var partidos = Object.keys(cont).filter(function(k){ return k.charAt(0) === 'p'; })
    .sort(function(a, b){
      return cont[b] - cont[a] || siglaDe(+a.slice(1)).localeCompare(siglaDe(+b.slice(1)));
    });
  var top = partidos.slice(0, n), resto = partidos.slice(n);
  var rot = function(k){ return 'outros ' + inteiro(k) + ' partidos'; };
  var nos = top.map(function(k){
    var sg = siglaDe(+k.slice(1));
    return {nome:sg, valor:cont[k], chaves:[k],
            href:hashCom({partido:(S.partido === sg ? '' : sg), fed:'', cand:'', q:'', forn:''})};
  });
  if(resto.length){
    nos.push({n:resto.length, rot:rot, nome:rot(resto.length), outros:1, chaves:resto,
              valor:resto.reduce(function(s, k){ return s + cont[k]; }, 0)});
  }
  saidas.forEach(function(s){
    if(cont[s[0]]) nos.push({nome:s[1], valor:cont[s[0]], chaves:[s[0]], fixo:1});
  });
  return nos;
}
function indicePorChave(nos){
  var ix = {};
  nos.forEach(function(n, i){ n.chaves.forEach(function(k){ ix[k] = i; }); });
  return ix;
}
function listaPt(xs){
  return xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' e ' + xs[xs.length - 1];
}
function contaPt(n, um, varios){ return inteiro(n) + ' ' + (n === 1 ? um : varios); }
function fraseEleitos(R, cargo, ano, uf){
  var d = {mesmo:0, x2:0, x3:0, x4:0, x5:0, x6:0}, cEsq = 0, cDir = 0, novo = 0, outra = 0;
  R.pessoas.forEach(function(p){
    if(p.lado.naEsq){
      cEsq++;
      d[p.lado.dir.charAt(0) === 'p' ? 'mesmo' : p.lado.dir]++;
    }
    if(p.lado.naDir){
      cDir++;
      if(p.lado.esq === 'xnovo') novo++;
      else if(p.lado.esq === 'xoutra') outra++;
    }
  });
  var onde = uf ? ' ' + ondeUF(uf) : '';
  var f = '';
  if(cEsq){
    var partes = [];
    if(d.mesmo) partes.push(contaPt(d.mesmo, 'foi eleito de novo para o mesmo cargo', 'foram eleitos de novo para o mesmo cargo'));
    if(d.x2) partes.push(contaPt(d.x2, 'foi eleito para outro cargo ou estado', 'foram eleitos para outro cargo ou estado'));
    if(d.x3) partes.push(contaPt(d.x3, 'disputa o 2º turno em 25/10', 'disputam o 2º turno em 25/10'));
    if(d.x4) partes.push(contaPt(d.x4, 'concorreu a vice ou suplência', 'concorreram a vice ou suplência'));
    if(d.x5) partes.push(contaPt(d.x5, 'concorreu e não se elegeu', 'concorreram e não se elegeram'));
    if(d.x6) partes.push(contaPt(d.x6, 'não registrou candidatura', 'não registraram candidatura'));
    f = 'Dos ' + inteiro(cEsq) + ' eleitos para ' + CARGO_FRASE[cargo] + onde + ' em ' + ano +
        ', ' + listaPt(partes) + '. ';
  }
  var p2 = [];
  if(novo) p2.push(contaPt(novo, 'não tinha sido eleito em ' + ano, 'não tinham sido eleitos em ' + ano));
  if(outra) p2.push(contaPt(outra, 'tinha sido eleito em outra disputa', 'tinham sido eleitos em outra disputa'));
  if(cDir) f += 'Dos ' + inteiro(cDir) + ' eleitos agora' + (p2.length ? ', ' + listaPt(p2) : '') + '.';
  return f.trim();
}
function fraseDoPartido(R, ano){
  var rot = S.partido || fedCurta(S.fed);
  var antes = 0, agora = 0, mesmo = 0, mudou = 0, novo = 0;
  R.pessoas.forEach(function(p){
    if(p.lado.naEsq && destacaEleitos(p.lado.esq)) antes++;
    if(p.lado.naDir && destacaEleitos(p.lado.dir)){
      agora++;
      if(p.lado.esq === 'xnovo') novo++;
      else if(p.l[12]) mudou++;
      else mesmo++;
    }
  });
  var f = rot + ': ' + contaPt(antes, 'eleito', 'eleitos') + ' em ' + ano + ' e ' +
          inteiro(agora) + ' agora.';
  if(agora){
    f += ' Dos eleitos agora, ' + listaPt([
      inteiro(mesmo) + ' já tinham sido eleitos pelo mesmo partido ou pelo sucessor',
      inteiro(mudou) + ' por outro partido',
      inteiro(novo) + ' não tinham sido eleitos']) + '.';
  }
  return f;
}
function tabelaEleitos(R, ano){
  var t = {};
  function lin(sg){ return t[sg] || (t[sg] = {sg:sg, antes:0, agora:0, re:0}); }
  R.pessoas.forEach(function(p){
    if(p.lado.naEsq) lin(siglaDe(p.l[3])).antes++;
    if(p.lado.naDir){
      var x = lin(siglaDe(p.l[8]));
      x.agora++;
      if(p.l[4] && !p.l[12]) x.re++;
    }
  });
  var ls = Object.keys(t).map(function(k){ return t[k]; }).sort(function(a, b){
    return b.agora - a.agora || b.antes - a.antes || a.sg.localeCompare(b.sg);
  });
  return '<details class="tabfx" open><summary><b>Por partido</b></summary><table><thead><tr>' +
    '<th scope="col">Partido</th><th scope="col" class="num">Eleitos em ' + ano + '</th>' +
    '<th scope="col" class="num">Eleitos agora</th><th scope="col" class="num">Diferença</th>' +
    '<th scope="col" class="num">Já eleitos antes, sem mudar de partido</th></tr></thead><tbody>' +
    ls.map(function(x){
      var df = x.agora - x.antes;
      return '<tr><td>' + esc(x.sg) + '</td><td class="num">' + inteiro(x.antes) +
        '</td><td class="num">' + inteiro(x.agora) + '</td><td class="num">' +
        (df > 0 ? '+' : '') + inteiro(df) + '</td><td class="num">' + inteiro(x.re) + '</td></tr>';
    }).join('') + '</tbody></table></details>';
}
function cargoDaPessoa(c){ return META.cargos[c] ? cargoCurto(META.cargos[c]) : 'vice ou suplência'; }
function linhaEleito(l){
  var fem = l[11] === 'F';
  var nome = l[10] ? '<a href="#' + esc(hashCom({cand:l[10], q:'', forn:''})) + '">' + esc(l[0]) + '</a>'
                   : esc(l[0]);
  var partes = [];
  if(l[4]) partes.push((fem ? 'eleita' : 'eleito') + ' em ' + l[4] + ': ' +
                       cargoDaPessoa(l[2]) + ', ' + siglaDe(l[3]) + ', ' + l[1]);
  if(l[7]) partes.push('em 2026: ' + cargoDaPessoa(l[7]) + ', ' + siglaDe(l[8]) + ', ' + l[6] +
                       (l[9] ? ', ' + rotuloDesfecho(l[9], fem).toLowerCase() : ''));
  else partes.push('sem candidatura registrada em 2026');
  if(l[12]) partes.push('mudou de partido');
  return nome + ' <span class="sub">' + esc(partes.join('; ')) + '</span>';
}
function listaDaFaixa(a, b, R){
  var quem = R.pessoas.filter(function(p){
    return a.chaves.indexOf(p.lado.esq) >= 0 && b.chaves.indexOf(p.lado.dir) >= 0;
  }).sort(function(x, y){ return x.l[0].localeCompare(y.l[0], 'pt-BR'); });
  var el = document.getElementById('elelista');
  if(!el) return;
  el.innerHTML = '<h3 class="tit-faixa">' + esc(a.nome + ' para ' + b.nome + ': ' +
    FMT_PESSOAS.cheio(quem.length)) + '</h3><ul class="lista-ele">' +
    quem.map(function(p){ return '<li>' + linhaEleito(p.l) + '</li>'; }).join('') + '</ul>';
  el.scrollIntoView({block:'nearest'});
}
function ligarEleitos(host, esq, dir, R){
  var svg = host && host.querySelector('svg.fluxo');
  if(!svg) return;
  if(S.partido || S.fed){
    svg.classList.add('fixo');
    var ps = svg.querySelectorAll('path');
    for(var i = 0; i < ps.length; i++){
      var a = esq[+ps[i].getAttribute('data-e')], b = dir[+ps[i].getAttribute('data-d')];
      ps[i].classList.toggle('sel', a.chaves.some(destacaEleitos) || b.chaves.some(destacaEleitos));
    }
  }
  svg.addEventListener('click', function(e){
    var p = e.target.closest('path');
    if(p) listaDaFaixa(esq[+p.getAttribute('data-e')], dir[+p.getAttribute('data-d')], R);
  });
}
function notaEleitos(cargo, ano){
  var n = ELE.ligados_por_nome || 0;
  return '<p class="notafx nota-ele">' + esc(
    'Contagem de pessoas, pela situação que o TSE publica depois da totalização. ' +
    '"Eleito em ' + ano + '" é o resultado daquela eleição, e não quem exerce o mandato ' +
    'hoje: houve suplente que assumiu, cassação e morte. Mudança de partido conta só ' +
    'quando o partido novo não é o sucessor do antigo por fusão ou incorporação.' +
    (cargo === '5' ? ' No Senado, as cadeiras em disputa em 2026 são as eleitas em 2018.' : '') +
    (n ? ' ' + contaPt(n, 'pessoa eleita antes não tem', 'pessoas eleitas antes não têm') +
         ' CPF no arquivo do TSE e foram ligadas pelo nome completo e pela data de nascimento.' : '') +
    ' Toque numa faixa para ver quem está nela.') + '</p>';
}
function viewEleitos(){
  var m = document.getElementById('conteudo');
  if(erros.ele){
    m.innerHTML = painelErro('Não foi possível carregar a lista de eleitos. Verifique a conexão.',
                             'retryele');
    return;
  }
  if(!ELE){ carregarEleitos(); m.innerHTML = '<div class="cartao">' + skCartao() + '</div>'; return; }
  var cargo = cargoEleitos(), uf = ufDaTela() === 'BRASIL' ? '' : ufDaTela();
  var ano = anoAntes(cargo);
  var R = montaEleitos(cargo, uf);
  var h = '<div class="cartao ele"><h2 class="tit-ele">' +
    esc('Eleitos para ' + CARGO_FRASE[cargo] + ', ' + ano + ' e 2026' + (uf ? ' ' + ondeUF(uf) : '')) + '</h2>';
  if(!R.pessoas.length){
    m.innerHTML = h + '<p class="frase-ele">' +
      esc('Nenhuma pessoa eleita para este cargo neste recorte.') + '</p></div>';
    return;
  }
  h += '<p class="frase-ele">' + esc(fraseEleitos(R, cargo, ano, uf)) + '</p>';
  if(S.partido || S.fed) h += '<p class="frase-ele">' + esc(fraseDoPartido(R, ano)) + '</p>';
  h += '<div class="eletab">' + tabelaEleitos(R, ano) + '</div>' +
       '<div id="fxele"></div><div id="elelista" aria-live="polite"></div>' +
       notaEleitos(cargo, ano) + '</div>';
  m.innerHTML = h;
  var n = quantosNos();
  var esq = nosEleitos(R.cEsq, [['xoutra', 'já eleitos em outra disputa'],
                                ['xnovo', 'não tinham sido eleitos em ' + ano]], n);
  var dir = nosEleitos(R.cDir, ['x2', 'x3', 'x4', 'x5', 'x6'].map(function(k){
    return [k, SAIDA_ELEITOS[k]];
  }), n);
  var ie = indicePorChave(esq), id = indicePorChave(dir), soma = {};
  R.pessoas.forEach(function(p){
    var ch = ie[p.lado.esq] + ':' + id[p.lado.dir];
    soma[ch] = (soma[ch] || 0) + 1;
  });
  var ligs = Object.keys(soma).map(function(ch){
    var ab = ch.split(':');
    return [+ab[0], +ab[1], soma[ch]];
  });
  fluxoDuasColunas(esq, dir, ligs, 'fxele', FMT_PESSOAS);
  ligarEleitos(document.getElementById('fxele'), esq, dir, R);
}
```

- [ ] **Passo 6: `render` e cliques**

Em `render`, logo depois de `if(!temDesfecho()) S.desf = '';`:

```js
  /* a aba de eleitos só existe depois do desfecho e com o arquivo publicado */
  if(S.v === 'eleitos' && !temEleitos()) S.v = 'geral';
```

Na cadeia de visões, antes de `else if(S.v === 'fornecedor') viewFornRecorte();`:

```js
  else if(S.v === 'eleitos') viewEleitos();
```

No tratador de cliques, junto de `retryflx`:

```js
  if(a === 'retryele'){ erros.ele = null; carregarEleitos(); render(); return; }
```

- [ ] **Passo 7: os testes de redação**

Run: `python -m unittest tests.test_pipeline.TestRedacaoDoSite tests.test_pipeline.TestHigieneDoFonte -v`
Expected: PASS. Palavra sem acento ou travessão aparece aqui: corrija a string, não o teste.

- [ ] **Passo 8: um `eleitos/BRASIL.json` de mentira para ver a tela**

Gerar a saída da fixture e acrescentar à mão um arquivo com os seis destinos. Escreva o script com a ferramenta de edição (não por heredoc) em `$TMP/ele_falso.py`:

```python
import json, sys
site = sys.argv[1]
meta = json.load(open(f'{site}/meta.json', encoding='utf-8'))
p = meta['dic']['partido']
def ix(s):
    if s not in p:
        p.append(s)
    return p.index(s)
L = []
def pessoa(nome, pa, destino, cg, pg, desf, sq, ano=2022, ca='6', mudou=0):
    L.append([nome, 'RR' if ano else '', ca if ano else '', ix(pa) if pa else -1, ano,
              destino, 'RR' if cg else '', cg, ix(pg) if pg else -1, desf, sq, 'F', mudou])
for i in range(3): pessoa(f'REELEITA {i}', 'PL', 1, '6', 'PL', 1, f'r{i}')
pessoa('MUDOU', 'PSC', 1, '6', 'PT', 1, 'm1', mudou=1)
pessoa('SUCESSOR', 'PSC', 1, '6', 'PODE', 1, 's1')
pessoa('SENADORA', 'PT', 2, '5', 'PT', 1, 'o1')
pessoa('SEGUNDO', 'MDB', 3, '3', 'MDB', 4, 'g1')
pessoa('VICE', 'MDB', 4, '4', 'MDB', 1, 'v1')
pessoa('PERDEU', 'PL', 5, '6', 'PL', 3, 'p1')
pessoa('SAIU', 'UNIÃO', 6, '', '', 0, '')
for i in range(2): pessoa(f'NOVATA {i}', '', 0, '6', 'PSD', 1, f'n{i}', ano=0)
pessoa('ERA SENADORA', 'PP', 2, '6', 'PP', 1, 'e1', ano=2022, ca='5')
json.dump({'anteriores': {}, 'ligados_por_nome': 1, 'fed': {}, 'c': L},
          open(f'{site}/eleitos/BRASIL.json', 'w', encoding='utf-8'), ensure_ascii=False)
meta['eleitos'] = {'n': len(L), 'ligados_por_nome': 1}
meta['tem_desfecho'] = True
json.dump(meta, open(f'{site}/meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
```

```bash
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita --sem-chave --site site/dados --estado "$TMP/estado-ele"
mkdir -p site/dados/eleitos && python "$TMP/ele_falso.py" site/dados
cd site && python -m http.server 8777
```

- [ ] **Passo 9: conferência visual**

Abrir `http://localhost:8777/#v=eleitos&uf=RR` no navegador (Chrome, com a skill `claude-in-chrome`), em 1280 px e em 390 px de largura, claro e escuro. Conferir, um por um:
1. O botão Eleitos aparece no fim da barra; sem `meta.eleitos` ele some (apague a chave do meta, recarregue, volte).
2. O chip de cargo mostra Dep. federal sem nada escolhido; sinal, tipo e desfecho ficam desligados.
3. A frase diz: dos 10 eleitos para a Câmara dos Deputados em Roraima em 2022, 5 foram eleitos de novo para o mesmo cargo, 1 para outro cargo ou estado, 1 disputa o 2º turno, 1 concorreu a vice ou suplência, 1 concorreu e não se elegeu, 1 não registrou candidatura; dos 8 eleitos agora, 2 não tinham sido eleitos em 2022 e 1 tinha sido eleito em outra disputa. Confira a soma contra o desenho.
4. À esquerda, "não tinham sido eleitos em 2022" (2) e "já eleitos em outra disputa" (1); à direita, os cinco destinos, nenhum deles dentro de "outros partidos".
5. Tocar numa faixa lista as pessoas dela; o nome com `sq` leva à ficha (que vai dar erro de ficha inexistente com o dado falso, e é esperado); "voltar" traz a aba de volta.
6. Escolher o partido PL no chip: as faixas do PL acendem, as outras apagam, a segunda frase aparece; passar o mouse num nó e tirar devolve o destaque do PL.
7. Cargo Senado: o título diz 2018 e a nota fala das cadeiras de 2018. Unidade BR: cargo vira Presidência. UF DF com Assembleia: a frase de recorte vazio, sem erro no console.
8. Em 390 px, a tabela "Por partido" vem antes do desenho, e não há rolagem horizontal.
9. A visão geral continua igual (os dois fluxos de dinheiro, com R$ nos rótulos).

Ler o console com `read_console_messages`: nenhum erro.

- [ ] **Passo 10: limpar e commitar**

```bash
rm -rf site/dados
git add site/index.html
git commit -m "A aba de eleitos, com o fluxo de 2022 para 2026 por partido, a frase de números e a lista de cada faixa"
```

---

### Tarefa 6: CLAUDE.md, rodada final e publicação

**Arquivos:**
- Modificar: `CLAUDE.md`

**Interfaces:**
- Consome: tudo das Tarefas 1 a 5.

- [ ] **Passo 1: CLAUDE.md**

Na tabela "Como está por dentro": em `site/dados/`, acrescentar `eleitos/BRASIL.json` (quem foi eleito antes e quem é eleito agora, uma linha por pessoa); em `ferramentas/`, `anteriores` (lê os eleitos de 2018 e 2022 uma vez); em `dados/`, `sucessao-partidos.csv`; na frase do estado, `anteriores.json`.

Em "Regras de trabalho", um item novo:

```markdown
- **A aba de eleitos compara cada cargo com a eleição anterior da mesma cadeira** `[decidido, Guilherme 06/10/2026]`: o Senado com 2018, o resto com 2022. "Segue eleito" vale para qualquer cargo, e partido que acabou é seguido pelo sucessor de `dados/sucessao-partidos.csv`: quem foi do PSC para o Podemos não mudou de partido. Os eleitos de antes moram em `anteriores.json`, na branch `dados`, feitos uma vez pelo workflow `anteriores.yml` com a `CONTAS_SAL`: cada pessoa é um HMAC, nunca CPF nem data de nascimento. **Se a `CONTAS_SAL` mudar, rode o workflow de novo**; até lá a rodada segue sem a aba e avisa. A tela diz "eleita em 2022", nunca "deputada atual": o TSE sustenta a eleição, não o mandato.
```

Em "O que o dado ensinou", o que a Tarefa 2 mostrou sobre o CPF e o arquivo BRASIL de 2018 e 2022 (uma ou duas frases, com os números do log).

- [ ] **Passo 2: suíte, rodada e validador**

Run: `python -m unittest discover -s tests`
Expected: OK.

```bash
python -m pipeline.rodar --fonte-local tests/fixtures/tse-rr --ufs RR --sem-receita --sem-chave --site site/dados --estado "$TMP/estado-ele2"
python -m pipeline.validar site/dados
rm -rf site/dados
```
Expected: `site/dados: limpo`.

- [ ] **Passo 3: commit**

```bash
git add CLAUDE.md
git commit -m "O CLAUDE.md conta a aba de eleitos, a comparacao do Senado com 2018 e o anteriores.json"
```

- [ ] **Passo 4: revisão do branch inteiro**

Usar superpowers:requesting-code-review sobre `main..eleitos-sankey`.

- [ ] **Passo 5: publicar (com OK do Guilherme a cada passo)**

1. `gh workflow run anteriores.yml -f gravar=true` e conferir no log as contagens da Tarefa 2, passo 3.
2. Merge de `eleitos-sankey` no `main` e push.
3. `gh workflow run diario.yml -f sem_receita=true`; no log, procurar `eleitos:` e os avisos `siglas_sem_par`; o validador precisa sair limpo (a conferência de cadeiras roda aqui pela primeira vez).
4. Abrir `https://guipfranco.github.io/contas2026/#v=eleitos` e repetir os itens 2, 3, 6 e 7 da conferência visual com o dado real.
5. Remover a worktree: `git -C /d/repos/contas2026 worktree remove /d/repos/contas2026-eleitos`.
