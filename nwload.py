#! /usr/bin/env python

from __future__ import print_function

import shlex, argparse, cmd
import logging
import random, time, os, sys
import multiprocessing
import signal

################################################################

class Conversions(object):
    """Support conversions of storage units with SI-ish units."""
    
    import re as _re

    _spec = _re.compile('''^\s*(?P<digits>[0-9]+)(?P<frac>\.[0-9]*)?\s*(?P<spec>.*)\s*$''')

    # Not quite SI units...  We allow suffix of B for Bytes.
    #
    # We use lowercase for powers of 10, uppercase for powers of 1024,
    # even when there is ambiguity in SI units or no lowercase form.
    #
    _mult = {
        'k': 1000,
        'kB': 1000,
        'K': 1024,
        'KB': 1024,
        'KiB': 1024,
        'm': 1000 * 1000,
        'mB': 1000 * 1000,
        'M': 1024 * 1024,
        'MB': 1024 * 1024,
        'MiB': 1024 * 1024,
        'g': 1000 * 1000 * 1000,
        'gB': 1000 * 1000 * 1000,
        'G': 1024 * 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'GiB': 1024 * 1024 * 1024,
        't': 1000 * 1000 * 1000 * 1000,
        'tB': 1000 * 1000 * 1000 * 1000,
        'T': 1024 * 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024,
        'TiB': 1024 * 1024 * 1024 * 1024,
        'p': 1000 * 1000 * 1000 * 1000 * 1000,
        'pB': 1000 * 1000 * 1000 * 1000 * 1000,
        'P': 1024 * 1024 * 1024 * 1024 * 1024,
        'PB': 1024 * 1024 * 1024 * 1024 * 1024,
        'PiB': 1024 * 1024 * 1024 * 1024 * 1024,
        'e': 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'eB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'E': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'EB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'EiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        }

    _div = (
        (_mult['KiB'],            1, 'B'),
        (_mult['MiB'], _mult['KiB'], 'KiB'),
        (_mult['GiB'], _mult['MiB'], 'MiB'),
        (_mult['TiB'], _mult['GiB'], 'GiB'),
        (_mult['PiB'], _mult['TiB'], 'TiB'),
        (_mult['EiB'], _mult['PiB'], 'PiB'),
        (        None, _mult['EiB'], 'EiB'))
        

    @classmethod
    def datasize2int(cls,s):
        """Convert a data size specification into a long integer."""
        m = cls._spec.match(s)
        if m is not None:
            digits = m.group('digits')
            frac = m.group('frac')
            if frac is not None:
                i = float(digits+frac)
            else:
                i = long(digits)
            ds = m.group('spec')
            if ds == '':
                return i
            else:
                try:
                    return long(i * cls._mult[ds])
                except:
                    pass
        raise DataSizeError(s)

    @classmethod
    def int2datasize(cls,v):
        """Convert an integer into a data size specification string."""
        for b,d,ds in cls._div:
            if b is None or v < b:
                return str(v/d) + ds

class DataSizeError(Exception):
    def __init__(self, ds):
        self._ds = ds

    def __repr__(self):
        return repr(self._ds)

################################################################



class NetworkTester(cmd.Cmd):
    """Command interpreter for the network workload tester.

    This uses the Python cmd module to parse commands.  We subvert it
    a bit to work better from scripts, but prefer it to shlex since it
    allows us to (potentially) provide CLI features such as command
    completion.

    The argparse module is used to parse arguments to individual
    commands, as well as subcommands.  It too is somewhat subverted to
    work better with scripts."""

    def __init__(self, cmdfile, outfile):
        # Create parsers

        ap = self.ap_parse_server = argparse.ArgumentParser(
            prog='server',
            description='Define a server'
        )

        ap = self.ap_parse_client =  argparse.ArgumentParser(
            prog='client',
            description='Define a client'
        )
        
        self.ap_parse_test = argparse.ArgumentParser(
            prog='test',
            description='Test the network'
        )
      
        self._cmd = ''
        cmd.Cmd.__init__(self, stdin=cmdfile)
        if cmdfile != sys.stdin:
            self.use_rawinput = False
            self.prompt = ''
        else:
            self.prompt = 'nwl: '
        #
        self.servers = {}
        self.clients = {}
        self.outfile = outfile

    def emptyline(self):
        return False

    def precmd(self, line):
        # Help deal with continued lines
        if line == '' or line[-1] != '\\':
            # Command is finished here
            res = self._cmd + line
            self._cmd = ''
            lres = res.lstrip()
            if lres != '' and lres[0] == '#':
                return ''
            return res
        if line != '':
            # Continued command (ends with backslash)
            self._cmd = self._cmd + line[:-1]
            return ''

    def postcmd(self, stop, line):
        # Handle prompting for continued lines
        if self.use_rawinput:
            if self._cmd == '':
                self.prompt = 'nwl: '
            else:
                self.prompt = '____ '
        return stop

    # "exit"

    def do_exit(self, cs):
        return True
    do_EOF = do_exit

    def help_exit(self):
        print ('usage: exit')
        print ('')
        print ('Exit from nwl')
    help_EOF = help_exit

    # "server"

    def do_server(self, cs):
        L = shlex.split(cs)
        try:
            n = self.ap_parse_server.parse_args(L)
        except SystemExit as e:
            return False
        except:
            return True
        n.func(n)
        return False

    def help_server(self):
        self.ap_parse_server.print_help()

    # "test"

    def do_test(self, cs):
        L = shlex.split(cs)
        try:
            n = self.ap_parse_test.parse_args(L)
        except SystemExit as e:
            return False
        except:
            return True
        r = RunTest(n, self.targets, self.tests, self.outfile)
        r.run_test()
        return False

    def help_test(self):
        self.ap_parse_test.print_help()


def main():

    # Set up logging.
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

    # Define command line parser.
    p = argparse.ArgumentParser(description='Test network performance.')
    p.add_argument('cmdfile', type=argparse.FileType('r'),
                   nargs='?', default='-')
    p.add_argument('--output', type=argparse.FileType('w'), default='-',
                   help='File for output of test results')
    n = p.parse_args()
    t = NetworkTester(n.cmdfile, n.output)
    t.cmdloop()
    sys.exit(0)

if __name__ == '__main__':
    main()
