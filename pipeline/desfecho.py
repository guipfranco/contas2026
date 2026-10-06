"""O desfecho da urna, do texto do TSE para um codigo pequeno.

`DS_SIT_TOT_TURNO` vem do consulta_cand e so e preenchido depois da
totalizacao; ate la e `#NULO` em toda linha. O vocabulario aqui e o historico
do TSE. Texto que ele nao reconhece vira 0 e e marcado como desconhecido, para
sair em meta.desfecho_desconhecidos e ser corrigido na rodada seguinte sem
derrubar o site.
"""
import re
import unicodedata

from .carregar import VAZIO

ELEITA, SUPLENTE, NAO_ELEITA, SEGUNDO_TURNO = 1, 2, 3, 4

# texto normalizado -> codigo
TABELA = {
    'ELEITO': ELEITA,
    'ELEITO POR QP': ELEITA,
    'ELEITO POR MEDIA': ELEITA,
    'SUPLENTE': SUPLENTE,
    'NAO ELEITO': NAO_ELEITA,
    '2O TURNO': SEGUNDO_TURNO,
    '2 TURNO': SEGUNDO_TURNO,
    'SEGUNDO TURNO': SEGUNDO_TURNO,
}


def normaliza(texto):
    """Caixa alta, sem acento, um espaco so; vazio para marcador de vazio."""
    s = (texto or '').strip()
    if s in VAZIO:
        return ''
    # o ordinal masculino e o simbolo de grau viram 'O' antes de tirar acento,
    # para '2º TURNO' e '2° TURNO' cairem na mesma chave
    s = s.replace('º', 'O').replace('°', 'O')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).upper()


def codigo(texto):
    return TABELA.get(normaliza(texto), 0)


def desconhecido(texto):
    """Texto nao vazio que a tabela nao reconhece."""
    n = normaliza(texto)
    return bool(n) and n not in TABELA
