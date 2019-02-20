#!/usr/bin/env python3

# stdlib
import sys, os
import json
import _pickle as pickle
import logging
import pdb

# Third party lib
from twisted.internet import reactor, protocol, threads
from twisted.internet.defer import DeferredQueue, inlineCallbacks

# Internal lib
from serverSideAnalysis import ServerTalker, decode
from settings import Settings, Commands, Options, QCOptions, PCAOptions, PCAFilterNames

# TODO: graceful exit

NUM = 8

HELP_STRING = "HELP MEEEEE" #TODO


class Hub(protocol.Protocol):
    def __init__(self, factory, clients, nclients):
        self.clients = clients
        self.nclients = nclients
        self.factory = factory
        self.dispatcher = ServerTalker(NUM, self,
                                       local_scratch)
        self.cache = None
        self.setup_logger()
        self.queue = message_queue

    def setup_logger(self):
        logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
        self.rootLogger = logging.getLogger()
        fileHandler = logging.FileHandler("{0}/{1}.log".format(os.getcwd(), "HYDRA_server_logger"))
        fileHandler.setFormatter(logFormatter)
        self.rootLogger.addHandler(fileHandler)

        consoleHandler = logging.StreamHandler(sys.stdout)
        consoleHandler.setFormatter(logFormatter)
        self.rootLogger.addHandler(consoleHandler)
        self.rootLogger.setLevel(logging.INFO)

    def get_response(self, options):
        options = [val.upper() for val in options]
        waiting_for_command = True
        while waiting_for_command:
            val = input(
                "Looks like everyone is here. Type the stage you want to proceed with? Options: " + 
                ", ".join(options)+ ": \n")

            self.rootLogger.info("Asking for input...")
            val = val.upper()
            if val in options:
                waiting_for_command = False
        if val == Commands.EXIT:
            self.tearDown()
        elif val == Commands.HELP:
            print(HELP_STRING)
        elif val == Commands.INIT:
            self.run_init()
        elif val == Commands.QC:
            self.run_QC()
        elif val == Commands.PCA:
            self.run_pca()
        elif val == Commands.ASSO:
            self.run_logistic_regression()
        self.rootLogger.info(val)
        self.wait_for_and_process_next_message()


    def run_QC(self):
        task = "QC"
        while True:
            val = input(
                """Indicate the filters and corresponding values(e.g. hwe 1e-5). Available filters are HWE, MAF, MPS(Missing Per sample), MPN(Missing per snp), snp(rsid) (MPS not implemented yet): \n""")
            val = val.upper()
            vals = val.split()
            if vals[0] == Commands.EXIT:
                self.tearDown()
                return
            elif len(vals) < 2:
                print("Specify `filter value` pairs? OK? OOOK?")
            else:
                subtasks = [v.upper() for v in vals[::2]]
                vals = vals[1::2]
                # Sanity checks:
                if not len(set(subtasks)) == len(subtasks):
                    print("You can only use the same filter once.")
                    continue
                # if not set(subtasks).issubset(QC_OPTIONS):
                if not set(subtasks).issubset(QCOptions.all_options):
                    print("Wrong keywords")
                    continue
                break
        self.rootLogger.info("QC input: {}".format(vals))
        vals = [float(v) for v in vals]
        outMessage = pickle.dumps({"TASK": task, "SUBTASK": "FILTERING", "FILTERS": subtasks, "VALS": vals})
        self.message(outMessage)
        inMessage = {"TASK": "QC", "SUBTASK": subtasks, "VALS": vals}
        message_queue.put(inMessage)
        self.get_options()

    def run_logistic_regression(self):
        while True:
            val = input("""Specify number of PCs followed by other covariates (Comma separated): """)
            vals = val.split(',')
            try:
                vals[0] = int(vals[0])
                if len(vals) != 1:  # TODO
                    print("We only support PCs for now")
                else:
                    break
            except NameError:
                continue
        self.rootLogger.info("Regression input: ", vals)
        out_message = pickle.dumps({"TASK": Commands.ASSO, "SUBTASK": "INIT", "VARS": vals, 
          "Threshold":2*(vals[0] + 2.0)/self.dispatcher.store.attrs["N"]})
        self.message(out_message)

    def get_options(self):
        message_queue.put("GET OPTIONS")

    def run_init(self):
        message = pickle.dumps({"TASK": "INIT", "SUBTASK": "STORE"})
        self.message(message)

    def run_pca(self):
        task = "PCA"
        while True:
            val = input(
                """Specify filters for PCA pre-processing: (OPTIONS: HWE, MAF,
                MPS, as before as well as LD. e.g. maf 0.1 LD 50: """)
            vals = val.split()
            if val == Commands.EXIT:
                sys.exit()
            if len(vals) < 2 and vals[0] != PCAFilterNames.PCA_NONE:
                print("Specify `filter value` pairs. PLEASEEEE!! REEEE!")
            else:
                subtasks = [v.upper() for v in vals[::2]]
                vals = vals[1::2]
                assert len(set(subtasks)) == len(subtasks)
                assert set(subtasks).issubset(PCAOptions.all_options)
                break
        self.rootLogger.info("PCA input: ", vals)
        vals = [float(v) for v in vals]
