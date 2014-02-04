'''
    Implements simple interface to a coin daemon's RPC.
'''

import simplejson as json
from twisted.internet import defer

import settings

import time

import lib.logger

log = lib.logger.get_logger('bitcoin_rpc_manager')

from lib.bitcoin_rpc import BitcoinRPC


class BitcoinRPCManager(object):
    def __init__(self):
        log.debug("Got to Bitcoin RPC Manager")

        self.conns = {}
        self.curr_wallet = settings.COINDAEMON_WALLETS.keys()[0]
        self.curr_conn = 0
        for (wallet, connSettings) in settings.COINDAEMON_WALLETS.items():
            for (i, conn) in enumerate(connSettings['hosts']):
                print wallet + " " + str(i)
                self.conns[wallet] = []
                self.conns[wallet].append(BitcoinRPC(conn['host'], conn['port'], conn['user'], conn['password']))


            #       self.conns = {}
            #       self.conns[0] = BitcoinRPC(settings.COINDAEMON_TRUSTED_HOST,
            #                             settings.COINDAEMON_TRUSTED_PORT,
            #                            settings.COINDAEMON_TRUSTED_USER,
            #                             settings.COINDAEMON_TRUSTED_PASSWORD)
            #       self.curr_conn = 0
            #       for x in range (1, 99):
            #           if hasattr(settings, 'COINDAEMON_TRUSTED_HOST_' + str(x)) and hasattr(settings, 'COINDAEMON_TRUSTED_PORT_' + str(x)) and hasattr(settings, 'COINDAEMON_TRUSTED_USER_' + str(x)) and hasattr(settings, 'COINDAEMON_TRUSTED_PASSWORD_' + str(x)):
            #               self.conns[len(self.conns)] = BitcoinRPC(settings.__dict__['COINDAEMON_TRUSTED_HOST_' + str(x)],
            #                                                       settings.__dict__['COINDAEMON_TRUSTED_PORT_' + str(x)],
            #                                                       settings.__dict__['COINDAEMON_TRUSTED_USER_' + str(x)],
            #                                                       settings.__dict__['COINDAEMON_TRUSTED_PASSWORD_' + str(x)])

    def add_connection(self, wallet, host, port, user, password):
        # TODO: Some string sanity checks
        self.conns[wallet][len(self.conns[wallet])] = BitcoinRPC(host, port, user, password)

    def next_connection(self, wallet):
        time.sleep(1)
        if len(self.conns[self.curr_wallet]) <= 1:
            log.error("Problem with Pool %s 0 -- NO ALTERNATE POOLS!!!", wallet)
            time.sleep(4)
            return
        log.error("Problem with Pool %s %i Switching to Next!" % (wallet, self.curr_conn))
        self.curr_conn = self.curr_conn + 1
        if self.curr_conn >= len(self.conns[wallet]):
            self.curr_conn = 0

    @defer.inlineCallbacks
    def check_height(self, wallet):
        while True:
            try:
                resp = (yield self.conns[wallet][self.curr_conn]._call('getinfo', []))
                break
            except:
                log.error("Check Height -- Pool %s %i Down!" % (wallet, self.curr_conn))
                self.next_connection(wallet)
        curr_height = json.loads(resp)['result']['blocks']
        log.debug("Check Height -- Current Pool %s %i : %i" % (wallet, self.curr_conn, curr_height))
        for i, conn in enumerate(self.conns[wallet]):
            if i == self.curr_conn:
                continue

            try:
                resp = (yield self.conns[wallet][i]._call('getinfo', []))
            except:
                log.error("Check Height -- Pool %s %i Down!" % (wallet, i))
                continue

            height = json.loads(resp)['result']['blocks']
            log.debug("Check Height -- Pool %s %i : %i" % (wallet, i, height))
            if height > curr_height:
                self.curr_conn = i
        defer.returnValue(True)

    def _call_raw(self, wallet, data):
        while True:
            try:
                return self.conns[wallet][self.curr_conn]._call_raw(data)
            except:
                self.next_connection(wallet)

    def _call(self, wallet, method, params):
        while True:
            try:
                return self.conns[wallet][self.curr_conn]._call(method, params)
            except:
                self.next_connection(wallet)

    def submitblock(self, wallet, block_hex, hash_hex):
        while True:
            try:
                return self.conns[wallet][self.curr_conn].submitblock(block_hex, hash_hex)
            except:
                self.next_connection(wallet)

    def getinfo(self, wallet):
        while True:
            try:
                return self.conns[wallet][self.curr_conn].getinfo()
            except:
                self.next_connection(wallet)

    def getblocktemplate(self, wallet):
        while True:
            try:
                return self.conns[wallet][self.curr_conn].getblocktemplate()
            except:
                self.next_connection(wallet)

    def prevhash(self, wallet):
        self.check_height(wallet)
        while True:
            try:
                return self.conns[wallet][self.curr_conn].prevhash()
            except:
                self.next_connection(wallet)

    def validateaddress(self, wallet, address):
        while True:
            try:
                return self.conns[wallet][self.curr_conn].validateaddress(address)
            except:
                self.next_connection(wallet)

    def getdifficulty(self, wallet):
        while True:
            try:
                return self.conns[wallet][self.curr_conn].getdifficulty()
            except:
                self.next_connection(wallet)
