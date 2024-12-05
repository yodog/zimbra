#!/usr/bin/env python

import ldap
import os

from mod_zmb_mylogformatter import logger as log

from collections import defaultdict
from timeit      import default_timer as timer

__author__  = 'yodog'
__version__ = '2019.07.12.1610'

# ------------------------------------------------------------------------------
# Definicoes
# ------------------------------------------------------------------------------

# Iniciar medicao de tempo de execucao deste script
start_time_script = timer()

# Tamanho das informacoes exibidas na tela
TRUNCATE = 99

# Algumas informacoes para serem usadas adiante
FQDN       = os.popen('hostname -f').read().split()[0]
SCRIPTNAME = os.path.splitext(os.path.basename(__file__))[0]
SCRIPTPATH = os.path.realpath(__file__)

# ------------------------------------------------------------------------------
# Funcoes
# ------------------------------------------------------------------------------

# * * *
# Returns ldap connection object
# * * *

def createLdapConn():
    LDAP_SERVER = "1.2.3.4"
    LDAP_USER   = "cn=config"
    LDAP_PASS   = "password"

    log.debug('Criando conexao ldap://%s', LDAP_SERVER)

    connection                  = ldap.initialize("ldap://%s" % LDAP_SERVER)
    connection.protocol_version = ldap.VERSION3
    connection.bind (LDAP_USER, LDAP_PASS)

    return connection

# * * *
# Returns dict with all zimbra accounts and the requested attrs
# * * *

def zmbGetAllAccounts():
    log.info('')
    log.info('Consultando contas de usuario')

    start_time_ldap = timer()
    LDAP_BASE_DN = "dc=br"
    LDAP_FILTRO  = """
        (&
            (objectClass=zimbraAccount)
            (zimbraMailDeliveryAddress=*)
            (!
                (|
                    (objectClass=zimbraCalendarResource)
                    (zimbraExternalUserMailAddress=*)
                )
            )
        )
    """
    LDAP_ATRIBUTOS = [
        "zimbraAccountStatus",
        "zimbraIsAdminAccount",
        "zimbraIsDelegatedAdminAccount",
        "zimbraIsSystemAccount",
        "zimbraMailDeliveryAddress",
    ]

    # Remover identacao da string LDAP_FILTRO (causa erro no consulta ldap)
    LDAP_FILTRO = "".join(LDAP_FILTRO.split())

    # Exportar esta constante para o escopo global pois preciso usa-la no fim do script
    if 'LDAP_ATRIBUTOS' not in globals(): globals()['LDAP_ATRIBUTOS'] = LDAP_ATRIBUTOS

    connection      = createLdapConn()
    ldapsearch      = connection.search_s(LDAP_BASE_DN, ldap.SCOPE_SUBTREE, LDAP_FILTRO, LDAP_ATRIBUTOS)
    end_time_ldap   = timer() - start_time_ldap

    log.info('... %d conta(s) encontrado(s) em %s segundos', len(ldapsearch), round(end_time_ldap,2))
    log.debug(str(ldapsearch))
    log.info('')

    return sorted(ldapsearch)

# * * *
# Pesquisar ldap e criar banco de dados indexado por dominio
# * * *

def createDomainDatabase():
    log.info('-' * TRUNCATE)
    log.info('Criando banco de dados indexado por dominio')

    bd = defaultdict(list)

    for uid, entry in zmbGetAllAccounts():
        email        = entry['zimbraMailDeliveryAddress'][0]
        user, domain = email.split('@')
        data         = {k:v[0] for k,v in entry.items()}
        bd[domain].append(data)

    log.info('Banco de dados criado')
    log.debug(str(bd))

    return bd

# * * *
# Criar array/lista com os contadores para o sumario
# Depois e salvo em um arquivo txt formatado igual ao 'domain summary'
# gerado pelo '/opt/zimbra/bin/zmaccts'
# * * *

def createSummaryArray():
    log.info('-' * TRUNCATE)
    log.info('Criando banco de dados com contadores para o sumario')

    summary = []

    for domain, domaindata in bd.items():
        s = dict(domain=domain, active=0, closed=0, locked=0, maintenance=0, total=0, admin=0, delegatedadmin=0, system=0, pending=0)

        for userdata in domaindata:
            if 'zimbraIsAdminAccount' in userdata:
                if userdata['zimbraIsAdminAccount'].upper() == 'TRUE':
                    s['admin'] += 1
                    continue
            if 'zimbraIsDelegatedAdminAccount' in userdata:
                if userdata['zimbraIsDelegatedAdminAccount'].upper() == 'TRUE':
                    s['delegatedadmin'] += 1
                    continue
            if 'zimbraIsSystemAccount' in userdata:
                s['system'] += 1
                continue
            zimbraAccountStatus = userdata['zimbraAccountStatus']
            s[zimbraAccountStatus] += 1
            s['total'] += 1
            s['*'] = '*'

        summary.append(s)

    log.info('')
    log.info('Banco de dados criado')
    log.debug(str(summary))

    return summary

