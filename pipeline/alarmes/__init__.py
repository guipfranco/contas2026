#!/usr/bin/env python3
"""O registro dos sinais, e as regras de redacao que valem para todos eles.

Um sinal deste painel **nao e uma acusacao**. Ele diz que um numero chamou
atencao e mostra qual numero foi, para quem quiser ir olhar. A redacao segue
quatro travas, e nenhuma delas e negociavel:

1. **Numero antes de adjetivo.** "Fornecedor aberto ha 47 dias" e um fato.
   "Fornecedor de fachada" e uma afirmacao sobre gente, que este painel nao
   tem como sustentar.
2. **Nenhuma palavra que impute conduta.** Nada de fraude, laranja, desvio,
   superfaturamento, irregular. Quando o padrao e legal e so atipico, o texto
   diz isso na propria frase.
3. **A explicacao inocente vem junto**, quando existe uma comum. Rateio de
   material entre candidatos e legal e produz o mesmo padrao de nota repetida;
   quem le precisa saber disso na mesma linha.
4. **CPF mascarado sempre.** Nome de pessoa fisica aparece, porque o gasto
   eleitoral e publico, mas o documento nao sai inteiro daqui.

Gravidade: 1 vale olhar, 2 vale conferir, 3 confira primeiro. Gravidade nao e
medida de ilegalidade, e ordem de fila de quem vai checar.
"""
import collections

Alarme = collections.namedtuple(
    'Alarme', 'codigo grav sq doc valor texto', defaults=('', 0, ''))

# codigo -> (familia, nome curto, o que significa, o que NAO significa)
CATALOGO = {
    'A1': ('fornecedor', 'CNPJ recém-aberto',
           'A empresa foi aberta pouco antes de começar a receber da campanha.',
           'Abrir empresa para prestar serviço de campanha é legal e comum.'),
    'A2': ('fornecedor', 'CNPJ fora de atividade',
           'A Receita Federal não registra a empresa como ativa.',
           'A baixa pode ter ocorrido depois do serviço prestado.'),
    'A3': ('fornecedor', 'fornecedor é candidato',
           'Quem recebeu também é candidato nesta eleição.',
           'Candidato pode ceder bem ou serviço a outro, e isso é declarado.'),
    'A4': ('fornecedor', 'atividade destoa do gasto',
           'A atividade econômica registrada do fornecedor não costuma casar '
           'com o tipo de despesa.',
           'Empresa pode prestar serviço fora do seu CNAE principal.'),
    'A5': ('fornecedor', 'gasto concentrado',
           'Boa parte do gasto do candidato foi para um só fornecedor.',
           'Contratar uma agência que faz tudo produz o mesmo número.'),
    'A6': ('fornecedor', 'pessoa física recebeu muito',
           'Uma pessoa física, não uma empresa, recebeu um valor alto.',
           'Cabo eleitoral, motorista e prestador autônomo são contratados '
           'assim, legalmente.'),
    'D1': ('ritmo', 'fornecedor novo hoje',
           'Este fornecedor aparece pela primeira vez na base hoje.',
           'Prestação de contas é entregue aos poucos; aparecer hoje é normal.'),
    'D2': ('ritmo', 'salto no gasto declarado',
           'O total declarado subiu muito de um dia para o outro.',
           'O salto costuma ser a entrega de um lote de notas, não gasto novo.'),
    'D3': ('ritmo', 'mesma nota em duas contas',
           'O mesmo número de documento, do mesmo fornecedor, aparece na conta '
           'de mais de um candidato.',
           'Rateio de material conjunto é legal e produz exatamente isso.'),
    'C1': ('candidato', 'perto do limite de gastos',
           'O gasto declarado se aproxima do limite legal do cargo.',
           'O limite vale para o total da campanha, e a conta ainda não fechou.'),
    'C2': ('candidato', 'nada declarado',
           'A candidatura não tem receita nem despesa declarada até agora.',
           'Quem não movimentou dinheiro presta contas ao final, sem nada a '
           'declarar.'),
    'B1': ('doador', 'doador também é fornecedor',
           'Quem doou para a campanha também recebeu dela como fornecedor.',
           'Prestar serviço e doar são atos distintos, ambos permitidos.'),
    'B2': ('doador', 'doações iguais no mesmo dia',
           'Várias pessoas diferentes doaram o mesmo valor no mesmo dia.',
           'Campanha de arrecadação com valor sugerido produz esse padrão.'),
    'B3': ('doador', 'recursos próprios altos',
           'A parcela bancada pelo próprio candidato é alta.',
           'O limite legal é sobre o rendimento do candidato, que não é público.'),
    'B4': ('doador', 'fundo para candidatas abaixo de 30 %',
           'A fatia do dinheiro público que chegou a candidatas do partido '
           'está abaixo do mínimo legal.',
           'A regra é aferida no fim da campanha, não no meio.'),
}

