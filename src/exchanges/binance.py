#!/usr/local/bin/python3

import csv
import datetime
import re
import requests
import src.exchanges.utils as utils


BINANCE_TRADES_FILE = 'binance_trades.csv'
BINANCE_TRADES_CSV_FIELDS = ['Date(UTC)', 'Pair', 'Side', 'Price', 'Executed', 'Amount', 'Fee']
BINANCE_COLUMN_PATTERN = r'^([0-9]+\.[0-9]+)(.*)$'
KLINE_CACHE = {}


def get_historical_price(symbol, date, use_max=True):
    # Kline helps fetch historical data from binance for free
    if symbol in utils.REBRANDED_TOKENS:
        print('Using special value for ${} ({})'.format(symbol, date))
        return -1
    if (symbol, date, use_max,) in KLINE_CACHE:
        return KLINE_CACHE[(symbol, date, use_max,)]
    start = int(date.timestamp()) * 1000
    end = start + 59999  # milliseconds
    kline_endpoint = 'https://api.binance.com/api/v3/klines?symbol={coin}USDT&interval=1m&startTime={start}&endTime={end}'.format(
        coin=symbol, start=start, end=end
    )
    j = utils.get_request_with_retry(kline_endpoint, {})
    assert len(j) == 1
    # Find the best moment during the 1m candle ;)
    if use_max:
        price = float(max(j[0][1:5]))
    else:
        price = float(min(j[0][1:5]))
    KLINE_CACHE[(symbol, date, use_max,)] = price
    return price


def prepare_rows_helper(row, trade_id_counter):
    trade_id = 'BINANCE:{}'.format(trade_id_counter)
    action = row[2].upper()
    date = datetime.datetime.strptime(
        row[0], "%m/%d/%Y %H:%M")
    price = float(row[3].replace(',', ''))

    size_matcher = re.search(BINANCE_COLUMN_PATTERN, row[4].strip('"').replace(',', ''))
    size = float(size_matcher.group(1))
    asset = size_matcher.group(2)  # primary coin
    assert size is not None and asset

    # Asset = the primary coin, Ref_asset = the reference coin
    # e.g. with BTCBNB pair, asset = BTC, ref_asset = BNB
    ref_asset_matcher = re.search(
        BINANCE_COLUMN_PATTERN, row[5].strip('"').replace(',', ''))
    ref_asset_total = float(ref_asset_matcher.group(1))
    ref_asset_symbol = ref_asset_matcher.group(2)
    assert ref_asset_total is not None and ref_asset_symbol
    add_reference_trade = False
    if 'USD' in ref_asset_symbol:
        ref_asset_price = 1.0
    else:
        ref_asset_price = get_historical_price(ref_asset_symbol, date, action == 'BUY')
        assert ref_asset_price > 0
        add_reference_trade = True

    # Fees could be paid in the primary coin or BNB if available, since BNB
    # provides discounted trades.
    fee_matcher = re.search(BINANCE_COLUMN_PATTERN,
                            row[6].strip('"').replace(',', ''))
    fee_asset_total = float(fee_matcher.group(1))
    fee_asset_symbol = fee_matcher.group(2)
    assert fee_asset_total is not None and fee_asset_symbol
    if 'USD' in fee_asset_symbol:
        fee_asset_price = 1.0
    elif fee_asset_symbol == asset and 'USD' in ref_asset_symbol:
        fee_asset_price = price
    else:
        fee_asset_price = get_historical_price(fee_asset_symbol, date, action == 'BUY')
        if fee_asset_price == -1:
            if fee_asset_symbol == asset:
                fee_asset_price = price * fee_asset_total * ref_asset_price
            else:
                assert False
    trading_fee = fee_asset_total * fee_asset_price

    if action == 'BUY':
        assert fee_asset_symbol == 'BNB' or fee_asset_symbol == asset
        total_dollars_without_fee = ref_asset_total * ref_asset_price
        total_dollars_with_fee = total_dollars_without_fee + trading_fee
    else:
        assert fee_asset_symbol == 'BNB' or fee_asset_symbol == ref_asset_symbol
        total_dollars_without_fee = ref_asset_total * ref_asset_price
        total_dollars_with_fee = total_dollars_without_fee - trading_fee

    ret = []
    # Add a concurrent buy and a sell to represent a crypto-to-crypto trade
    if add_reference_trade:
        # If adding both a buy and a sell, realize fees on crypto sell side, and use no fees
        # on the crypto buy side (lower basis)
        if action == 'BUY':
            ret.append([trade_id, action, date, size,
                        asset, 0, total_dollars_without_fee])
            ret.append(['{}-AUXILIARY'.format(trade_id), 'SELL', date,
                        ref_asset_total, ref_asset_symbol, trading_fee, total_dollars_without_fee - trading_fee])
        else:
            ret.append([trade_id, action, date, size,
                        asset, trading_fee, total_dollars_without_fee - trading_fee])
            ret.append(['{}-AUXILIARY'.format(trade_id), 'BUY', date,
                        ref_asset_total, ref_asset_symbol, 0, total_dollars_without_fee])
    else:
        ret.append([trade_id, action, date, size,
                    asset, trading_fee, total_dollars_with_fee])
    return ret


def get_csv_rows(filename=BINANCE_TRADES_FILE):
    rows = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        assert next(reader) == BINANCE_TRADES_CSV_FIELDS
        trade_id_counter = 0  # Binance does not provide an internal trade ID
        for row in reader:
            rows += prepare_rows_helper(row, trade_id_counter)
            trade_id_counter += 1
    return sorted(rows, key=lambda x: x[2])


STANDARD_CSV_FIELDS = ['trade id', 'action', 'date',
                       'size', 'asset', 'trading_fee', 'total_dollars']

if __name__ == '__main__':
    rows = get_csv_rows()
    utils.get_token_bases(rows)
