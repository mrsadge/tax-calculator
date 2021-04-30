#!/usr/local/bin/python3

import csv
import datetime
import utils


KRAKEN_TRADES_FILE = 'kraken_trades.csv'
KRAKEN_TRADES_CSV_FIELDS = ['txid', 'ordertxid', 'pair', 'time', 'type',
                            'ordertype', 'price', 'cost', 'fee', 'vol', 'margin', 'misc', 'ledgers']


def get_standard_trades(filename=KRAKEN_TRADES_FILE):
    rows = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        assert next(reader) == KRAKEN_TRADES_CSV_FIELDS
        for row in reader:
            trade_id = 'KRAKEN:{}:{}'.format(row[0], row[1])
            action = row[4].upper()
            date = datetime.datetime.strptime(
                row[3], "%Y-%m-%d %H:%M:%S.%f")
            size = float(row[9])
            asset = row[2].split('USD')[0]
            if asset.startswith('X'):
                asset = asset[1:]
            if asset.endswith('Z'):
                asset = asset[:-1]
            if asset == 'XBT':
                asset = 'BTC'
            if not asset:
                continue
            trading_fee = float(row[8])
            if action == 'BUY':
                total_dollars = float(row[7]) + trading_fee
            else:
                total_dollars = float(row[7]) - trading_fee
            rows.append([trade_id, action, date, size, asset, trading_fee, total_dollars])
    return sorted(rows, key=lambda x: x[2])


if __name__ == '__main__':
    rows = get_standard_trades()
    utils.process_trades(rows)
