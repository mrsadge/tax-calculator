#!/usr/local/bin/python3

import copy
import datetime
import requests
import time


# Date should be standardized in UTC
STANDARD_CSV_FIELDS = ['trade id', 'action', 'date', 'size', 'asset', 'trading_fee', 'total_dollars']
REBRANDED_TOKENS = {
    'LEND': 'AAVE',
}


def get_request_with_retry(url, headers, num_retries=6):
    for i in range(num_retries):
        try:
            response = requests.get(url, headers=headers)
            if response.status_code >= 400 and response.status_code < 500:
                print('received a {} from {}'.format(response.status_code, url))
            response.raise_for_status()
            return response.json()
        except Exception:
            time.sleep(2**i)
    return None


def process_buys(buys):
    basis_dict = {}
    fee_total = 0
    for row in buys:
        trade_id, action, date, size, asset, fee, net_fiat = row
        assert action == 'BUY'
        fee_total += fee
        basis = abs(net_fiat) / size
        if asset not in basis_dict:
            basis_dict[asset] = []

        index = 0
        for curr_date, curr_price, curr_size, curr_trade_id in basis_dict[asset]:
            if date < curr_date:
                break
            index += 1

        if index > -1:
            basis_dict[asset].insert(index, (date, basis, size, trade_id,))
    
    return basis_dict, fee_total


def process_sells(sells, basis_dict):
    specific_id_audit = []
    sold_assets_with_no_basis = {}
    short_term_obligation = 0
    long_term_obligation = 0
    fee_total = 0
    # Process sells
    for sell in sells:
        trade_id, action, date, size, asset, fee, net_fiat = sell
        if action == 'BURN':
            lowifo = None
            prev_bases = basis_dict[asset]
            i = len(prev_bases) - 1
            while i >= 0:
                curr_date, curr_basis, curr_size, curr_trade_id = prev_bases[i]
                if curr_date < date:
                    lowifo = calculate_obligation_after_sale(
                        prev_bases, i+1, 'lowifo', size, net_fiat, date, trade_id)
                    break
                i -= 1
            _, _, remaining_bases, remaining_size, specific_entries = lowifo  # use lowest basis for non-transfer L1 fees ;)
            basis_dict[asset] = remaining_bases
            for entry in specific_entries:
                csv_line = '{},{},BURN'.format(asset, entry)
                specific_id_audit.append(csv_line)
            continue

        assert action == 'SELL'
        fee_total += fee
        basis = net_fiat / size
        if asset not in sold_assets_with_no_basis:
            sold_assets_with_no_basis[asset] = []

        # Obtained the asset somewhere else, e.g. in a prior year OR desposited in
        if asset not in basis_dict:
            sold_assets_with_no_basis[asset].append(
                (date, basis, size, trade_id,))
            continue
        prev_bases = basis_dict[asset]

        # v1: HIFO support only for sells
        hifo = None
        i = len(prev_bases) - 1
        while i >= 0:
            curr_date, curr_basis, curr_size, curr_trade_id = prev_bases[i]
            if curr_date < date:
                hifo = calculate_obligation_after_sale(
                    prev_bases, i+1, 'hifo', size, net_fiat, date, trade_id)
                break
            i -= 1

        if not hifo:
            sold_assets_with_no_basis[asset].append(
                (date, basis, size, trade_id,))
            continue
        curr_short, curr_long, remaining_bases, remaining_size, specific_entries = hifo
        short_term_obligation += curr_short
        long_term_obligation += curr_long
        if remaining_size > 0 and basis * remaining_size >= 0.01:  # only record assets worth more than 1 cent
            sold_assets_with_no_basis[asset].append(
                (date, basis, remaining_size, trade_id,))
        basis_dict[asset] = remaining_bases
        for entry in specific_entries:
            csv_line = '{},{}'.format(asset, entry)
            specific_id_audit.append(csv_line)

    return short_term_obligation, long_term_obligation, specific_id_audit, sold_assets_with_no_basis, fee_total


# Returns (amount, bool,) where bool represents whether the obligation is short-term
def calculate_obligation(entry_basis, exit_basis, entry_size, exit_size, entry_date, exit_date):
    short_term = True
    if exit_date - entry_date > datetime.timedelta(days=365):
        short_term = False
    return ((exit_basis * exit_size) - (entry_basis * entry_size), short_term,)


