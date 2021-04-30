#!/usr/local/bin/python3

import csv
import datetime
import json
import src.wallets.secrets as secrets

from src.exchanges.utils import get_request_with_retry, process_trades


ETHERSCAN_PRIMARY_TRADES_FILE = 'etherscan_primary_{wallet}.csv'.format(
    wallet=secrets.PRIMARY_WALLET_ADDRESS)
ETHERSCAN_CSV_FIELDS = ["Txhash", "Blockno", "UnixTimestamp", "DateTime", "From", "To", "ContractAddress",
                        "Value_IN(ETH)", "Value_OUT(ETH)", "CurrentValue @ $2463.09/Eth", "TxnFee(ETH)",
                        "TxnFee(USD)", "Historical $Price/Eth", "Status", "ErrCode"]
ETHERSCAN_TRANSACTION_API_ENDPOINT = 'https://api.etherscan.io/api?module=account&action=tokentx&address={wallet}&startblock={block}&endblock={block}&apikey={token}'
COINGECKO_FETCH_PRICE_API_ENDPOINT = 'https://api.coingecko.com/api/v3/coins/{asset_id}/history?date={dt_string}'
with open('coin_map.json') as f:
    COIN_MAP = json.loads(f.read())


def get_daily_price_from_coingecko(asset, name, timestamp):
    dt_string = datetime.datetime.fromtimestamp(timestamp).strftime("%d-%m-%Y")
    asset_id = None
    if asset not in COIN_MAP:
        # Unrecognized assets do not trigger taxable events and have 0 value
        print('Unrecognized asset by coingecko: {}'.format(asset))
        return 0
    if len(COIN_MAP[asset]) == 1:
        # Auto-resolve unique token tickers to avoid naming inconsistencies
        asset_id = COIN_MAP[asset][0][1]
    else:
        for current_name, current_id in COIN_MAP[asset]:
            if current_name in name or name in current_name:
                asset_id = current_id
                break
    if not asset_id:
        # Tokens that are registered under a valid symbol but aren't recognized by coingecko should be ignored too
        print('Missing asset info for {} {}'.format(asset, name))
        return 0
    url = COINGECKO_FETCH_PRICE_API_ENDPOINT.format(
        asset_id=asset_id, dt_string=dt_string
    )
    response = get_request_with_retry(url, {'accept': 'application/json'})
    if 'market_data' not in response:
        print('Missing price info for {} on {}'.format(asset_id, dt_string))
        return 0
    return float(response['market_data']['current_price']['usd'])


def get_transfers_from_blockno(address, blockno, original_txid, historical_eth_price, trading_fee):
    url = ETHERSCAN_TRANSACTION_API_ENDPOINT.format(
        wallet=address, block=blockno, token=secrets.ETHERSCAN_API_KEY
    )
    response = get_request_with_retry(url, {})
    assert response['message'] == 'OK' or response['message'] == 'No transactions found'
    relevant_transfers = []
    counter = 0
    for transfer in response['result']:
        if original_txid != transfer['hash'] or transfer['from'] == '0x0000000000000000000000000000000000000000':
            continue
        trade_id = '{}:{}'.format(transfer['hash'], counter)
        asset = transfer['tokenSymbol']
        tokenName = transfer['tokenName']
        decimal = int(transfer['tokenDecimal'])
        size = int(transfer['value']) / (10 ** decimal)
        if transfer['to'] == address:
            action = 'BUY'
        elif transfer['from'] == address:
            action = 'SELL'
        else:
            raise ValueError('transfer does not involve the current address')
        # figure out basis here
        if asset == "eth":
            current_price = historical_eth_price
        else:
            asset_upper = asset.upper()
            tokenName_upper = tokenName.upper()
            current_price = get_daily_price_from_coingecko(
                asset_upper, tokenName_upper, int(transfer['timeStamp']))
        net_fiat = current_price * size
        relevant_transfers.append([trade_id, action, size, asset, net_fiat])
        counter += 1

    # If there are 0 relevant transfers, we simply have some contract execution that
    # doesn't affect asset balance beyond gas fee (e.g. approval)
    # If there is only 1 relevant transfer, we count it as a deposit or a withdrawal
    if len(relevant_transfers) <= 1:
        return relevant_transfers

    # Determine the optimal transfer basis to assign the gas fee to, prioritize the sell
    # transaction if there is one to minimize gains/maximize losses
    buy_max = sell_max = 0
    buy_max_index = sell_max_index = 0
    for i, (_, action, _, _, net_fiat,) in enumerate(relevant_transfers):
        if action == 'BUY':
            if net_fiat > buy_max:
                buy_max = net_fiat
                buy_max_index = i
        else:
            if net_fiat > sell_max:
                sell_max = net_fiat
                sell_max_index = i
    if sell_max:
        relevant_transfers[sell_max_index][-1] -= trading_fee
    elif buy_max:
        relevant_transfers[buy_max_index][-1] += trading_fee
    return relevant_transfers


def get_standard_trades_deposits_withdrawals(address):
    trades = []
    deposits = []
    withdrawals = []
    filename = ETHERSCAN_PRIMARY_TRADES_FILE.format(wallet=address)
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        assert next(reader) == ETHERSCAN_CSV_FIELDS
        for row in reader:
            txid = row[0]
            blockno = row[1]
            date = datetime.datetime.strptime(
                row[3], "%Y-%m-%d %H:%M:%S")
            txn_fee_amount = float(row[10])
            historical_eth_price = float(row[12])
            trading_fee = txn_fee_amount * historical_eth_price
            transfers = get_transfers_from_blockno(
                address, blockno, txid, historical_eth_price, trading_fee)
            if len(transfers) == 1:
                lone_transfer = transfers[0]
                if lone_transfer[1] == 'SELL':
                    trades.append([txid, 'BURN', date, txn_fee_amount, 'ETH', trading_fee, 0])
                    withdrawals.append(lone_transfer)
                else:
                    deposits.append(lone_transfer)
                continue
            if not transfers:
                trades.append([txid, 'BURN', date, txn_fee_amount, 'ETH', trading_fee, 0])
                continue
            for transfer in transfers:
                trade_id, action, size, asset, net_fiat = transfer
                trades.append([trade_id, action, date, size,
                            asset, trading_fee, net_fiat])
    return sorted(trades, key=lambda x: x[2]), deposits, withdrawals


if __name__ == '__main__':
    trades, deposits, withdrawals = get_standard_trades_deposits_withdrawals(
        secrets.PRIMARY_WALLET_ADDRESS)
    process_trades(trades)
