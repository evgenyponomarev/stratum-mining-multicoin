from service import MiningService
from subscription import MiningSubscription
from twisted.internet import defer
from twisted.internet.error import ConnectionRefusedError
import time
import simplejson as json
from twisted.internet import reactor
import threading
from mining.work_log_pruner import WorkLogPruner

import lib.settings as settings

# Get logging online as soon as possible
import lib.logger
log = lib.logger.get_logger('mining')


@defer.inlineCallbacks
def setup(on_startup):
    '''Setup mining service internal environment.
    You should not need to change this. If you
    want to use another Worker manager or Share manager,
    you should set proper reference to Interfaces class
    *before* you call setup() in the launcher script.'''

    from interfaces import Interfaces

    from lib.bitcoin_rpc_manager import BitcoinRPCManager

    bitcoin_rpc = BitcoinRPCManager()
    
    # Check litecoind
    #         Check we can connect (sleep)
    # Check the results:
    #         - getblocktemplate is avalible        (Die if not)
    #         - we are not still downloading the blockchain        (Sleep)
    log.info("Connecting to all litecoind...")
    for (wallet, connSettings) in settings.COINDAEMON_WALLETS.items():
        wallet_connect(wallet, bitcoin_rpc)


    yield 1
    on_startup.callback(True)
    log.info("MINING SERVICE IS READY")


@defer.inlineCallbacks
def wallet_connect(wallet, bitcoin_rpc):
    log.debug("IM HERE")

    from interfaces import Interfaces

    from lib.block_updater import BlockUpdater
    from lib.template_registry import TemplateRegistry
    from lib.block_template import BlockTemplate
    from lib.coinbaser import SimpleCoinbaser

    failure = 0
    while True:
        try:
            result = (yield bitcoin_rpc.getblocktemplate(wallet))
            if isinstance(result, dict):
                # litecoind implements version 1 of getblocktemplate
                if result['version'] >= 1:
                    result = (yield bitcoin_rpc.getinfo(wallet))
                    if isinstance(result, dict):
                        if 'stake' in result and settings.COINDAEMON_Reward == 'POS':
                            log.info("CoinD looks to be a POS Coin, Config for POS looks correct")
                            break
                        elif 'stake' not in result and settings.COINDAEMON_Reward == 'POW':
                            log.info("CoinD looks to be a POW Coin, Config looks to be correct")
                            break
                        else:
                            log.error("Wrong Algo Selected for %s, Switch to appropriate POS/POW in config.py!" % wallet)
                            #reactor.stop()
                            failure = 1
                            break

                else:
                    log.error("Block Version mismatch: %s" % result['version'])

        except ConnectionRefusedError, e:
            log.error("Connection refused while trying to connect to the %s (are your COIND_* settings correct?)" % wallet)
            #reactor.stop()
            failure = 1
            break

        except Exception, e:
            if isinstance(e[2], str):
                try:
                    if isinstance(json.loads(e[2])['error']['message'], str):
                        error = json.loads(e[2])['error']['message']
                    if error == "Method not found":
                        log.error("CoinD does not support getblocktemplate!!! (time to upgrade.)")
                        #reactor.stop()
                        failure = 1
                        break
                    elif "downloading blocks" in error:
                        log.error("CoinD downloading blockchain... will check back in 30 sec")
                        #time.sleep(29)
                        failure = 1
                        break
                    else:
                        log.error("Coind Error: %s", error)
                except ValueError:
                    log.error("Failed Connect(HTTP 500 or Invalid JSON), Check Username and Password!")
                    #reactor.stop()
                    failure = 1
                    break
        time.sleep(1)  # If we didn't get a result or the connect failed

    if(failure == 1):
        log.error("Problems with Coind %s, retry in 30 sec" % wallet)
        yield sleep(29)
        wallet_connect(wallet, bitcoin_rpc)

    log.info('Connected to the coind - Begining to load Address and Module Checks!')

    # Start the coinbaser
    coinbaser = SimpleCoinbaser(bitcoin_rpc, wallet)
    log.info('Starting registry')
    (yield coinbaser.on_load)

    log.info('Starting registry')

    mining_subscription = MiningSubscription()
    mining_subscription.wallet = wallet

    registry = TemplateRegistry(wallet,
                                BlockTemplate,
                                coinbaser,
                                bitcoin_rpc,
                                getattr(settings, 'INSTANCE_ID'),
                                mining_subscription.on_template,
                                Interfaces.share_manager.on_network_block)

    log.info('Set template registry for %s' % wallet)

    # Template registry is the main interface between Stratum service
    # and pool core logic
    #Interfaces.set_template_registry(registry)
    Interfaces.add_template_registry(wallet, registry)

    log.info('Block updater')

    # Set up polling mechanism for detecting new block on the network
    # This is just failsafe solution when -blocknotify
    # mechanism is not working properly
    BlockUpdater(wallet, registry, bitcoin_rpc)

    log.info('Threading thread')

    prune_thr = threading.Thread(target=WorkLogPruner, args=(Interfaces.worker_manager.job_log,))
    prune_thr.daemon = True
    prune_thr.start()

    #on_startup.callback(True)


def sleep(seconds):
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, seconds)
    return d

