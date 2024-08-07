import hmac
import json

import time

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class PublicBybitWebSocket(KuegiWebsocket):
    def __init__(self, publicURL, logger, mainSocket,symbol, minutesPerBar):
        self.data = {}
        self.symbol= symbol
        self.minutesPerBar= minutesPerBar
        self.initial_subscribe_done = False
        super().__init__([publicURL],  None, None, logger, None)
        self.mainSocket= mainSocket

    def on_message(self, message):
        self.mainSocket.on_message(message)

    def on_pong(self):
        self.ws.send(json.dumps({"op": "ping"}))

    def subscribe(self,topic:str, ws):
        param = dict(
            op='subscribe',
            args=[topic]
        )
        ws.send(json.dumps(param))
        if topic not in self.mainSocket.data:
            self.mainSocket.data[topic] = []

    def subscribe_realtime_data(self):
        subbarsIntervall = '1' if self.minutesPerBar <= 60 else '60'
        self.subscribe('kline.' + subbarsIntervall + '.' + self.symbol,self.ws)
        self.subscribe("tickers."+self.symbol,self.ws)
        self.initial_subscribe_done = True


class BybitWebsocket(KuegiWebsocket):
    # User can ues MAX_DATA_CAPACITY to control memory usage.
    MAX_DATA_CAPACITY = 200
    PRIVATE_TOPIC = ['position', 'execution', 'order']

    def __init__(self, wsURLs, api_key, api_secret, logger, callback,symbol, minutesPerBar, category):
        self.data = {}
        self.symbol = symbol
        self.minutesPerBar = minutesPerBar
        super().__init__([wsURLs[0]], api_key, api_secret, logger, callback)
        self.public = PublicBybitWebSocket(wsURLs[1], logger, self,symbol, minutesPerBar) #no auth for public

    def on_pong(self):
        self.ws.send(json.dumps({"op": "ping"}))

    def generate_signature(self, expires):
        """Generate a request signature."""
        _val = 'GET/realtime' + expires
        return str(hmac.new(bytes(self.api_secret, "utf-8"), bytes(_val, "utf-8"), digestmod="sha256").hexdigest())

    def exit(self):
        if self.public:
            self.public.exit()
        super().exit()

    def do_auth(self):
        expires = str(int(round(time.time()) + 5)) + "000"
        signature = self.generate_signature(expires)
        auth = {"op": "auth", "args": [self.api_key, expires, signature]}
        self.ws.send(json.dumps(auth))

    def subscribe_realtime_data(self):
        self.subscribe_order()
        self.subscribe_execution()
        self.subscribe_position()
        self.subscribe_wallet_data()
        if not self.public.initial_subscribe_done:
            self.public.subscribe_realtime_data()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        message = json.loads(message)
        if 'success' in message:
            if message["success"]:
                if 'op' in message and message["op"] == 'auth':
                    self.auth = True
                    self.logger.info("Authentication success.")
                if 'ret_msg' in message and message["ret_msg"] == 'pong':
                    pass
            else:
                self.logger.error("Error in socket: " + str(message))

        if 'topic' in message:
            self.data[message["topic"]].append(message["data"])
            if len(self.data[message["topic"]]) > BybitWebsocket.MAX_DATA_CAPACITY:
                self.data[message["topic"]] = self.data[message["topic"]][BybitWebsocket.MAX_DATA_CAPACITY // 2:]
            if self.callback is not None:
                self.callback(message['topic'])

    def subscribe(self, topic: str, ws):
        param = dict(
            op='subscribe',
            args=[topic]
        )
        ws.send(json.dumps(param))
        if topic not in self.data:
            self.data[topic] = []

    # privates -------------------

    def subscribe_wallet_data(self):
        self.subscribe("wallet", self.ws)

    def subscribe_position(self):
        self.subscribe("position", self.ws)

    def subscribe_execution(self):
        self.subscribe("execution", self.ws)

    def subscribe_order(self):
        self.subscribe("order", self.ws)

    def get_data(self, topic):
        if topic not in self.data:
            self.logger.info(" The topic %s is not subscribed." % topic)
            return []
        if topic.split('.')[0] in BybitWebsocket.PRIVATE_TOPIC and not self.auth:
            self.logger.info("Authentication failed. Please check your api_key and api_secret. Topic: %s" % topic)
            return []
        else:
            if len(self.data[topic]) == 0:
                return []
            return self.data[topic].pop()
