#!/usr/local/bin/python3

import csv
import datetime
import utils


COINBASE_TRADES_FILE = 'coinbase_trades.csv'
COINBASE_DEPOSITS_FILE = 'coinbase_deposits.csv'
COINBASE_TRADES_CSV_FIELDS = ['portfolio', 'trade id', 'product', 'side', 'created at',
                              'size', 'size unit', 'price', 'fee', 'total', 'price/fee/total unit']


def get_csv_rows(filename=COINBASE_TRADES_FILE):
    rows = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        assert next(reader) == COINBASE_TRADES_CSV_FIELDS
        for row in reader:
            trade_id = 'COINBASE:{}'.format(row[1])
            action = row[3].upper()
            date = datetime.datetime.strptime(
                row[4], "%Y-%m-%dT%H:%M:%S.%fz")
            size = float(row[5])
            asset = row[6]
            trading_fee = float(row[8])
            net_fiat = abs(float(row[9]))
            assert 'USD' in row[10]
            rows.append([trade_id, action, date, size, asset, trading_fee, net_fiat])
    return sorted(rows, key=lambda x: x[2])


# 1. obtain buy bases for every single wallet (XYZUSD are buy events and ABCXYZ are both buy and sell events)
# 2. record deposits by inheriting bases from source wallet to the current wallet's buys (only share HIFO buy trades before the withdrawal event)
# 3. record withdrawals by subtracting from current wallet's buys so that the destination wallet can use those bases (share HIFO trades)
# 3. aggregate all sells into one chronological list, and iterate through them (follow the wallet they transacted on)
def get_deposits_and_withdrawals(filename=COINBASE_DEPOSITS_FILE):
    pass


if __name__ == '__main__':
    rows = get_csv_rows()
    rows_2019 = get_csv_rows(filename='coinbase_trades_2019.csv')
    leftovers_2019 = utils.get_previous_year_leftovers(rows_2019)
    utils.process_trades(leftovers_2019 + rows)