# Returns (short_term_amount, long_term_amount,
#          remaining entry trades after HIFO eviction, remaining exit size,
#          specific IDs of entry trades)
def calculate_obligation_after_sale(all_bases, end_index, strategy, sale_size, net_fiat, sale_date, sale_trade_id):
    bases_copy = copy.deepcopy(all_bases[:end_index])
    exit_basis = net_fiat / sale_size
    done = False
    deleted_state = {}
    short_term_obligation = 0
    long_term_obligation = 0
    specific_entry_ids = []

    while sale_size > 0 and len(deleted_state) != end_index:
        if strategy == 'hifo':
            strategy_index = bases_copy.index(max(
                bases_copy, key=lambda x: x[0]))
        elif strategy == 'lowifo':
            strategy_index = bases_copy.index(min(
                bases_copy, key=lambda x: x[0]))
        else:
            raise ValueError('unsupported tax strategy: {}'.format(strategy))
        curr_date, curr_basis, curr_size, curr_trade_id = bases_copy[strategy_index]

        if curr_size >= sale_size:
            entry_size = sale_size
            exit_size = sale_size
            deleted_state[curr_trade_id] = sale_size
        else:
            entry_size = curr_size
            exit_size = curr_size
            deleted_state[curr_trade_id] = curr_size
            bases_copy.pop(strategy_index)

        sale_size -= curr_size
        obligation, short_term = calculate_obligation(
            curr_basis, exit_basis, entry_size, exit_size, curr_date, sale_date)
        if short_term:
            short_term_obligation += obligation
        else:
            long_term_obligation += obligation
        assert(sale_date > curr_date)
        specific_entry_ids.append('{},{},{},{},{},{},{},{},{}'.format(
            curr_date, curr_basis, entry_size, curr_trade_id,
            sale_date, exit_basis, exit_size, sale_trade_id, obligation
        ))

    remaining_bases = []
    for entry in all_bases:
        curr_date, curr_basis, curr_size, curr_trade_id = entry
        if curr_trade_id not in deleted_state:
            remaining_bases.append(entry)
            continue
        new_size = curr_size - deleted_state[curr_trade_id]
        if new_size > 0:
            remaining_bases.append(
                (curr_date, curr_basis, new_size, curr_trade_id,))

    return short_term_obligation, long_term_obligation, remaining_bases, sale_size, specific_entry_ids


# Get 2019's leftover assets to find bases for sells and withdrawals in 2020.
def get_previous_year_leftovers(rows):
    buys = []
    sells = []
    for row in rows:
        if row[1] == 'BUY':
            buys.append(row)
        else:
            sells.append(row)

    # Process buys
    basis_dict, _ = process_buys(buys)

    # Process sells
    _, _, _, _, _ = process_sells(sells, basis_dict)

    previous_year_buys = []
    for asset, basis_info in basis_dict.items():
        for date, basis, size, trade_id in basis_info:
            previous_year_buys.append(
                [trade_id, 'BUY', date, size, asset, 0, basis * size]  # 0 fee for the previous year
            )
    return previous_year_buys


def process_trades(rows):
    # v1: Assume we only have 1 default portfolio, denominated in USD/USD stable.
    buys = []
    sells = []
    for row in rows:
        if row[1] == 'BUY':
            buys.append(row)
        else:
            sells.append(row)

    # Process buys
    basis_dict, buy_fees = process_buys(buys)

    # Process sells
    short_term_obligation, long_term_obligation, specific_id_audit, sold_assets_with_no_basis, sell_fees = process_sells(sells, basis_dict)
    fee_total = buy_fees + sell_fees

    print('Total short term obligation: ${}'.format(short_term_obligation))
    print('Total long term obligation: ${}'.format(long_term_obligation))
    print('Fees paid to the exchange: ${}'.format(fee_total))

    print('=====================================')
    print('Assets sold with no basis set in 2020:')
    for asset, basis_info in sold_assets_with_no_basis.items():
        if sum(x[1] * x[2] for x in basis_info) < 0.01:
            continue
        print('{} {}'.format(sum(x[2] for x in basis_info), asset))

    print('================')
    print('Leftover assets:')
    for asset, basis_info in basis_dict.items():
        if sum(x[1] * x[2] for x in basis_info) < 0.01:
            continue
        print('{} {}'.format(sum(x[2] for x in basis_info), asset))

    validation = 0
    for line in specific_id_audit:
        validation += float(line.split(',')[-1])
    assert(int(validation) == int(short_term_obligation + long_term_obligation))


