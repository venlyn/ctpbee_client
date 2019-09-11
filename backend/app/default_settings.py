import json
import os
import time
from json import JSONDecodeError
from datetime import datetime
from flask import make_response
from flask_socketio import SocketIO

from ctpbee import CtpbeeApi
from ctpbee.constant import LogData, AccountData, ContractData, BarData, OrderData, PositionData, TickData, SharedData, \
    TradeData
from app.model import db


class DefaultSettings(CtpbeeApi):

    def __init__(self, name, app, socket_io: SocketIO):
        super().__init__(name, app)
        self.io = socket_io
        ## 记录所有的bar
        self.global_bar = {}

        ## 记录每个合约是否载入状态
        self.local_status = {}

    def on_log(self, log: LogData):
        data = {
            "type": "log",
            "data": log
        }
        self.io.emit('log', data)

    def on_account(self, account: AccountData) -> None:
        data_list = []
        for k, v in account._to_dict().items():
            temp = {}
            temp['key'] = k
            temp['value'] = v
            data_list.append(temp)
        data = {
            "type": "account",
            "data": data_list
        }
        self.io.emit('account', data)

    def on_contract(self, contract: ContractData):
        pass

    def on_bar(self, bar: BarData) -> None:
        timestamp = round(bar.datetime.timestamp() * 1000)

        db[bar.local_symbol].insert(dict(timestamp=timestamp, open_price=bar.open_price, high_price=bar.high_price,
                                         low_price=bar.low_price, close_price=bar.close_price, volume=bar.volume))
        info = [timestamp, bar.open_price, bar.high_price, bar.low_price,
                bar.close_price, bar.volume]
        self.io.emit("bar", info)

    def on_order(self, order: OrderData) -> None:
        # 更新活跃报单
        active_orders = []
        for order in self.app.recorder.get_all_active_orders(order.local_symbol):
            active_orders.append(order._to_dict())
        data = {
            "type": "active_order",
            "data": active_orders
        }

        self.io.emit("active_order", data)
        orders = []
        for order in self.app.recorder.get_all_orders():
            orders.append(order._to_dict())
        data = {
            "type": "order",
            "data": orders
        }
        self.io.emit("order", data)

    def on_position(self, position: PositionData) -> None:
        data = {
            "type": "position",
            "data": self.app.recorder.get_all_positions()
        }
        self.io.emit("position", data)

    def on_tick(self, tick: TickData) -> None:
        self.local_status.setdefault(tick.local_symbol, False)
        self.global_bar.setdefault(tick.local_symbol, [])

        tick.datetime = str(tick.datetime)
        data = {
            "type": "tick",
            "data": tick._to_dict()
        }
        self.io.emit("tick", data)
        data = {
            "type": "position",
            "data": self.app.recorder.get_all_positions()
        }
        self.io.emit("position", data)
        if not self.local_status.get(tick.local_symbol):
            try:
                with open(f"{os.path.dirname(__file__)}/static/json/{tick.symbol}.json", "r") as f:
                    from json import load
                    st = True
                    try:
                        data = load(f)
                    except JSONDecodeError:
                        st = False
                    if data.get("data") is not None and st:
                        klines = data.get("data").get("lines")
                        assert type(klines) == list
                        if len(klines) != 0:
                            self.global_bar.get(tick.local_symbol).extend(klines)
            except FileNotFoundError:
                pass
            self.local_status[tick.local_symbol] = True
        with open(f"{os.path.dirname(__file__)}/static/json/{tick.symbol}.json", "w") as f:
            from json import dump
            update_result = {
                "success": True,
                "data": {
                    "lines": self.global_bar.get(tick.local_symbol),
                    "depths": {
                        "asks": [
                            [
                                tick.ask_price_1,
                                tick.ask_volume_1
                            ]
                        ],
                        "bids": [
                            [
                                tick.bid_price_1,
                                tick.bid_volume_1
                            ]
                        ]
                    }
                }
            }
            f.truncate(0)
            dump(update_result, f)

        self.io.emit("update_all", update_result)

    def on_shared(self, shared: SharedData) -> None:
        shared.datetime = str(shared.datetime)
        data = {
            "type": "shared",
            "data": shared._to_dict()
        }
        self.io.emit('shared', data)

    def on_trade(self, trade: TradeData) -> None:
        trades = []
        for trade in self.app.recorder.get_all_trades():
            trades.append(trade._to_dict())
        data = {
            "type": "trade",
            "data": trades
        }
        self.io.emit('trade', data)

    def on_init(self, init):
        pass


def true_response(msg='', data=''):
    res = {
        'success': True,
        'msg': msg,
        'data': data
    }
    return make_response(json.dumps(res))


def false_response(msg='', data=''):
    res = {
        'success': False,
        'msg': msg,
        'data': data
    }
    return make_response(json.dumps(res))


def true_return(msg='', data=''):
    return {
        'success': True,
        'msg': msg,
        'data': data
    }


def false_return(msg='', data=''):
    return {
        'success': False,
        'msg': msg,
        'data': data
    }