GRAVIDADE = {1: 'vale olhar', 2: 'vale conferir', 3: 'confira primeiro'}

# Palavras que nao podem aparecer em texto de alarme. O teste cobre isso.
PROIBIDAS = (
    'fraude', 'fraudulent', 'laranja', 'desvio', 'desviou', 'superfatur',
    'sobrepreço', 'sobrepreco', 'irregular', 'ilegal', 'crime', 'criminos',
    'corrupção', 'corrupcao', 'caixa dois', 'fachada', 'suspeito', 'suspeita',
    'escândalo', 'escandalo', 'roubo', 'roubou', 'lavagem',
)


def moeda(centavos):
    """R$ 1,2 mi / R$ 35 mil / R$ 847. Numero legivel num celular."""
    v = centavos / 100
    if v >= 1_000_000:
        return f'R$ {v / 1_000_000:.1f} mi'.replace('.', ',')
    if v >= 1_000:
        return f'R$ {v / 1000:.0f} mil'
    return f'R$ {v:.0f}'


def pct(parte, todo):
    return 0 if not todo else round(parte / todo * 100)


class Contexto:
    """Tudo que um alarme pode precisar alem do proprio candidato."""

    def __init__(self, nac, receita=None, tetos=None, cnae_por_tipo=None,
                 cnae_nome=None, hoje='', primeira_vez=None, ontem=None,
                 plataformas=()):
        self.nac = nac
        self.receita = receita or {}
        self.tetos = tetos or {}
        self.cnae_por_tipo = cnae_por_tipo or {}
        self.cnae_nome = cnae_nome or {}
        self.hoje = hoje
        self.primeira_vez = primeira_vez or {}
        self.ontem = ontem or {}
        self.plataformas = set(plataformas)

    def teto(self, uf, cargo):
        return self.tetos.get((uf, cargo)) or self.tetos.get(('BR', cargo))


def avaliar(a, ctx):
    """Todos os sinais de um candidato, ja com a redacao pronta."""
    from . import fornecedor, ritmo, candidato, doador
    saida = []
    for mod in (fornecedor, ritmo, candidato, doador):
        try:
            saida.extend(mod.avaliar(a, ctx))
        except Exception as e:  # noqa: BLE001
            # Um alarme que quebra nao pode derrubar a rodada inteira.
            print(f'   alarme {mod.__name__} falhou em {a.sq}: '
                  f'{type(e).__name__}: {e}')
    return saida


def confere_redacao(alarmes):
    """Devolve os textos que violam as travas de redacao. Vazio e o esperado."""
    ruins = []
    for x in alarmes:
        baixo = x.texto.lower()
        for p in PROIBIDAS:
            if p in baixo:
                ruins.append((x.codigo, p, x.texto))
        if not any(c.isdigit() for c in x.texto):
            ruins.append((x.codigo, 'sem número', x.texto))
    return ruins