#        outMessage = pickle.dumps({"TASK": task, "SUBTASK": "FILTERING", "FILTERS": subtasks, "VALS": vals})
        outMessage = pickle.dumps({"TASK": task, "SUBTASK": "fake"})
        self.message(outMessage)
#        inMessage = {"TASK": "PCA", "SUBTASK": "FILTERS", "FILTERS": subtasks, "VALS": vals}
#        message_queue.put(inMessage)

    def connectionMade(self):
        print("connected to user", (self))
        if len(self.clients) < self.nclients:
            self.factory.clients.append(self)
        else:
            self.factory.clients[self.nclients] = self
        if len(self.clients) == NUM:
            val = self.get_response(Commands.all_commands)

    def wait_for_and_process_next_message(self):
        reactor.callLater(0, self._wait_for_and_process_next_message)

    @inlineCallbacks
    def _wait_for_and_process_next_message(self):
        message = yield message_queue.get()
        if message == "GET OPTIONS":
            self.get_response(Commands.all_commands)
        else:
            yield threads.deferToThread(self.dispatcher.dispatch, message)
            self.wait_for_and_process_next_message()

    def message(self, command):
        reactor.callFromThread(self._message, command)

    def _message(self, command):
        for c in self.factory.clients:
            c.transport.write(command)

    def tearDown(self):
        reactor.stop()
        for c in self.factory.clients:
            c.connectionLost("Exiting")
        return

    def connectionLost(self, reason):  # TODO
        self.nclients -= 1

    def dataReceived(self, data):
        if len(self.clients) == NUM:
            tryDecoding = False
            if data.endswith(Settings.PICKLE_STOP):
                data = data[:-13]
                tryDecoding = True
            if self.cache is not None:
                data = self.cache + data
            if tryDecoding:
                try:
                    print(sys.getsizeof(data))
                    pdb.set_trace()
                    message = decode(data)
                    print("finished decoding")
                    message_queue.put(message)
                    self.cache = None
                except pickle.UnpicklingError as e:
                    self.cache = data

class PauseTransport(protocol.Protocol):
    def makeConnection(self, transport):
        transport.pauseProducing()


class HubFactory(protocol.Factory):
    def __init__(self, num):
        self.clients = set([])
        self.nclients = 0
        self.totConnections = num

    def buildProtocol(self, addr):
        print(self.nclients)
        if self.nclients < self.totConnections:
            self.nclients += 1
            return Hub(self, self.clients, self.nclients)
        protocol = PauseTransport()
        protocol.factory = self
        return protocol

if __name__== "__main__":
    PORT = 9000
    if len(sys.argv) >= 2:
        local_scratch = sys.argv[1]
        if len(sys.argv) == 3:
            PORT = int(sys.argv[2])
    else:
        local_scratch = Settings.local_scratch
    print('Starting server...')
    factory = HubFactory(NUM)
    reactor.listenTCP(PORT, factory)
    print(f'Server listening on port {PORT}')
    factory.clients = []
    message_queue = DeferredQueue()
    reactor.run()
