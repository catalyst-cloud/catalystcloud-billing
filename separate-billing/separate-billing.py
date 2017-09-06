#!/usr/bin/env python

import argparse
import collections
import datetime
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
import prettytable

from oslo_utils import encodeutils
from oslo_utils import importutils
from oslo_log import log as logging
from oslo_config import cfg
from retrying import retry

from keystoneclient.v2_0 import client as keystone_client
from distilclient import client as distil_client


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
DOMAIN = "billing"


def prepare_log():
    logging.register_options(CONF)
    extra_log_level_defaults = [
        'dogpile=INFO',
        'routes=INFO'
        ]

    logging.set_defaults(
        default_log_levels=logging.get_default_log_levels() +
        extra_log_level_defaults)

    logging.setup(CONF, DOMAIN)


def arg(*args, **kwargs):
    def _decorator(func):
        func.__dict__.setdefault('arguments', []).insert(0, (args, kwargs))
        return func
    return _decorator


class CatalystCloudShell(object):

    def get_base_parser(self):
            parser = argparse.ArgumentParser(
                prog='separate-billing',
                description='Script for Catalyst Cloud to check the total'
                            ' usage for this month.',
                add_help=False,
            )

            # Global arguments
            parser.add_argument('-h', '--help',
                                action='store_true',
                                help=argparse.SUPPRESS,
                                )

            parser.add_argument('-a', '--os-auth-url', metavar='OS_AUTH_URL',
                                type=str, required=False, dest='OS_AUTH_URL',
                                default=os.environ.get('OS_AUTH_URL', None),
                                help='Keystone Authentication URL')

            parser.add_argument('-u', '--os-username', metavar='OS_USERNAME',
                                type=str, required=False, dest='OS_USERNAME',
                                default=os.environ.get('OS_USERNAME', None),
                                help='Username for authentication')

            parser.add_argument('-p', '--os-password', metavar='OS_PASSWORD',
                                type=str, required=False, dest='OS_PASSWORD',
                                default=os.environ.get('OS_PASSWORD', None),
                                help='Password for authentication')

            parser.add_argument('-t', '--os-tenant-name',
                                metavar='OS_TENANT_NAME',
                                type=str, required=False,
                                dest='OS_TENANT_NAME',
                                default=os.environ.get('OS_TENANT_NAME', None),
                                help='Tenant name for authentication')

            parser.add_argument('-r', '--os-region-name',
                                metavar='OS_REGION_NAME',
                                type=str, required=False,
                                dest='OS_REGION_NAME',
                                default=os.environ.get('OS_REGION_NAME', None),
                                help='Region for authentication')

            parser.add_argument('-c', '--os-cacert', metavar='OS_CACERT',
                                dest='OS_CACERT',
                                default=os.environ.get('OS_CACERT'),
                                help='Path of CA TLS certificate(s) used to '
                                'verify the remote server\'s certificate. '
                                'Without this option glance looks for the '
                                'default system CA certificates.')

            parser.add_argument('-k', '--insecure',
                                default=False,
                                action='store_true', dest='OS_INSECURE',
                                help='Explicitly allow script to perform '
                                '\"insecure SSL\" (https) requests. '
                                'The server\'s certificate will not be '
                                'verified against any certificate authorities.'
                                ' This option should be used with caution.')

            return parser

    def get_subcommand_parser(self):
        parser = self.get_base_parser()
        self.subcommands = {}
        subparsers = parser.add_subparsers(metavar='<subcommand>')
        submodule = importutils.import_module('separate-billing')
        self._find_actions(subparsers, submodule)
        self._find_actions(subparsers, self)
        return parser

    def _find_actions(self, subparsers, actions_module):
        for attr in (a for a in dir(actions_module) if a.startswith('do_')):
            command = attr[3:].replace('_', '-')
            callback = getattr(actions_module, attr)
            desc = callback.__doc__ or ''
            help = desc.strip().split('\n')[0]
            arguments = getattr(callback, 'arguments', [])

            subparser = subparsers.add_parser(command,
                                              help=help,
                                              description=desc,
                                              add_help=False,
                                              formatter_class=HelpFormatter
                                              )
            subparser.add_argument('-h', '--help',
                                   action='help',
                                   help=argparse.SUPPRESS,
                                   )
            self.subcommands[command] = subparser
            for (args, kwargs) in arguments:
                subparser.add_argument(*args, **kwargs)
            subparser.set_defaults(func=callback)

    @arg('command', metavar='<subcommand>', nargs='?',
         help='Display help for <subcommand>.')
    def do_help(self, args):
        """Display help about this program or one of its subcommands."""
        if getattr(args, 'command', None):
            if args.command in self.subcommands:
                self.subcommands[args.command].print_help()
            else:
                raise Exception("'%s' is not a valid subcommand" %
                                args.command)
        else:
            self.parser.print_help()

    def init_client(self, args):
        if not args.OS_AUTH_URL:
            print("Please source your rc file first.")
            sys.exit(1)
        try:
            from keystoneauth1.identity import generic
            from keystoneauth1 import session

            auth = generic.Password(auth_url=args.OS_AUTH_URL,
                                    username=args.OS_USERNAME,
                                    password=args.OS_PASSWORD,
                                    project_name=args.OS_TENANT_NAME,
                                    )
            sess = session.Session(auth=auth)

            keystone = keystone_client.Client(session=sess)
            self.keystone = keystone
        except Exception as e:
            raise e

        try:
            # NOTE(flwang): It's OK only talk to WLG region to get the data
            region = 'nz_wlg_2'
            distil_url = "https://api.cloud.catalyst.net.nz:9999"
            distil = distil_client.Client(version='2',
                                          distil_url=distil_url,
                                          session=sess, region_name=region)
            
            self.distil = distil
        except Exception as e:
            raise e

    def main(self, argv):
        parser = self.get_base_parser()
        (options, args) = parser.parse_known_args(argv)

        subcommand_parser = self.get_subcommand_parser()
        self.parser = subcommand_parser

        if options.help or not argv:
            self.do_help(options)
            return 0

        args = subcommand_parser.parse_args(argv)
        if args.func == self.do_help:
            self.do_help(args)
            return 0

        try:
            args.func(self, args)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                      limit=2, file=sys.stdout)


