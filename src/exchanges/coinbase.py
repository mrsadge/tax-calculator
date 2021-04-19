#!/usr/local/bin/python3

import csv
import datetime
import utils


COINBASE_CSV_FILE = 'coinbase_trades.csv'
COINBASE_CSV_FIELDS = ['portfolio', 'trade id', 'product', 'side', 'created at',
                       'size', 'size unit', 'price', 'fee', 'total', 'price/fee/total unit']

STANDARD_CSV_FIELDS = ['trade id', 'action', 'date',
                       'size', 'asset', 'trading_fee', 'total_dollars']


def get_csv_rows(filename=COINBASE_CSV_FILE):
    rows = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        assert next(reader) == COINBASE_CSV_FIELDS
        for row in reader:
            trade_id = 'COINBASE:{}'.format(row[1])
            action = row[3]
            date = datetime.datetime.strptime(
                row[4], "%Y-%m-%dT%H:%M:%S.%fz")
            size = float(row[5])
            asset = row[6]
            trading_fee = float(row[8])
            net_fiat = float(row[9])
            assert 'USD' in row[10]
            rows.append([trade_id, action, date, size, asset, trading_fee, net_fiat])
    return sorted(rows, key=lambda x: x[2])


if __name__ == '__main__':
    rows = get_csv_rows()
    utils.get_token_bases(rows)
