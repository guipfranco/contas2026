#!/usr/bin/env python3
"""O endereco publico de um fornecedor, sem repetir o CPF de ninguem.

**O problema.** A ficha de fornecedor precisa de um identificador estavel: o
mesmo fornecedor tem de abrir no mesmo endereco hoje e amanha, e o link tem de
sobreviver a rodada da noite. O documento serve, mas para pessoa fisica ele e
justamente o que a trava do projeto manda nao publicar.

**Por que hash nao basta.** Um sha256 do CPF parece anonimo e nao e: sao 10^11
combinacoes, e uma placa de video moderna varre isso em segundos. Publicar o
hash e publicar o CPF para quem quiser gastar dez minutos.

**O que este modulo faz.** O identificador de pessoa fisica e um HMAC-SHA256
truncado, com uma chave que **nao mora no repositorio**: ela vem da variavel de
ambiente CONTAS_SAL, que no GitHub Actions e um secret. Sem a chave nao ha
como voltar do identificador para o CPF, nem montando a tabela inteira.

CNPJ nao passa por isso: empresa e publica por natureza, e o proprio numero e o
endereco mais util que existe (da para conferir na Receita, no mesmo instante).

**Quando a chave falta** (maquina de quem desenvolve, rodada local) o modulo usa
um sal declarado aqui e avisa quem chamar, porque nessa condicao o
identificador de pessoa fisica e reversivel e nao deve ir ao ar.
"""
import hashlib
import hmac
import os

SAL_DE_DESENVOLVIMENTO = b'contas2026-sem-segredo-nao-publique'
# 16 hex sao 64 bits. Com 12 (48 bits) e 380 mil pessoas fisicas, a chance de
# duas cairem no mesmo identificador passava de 0,5 %, e a ficha de uma
# sobrescreveria a da outra em silencio.
TAMANHO = 16


def sal():
    """A chave do HMAC. Do ambiente em producao, declarada em desenvolvimento."""
    do_ambiente = os.environ.get('CONTAS_SAL', '').strip()
    return do_ambiente.encode('utf-8') if do_ambiente else SAL_DE_DESENVOLVIMENTO


def tem_sal_de_verdade():
    return bool(os.environ.get('CONTAS_SAL', '').strip())


def ident(doc):
    """CNPJ vira ele mesmo; CPF vira 'p' + 12 hex de HMAC. Vazio vira ''.

    O 'p' na frente e o que deixa o front saber, sem tabela, se aquele endereco
    e de empresa ou de pessoa fisica.
    """
    doc = (doc or '').strip()
    if not doc:
        return ''
    if len(doc) == 14:
        return doc
    marca = hmac.new(sal(), doc.encode('utf-8'), hashlib.sha256)
    return 'p' + marca.hexdigest()[:TAMANHO]


def ident_publico(doc):
    """O identificador que pode ir ao ar, ou vazio.

    Sem a chave do ambiente, pessoa fisica nao ganha endereco publico: o HMAC com
    sal declarado volta ao CPF por forca bruta. Quem chama isto e quem escreve
    lista e link; a ficha em si tambem nao e gerada, em escrever.py.
    """
    doc = (doc or '').strip()
    if len(doc) != 14 and not tem_sal_de_verdade():
        return ''
    return ident(doc)


def bloco(identificador, quantos=256):
    """Em que arquivo aquele fornecedor mora.

    Sao centenas de milhares de fornecedores, e um arquivo por fornecedor
    derruba o deploy do Pages (419 mil arquivos num artifact so). Eles moram em
    blocos, e o front descobre o bloco pela mesma conta, sem baixar indice
    nenhum. A conta e um djb2 simples justamente para caber em cinco linhas de
    JavaScript e dar o mesmo numero nos dois lados.
    """
    h = 5381
    for ch in (identificador or ''):
        h = ((h * 33) ^ ord(ch)) & 0xFFFFFFFF
    return h % quantos