if __name__ == '__main__':
    rows = [
        ['COINBASE:558031', 'BUY', datetime.datetime(2020, 4, 10, 7, 8, 43, 44000), 5515.2, 'KNC', 2.6307504, 2633.3811504],
        ['COINBASE:558081', 'BUY', datetime.datetime(2020, 4, 10, 7, 28, 20, 101000), 3879.1, 'KNC', 1.8503307, 1852.1810307],
        ['COINBASE:558082', 'BUY', datetime.datetime(2020, 4, 10, 7, 28, 31, 374000), 1044.7, 'KNC', 0.4983219, 498.8202219],
        ['COINBASE:558083', 'BUY', datetime.datetime(2020, 4, 10, 7, 28, 35, 952000), 13.9, 'KNC', 0.0066303, 6.6369303],
        ['COINBASE:558084', 'BUY', datetime.datetime(2020, 4, 10, 7, 29, 17, 317000), 480.0, 'KNC', 0.22896, 229.18896],
        ['COINBASE:558085', 'BUY', datetime.datetime(2020, 4, 10, 7, 29, 17, 418000), 1392.0, 'KNC', 0.663984, 664.647984],
        ['COINBASE:558086', 'BUY', datetime.datetime(2020, 4, 10, 7, 29, 25, 547000), 479.0, 'KNC', 0.228483, 228.711483],
        ['COINBASE:558087', 'BUY', datetime.datetime(2020, 4, 10, 7, 29, 27, 419000), 1000.0, 'KNC', 0.477, 477.477],
        ['COINBASE:558089', 'BUY', datetime.datetime(2020, 4, 10, 7, 29, 50, 479000), 1393.0, 'KNC', 0.664461, 665.125461],
        ['COINBASE:558091', 'BUY', datetime.datetime(2020, 4, 10, 7, 30, 1, 502000), 1052.0, 'KNC', 0.501804, 502.305804],
        ['COINBASE:558092', 'BUY', datetime.datetime(2020, 4, 10, 7, 30, 4, 26000), 51.0, 'KNC', 0.024327, 24.351327],
        ['COINBASE:558093', 'BUY', datetime.datetime(2020, 4, 10, 7, 30, 48, 854000), 1000.0, 'KNC', 0.477, 477.477],
        ['COINBASE:558094', 'BUY', datetime.datetime(2020, 4, 10, 7, 30, 55, 444000), 1000.0, 'KNC', 0.477, 477.477],
        ['COINBASE:558095', 'BUY', datetime.datetime(2020, 4, 10, 7, 31, 19, 180000), 1000.0, 'KNC', 0.477, 477.477],
        ['COINBASE:558096', 'BUY', datetime.datetime(2020, 4, 10, 7, 31, 20, 209000), 936.4, 'KNC', 0.4466628, 447.1094628],
        ['COINBASE:590983', 'SELL', datetime.datetime(2020, 4, 24, 18, 43, 2, 707000), 436.7, 'KNC', 0.33774378, 224.82477622],
        ['COINBASE:590984', 'SELL', datetime.datetime(2020, 4, 24, 18, 43, 2, 809000), 1160.0, 'KNC', 0.897144, 597.198856],
        ['COINBASE:590985', 'SELL', datetime.datetime(2020, 4, 24, 18, 43, 2, 960000), 121.0, 'KNC', 0.0935814, 62.2940186],
        ['COINBASE:590987', 'SELL', datetime.datetime(2020, 4, 24, 18, 43, 9, 386000), 29.0, 'KNC', 0.0224286, 14.9299714],
        ['COINBASE:590990', 'SELL', datetime.datetime(2020, 4, 24, 18, 43, 34, 578000), 188.7, 'KNC', 0.14594058, 97.14777942],
        ['COINBASE:590991', 'SELL', datetime.datetime(2020, 4, 24, 18, 43, 37, 170000), 2.0, 'KNC', 0.0015468, 1.0296532],
        ['COINBASE:590995', 'SELL', datetime.datetime(2020, 4, 24, 18, 44, 40, 981000), 29.0, 'KNC', 0.0224286, 14.9299714],
        ['COINBASE:590996', 'SELL', datetime.datetime(2020, 4, 24, 18, 46, 6, 386000), 18274.9, 'KNC', 14.13380766, 9408.40463234]
    ]
    buy_size = sell_size = 0
    for row in rows:
        if row[1] == 'BUY':
            buy_size += row[3]
        else:
            sell_size += row[3]
    print(buy_size)
    print(sell_size)
    process_trades(rows)