class HelpFormatter(argparse.HelpFormatter):
    def start_section(self, heading):
        # Title-case the headings
        heading = '%s%s' % (heading[0].upper(), heading[1:])
        super(HelpFormatter, self).start_section(heading)

@arg('--prefix', metavar='CUSTOMER_PREFIX', dest='CUSTOMER_PREFIX',
     required=True,
     help='A prefix for a particular customer to get the cost.')
def do_show(shell, args):
    """ Get separate billing based on the given customer prefix.
    """
    shell.init_client(args)
    end = datetime.datetime.today()

    # NOTE(flwang): Cover at least 2 months to make sure there is an invoices
    year = end.year - 1 if end.month == 1 else end.year
    month = 11 if end.month == 1 else end.month - 2
    start = datetime.datetime(end.year, end.month - 2, 1)
    invoices = get_invoices(shell, start, end)

    get_customer_cost(invoices, args.CUSTOMER_PREFIX)


@retry(stop_max_attempt_number=5, wait_fixed=1000)
def get_invoices(shell, start, end, project_id=""):
    return shell.distil.invoices.list(start, end,
                                      detailed=True,
                                      project_id=project_id)


def get_customer_cost(invoices, customer_prefix):
    all_invoices = collections.OrderedDict(sorted(invoices["invoices"].items(),
                                           key=lambda t: t[0]))

    if len(all_invoices) == 0:
        LOG.error("Cannot find any invoice for the last 2 months.")
        return

    # TODO(flwang): As a reference, we only get the latest invoice, it's easy
    # to get the others by the date.
    month_invoice = all_invoices.values()[-1]["details"]
    total_cost = 0
    details = []
    for category in month_invoice.keys():
        for product in month_invoice[category]["breakdown"].keys():
            for resource in month_invoice[category]["breakdown"][product]:
                if resource["resource_name"].startswith(customer_prefix):
                    details.append(resource)
                    total_cost += resource["cost"]

    print_list(details, ["resource_name", "rate", "quantity", "unit", "cost"])
    print("Total cost of customer [%s] for the month of [%s] is : $%.2f" %
          (customer_prefix, all_invoices.keys()[-1], total_cost))


def print_list(objs, fields, formatters={}):
    pt = prettytable.PrettyTable([f for f in fields], caching=False)
    pt.align = 'l'

    for o in objs:
        row = []
        for field in fields:
            if field in formatters:
                row.append(formatters[field](o))
            else:
                field_name = field.lower().replace(' ', '_')
                if type(o) == dict and field in o:
                    data = o[field_name]
                else:
                    data = getattr(o, field_name, None) or ''
                row.append(data)
        pt.add_row(row)

    print(encodeutils.safe_encode(pt.get_string()))


if __name__ == '__main__':
    prepare_log()

    try:
        CatalystCloudShell().main(sys.argv[1:])
    except KeyboardInterrupt:
        print("Terminating...")
        sys.exit(1)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback,
                                  limit=2, file=sys.stdout)
