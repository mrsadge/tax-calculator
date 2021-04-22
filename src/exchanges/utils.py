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


def get_request_with_retry(url, headers, num_retries=3):
    for i in range(num_retries):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception:
            time.sleep(2**i)
    return None


# Returns (amount, bool,) where bool represents whether the obligation is short-term
def calculate_obligation(entry_basis, exit_basis, entry_size, exit_size, entry_date, exit_date):
    short_term = True
    if exit_date - entry_date > datetime.timedelta(days=365):
        short_term = False
    return ((exit_basis * exit_size) - (entry_basis * entry_size), short_term,)


# Returns (short_term_amount, long_term_amount,
#          remaining entry trades after HIFO eviction, remaining exit size,
#          specific IDs of entry trades)
def calculate_hifo_obligation_after_sale(all_bases, end_index, sale_size, net_fiat, sale_date, sale_trade_id):
    bases_copy = copy.deepcopy(all_bases[:end_index])
    exit_basis = net_fiat / sale_size
    done = False
    deleted_state = {}
    short_term_obligation = 0
    long_term_obligation = 0
    specific_entry_ids = []

    while sale_size > 0 and len(deleted_state) != end_index:
        max_index = bases_copy.index(max(
            bases_copy, key=lambda x: x[0]))
        curr_date, curr_basis, curr_size, curr_trade_id = bases_copy[max_index]

        if curr_size >= sale_size:
            entry_size = sale_size
            exit_size = sale_size
            deleted_state[curr_trade_id] = sale_size
        else:
            entry_size = curr_size
            exit_size = curr_size
            deleted_state[curr_trade_id] = curr_size
            bases_copy.pop(max_index)

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


def get_token_bases(rows):
    # v1: Assume we only have 1 default portfolio, denominated in USD/USD stable.

    basis_dict = {}
    sells = []
    fee_total = 0

    # Process buys
    for row in rows:
        trade_id, action, date, size, asset, fee, net_fiat = row
        if action == 'SELL':
            sells.append(row)
            continue
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

    specific_id_audit = []
    sold_assets_with_no_basis = {}
    short_term_obligation = 0
    long_term_obligation = 0
    # Process sells
    for sell in sells:
        trade_id, action, date, size, asset, fee, net_fiat = sell
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

        # v1: HIFO support only
        hifo = None
        i = len(prev_bases) - 1
        while i >= 0:
            curr_date, curr_basis, curr_size, curr_trade_id = prev_bases[i]
            if curr_date < date:
                hifo = calculate_hifo_obligation_after_sale(
                    prev_bases, i+1, size, net_fiat, date, trade_id)
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