# * * *
# Pretty print a list of dictionaries (myDict) as a dynamically sized table.
# If column names (colList) aren't specified, they will show in random order.
# * * *

def printTable(myDict, colList=None, fileName=None):
    if not colList: colList = list(myDict[0].keys() if myDict else [])
    myList = []
    for item in myDict: myList.append([str(item[col] if item[col] is not None else '') for col in colList])
    myList = sorted(myList)
    myList.insert(0, colList) # header
    colSize = [max(map(len,col)) for col in zip(*myList)]
    formatStr = ' | '.join(["{{:<{}}}".format(i) for i in colSize])
    myList.insert(1, ['-' * i for i in colSize]) # Seperating line
    if fileName:
        with open(fileName, 'wb') as f:
            for item in myList: f.write( formatStr.format(*item) + '\n' )
    else:
        for item in myList: print(formatStr.format(*item))

# * * *
# Send text file as email body
# * * *

def sendMail(textfile, send=False):
    import smtplib
    from email.mime.text import MIMEText

    with open(textfile, 'rb') as fp:
        msg = MIMEText(fp.read())

    msg['Subject'] = 'Zimbra Domain Summary'
    msg['From']    = SCRIPTNAME + '@' + FQDN
    msg['To']      = 'lista@dominio.com.br'

    # postar sem autenticacao com starttls
    s = smtplib.SMTP('smtp.dominio.com.br', 587)
    s.starttls()
    if send:
        s.sendmail(msg['From'], msg['To'], msg.as_string())
    s.quit()

    # postar com autenticacao na porta segura
    #s = smtplib.SMTP_SSL('mobile.dominio.com.br', 465)
    #s.login('testador@dominio.com.br', 'senha')
    #if send:
    #    s.sendmail(msg['From'], msg['To'], msg.as_string())
    #s.quit()

    return str(msg)

# ------------------------------------------------------------------------------
# __main__
# ------------------------------------------------------------------------------
# Wrapping the execution in __main__ makes it safe to be imported
# If the module is the main program it will execute the functions
# If the module is imported by another, only load the functions
# ------------------------------------------------------------------------------

if __name__ == '__main__':

    # --------------------------------------------------------------------------
    # Argumentos
    # --------------------------------------------------------------------------

    import argparse

    arg_parser = argparse.ArgumentParser(
        description     = 'Relatorio de aproriacao do Zimbra',
        epilog          = 'Arquivos de saida: /tmp/<domain>.csv',
        formatter_class = lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=999)
    )

    arg_parser.add_argument('-v', '--version', action='version', version=__version__)

    argslist = [
        ('-l', '--loglevel', '(default: %(default)s) Alterar verbosidade', dict(
            type=str.upper, const='logging.', default='WARN', nargs='?')
        ),
        ('-s', '--sendmail', '(default: %(default)s) Enviar resultado por email', dict(action='store_true')),
        ('-t', '--testmode', '(default: %(default)s) Ativar modo teste (rapido)', dict(action='store_true')),
    ]

    for argshort, arglong, desc, options in argslist:
        arg_parser.add_argument(argshort, arglong, help=desc, **options)

    args = arg_parser.parse_args()

    # --------------------------------------------------------------------------
    # Inicio
    # --------------------------------------------------------------------------

    # Ajustar nivel de verbosidade do log, caso o usuario tenha passado algum
    log.setLevel(args.loglevel)

    # Pesquisar ldap e criar banco de dados indexado por dominio
    bd = createDomainDatabase()

    # Array com contadores do sumario
    summary = createSummaryArray()

    # Arquivo em que o sumario sera gravado
    summaryfile = '/tmp/domainsummary.txt'

    log.info('-' * TRUNCATE)
    log.info('Salvando arquivo de sumario em %s', summaryfile)
    log.debug(str(summary))

    # Gerar tabela com o conteudo do sumario
    printTable(
        summary,
        ['domain', 'active', 'closed', 'locked', 'maintenance', 'total', '*', 'admin', 'delegatedadmin', 'system', 'pending'],
        summaryfile
    )

    # Imprimir resultado. Envia-lo por email?
    log.info('Enviar sumario por email: %s', args.sendmail)
    msg = sendMail(summaryfile, args.sendmail)
    print ('\n'), msg

    # --------------------------------------------------------------------------
    # Fim
    # --------------------------------------------------------------------------

    end_time_script = timer() - start_time_script

    log.info('-' * TRUNCATE)
    log.info('Script finalizado em %s segundos', round(end_time_script,2))
