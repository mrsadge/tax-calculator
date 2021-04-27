#!/usr/local/bin/python3

import csv
import datetime
import wallets.secrets

from exchanges.utils import get_request_with_retry, process_trades


ETHERSCAN_PRIMARY_TRADES_FILE = 'etherscan_primary_{wallet}.csv'.format(
    wallet=wallets.secrets.PRIMARY_WALLET_ADDRESS)
ETHERSCAN_CSV_FIELDS = ["Txhash", "Blockno", "UnixTimestamp", "DateTime", "From", "To", "ContractAddress",
                        "Value_IN(ETH)", "Value_OUT(ETH)", "CurrentValue @ $2463.09/Eth", "TxnFee(ETH)",
                        "TxnFee(USD)", "Historical $Price/Eth", "Status", "ErrCode"]
ETHERSCAN_TRANSACTION_API_ENDPOINT = 'https://api.etherscan.io/api?module=account&action=tokentx&address={wallet}&startblock={block}&endblock={block}&apikey={token}'


def get_transfers_from_blockno(address, blockno, original_txid):
    url = ETHERSCAN_TRANSACTION_API_ENDPOINT.format(
        wallet=address, block=blockno, token=wallets.secrets.ETHERSCAN_API_KEY
    )
    response = get_request_with_retry(url, {})
    assert response['message'] == 'OK'
    relevant_transfers = []
    counter = 0
    for transfer in response['result']:
        if original_txid != transfer['hash'] or transfer['from'] == '0x0000000000000000000000000000000000000000':
            continue
        trade_id = '{}:{}'.format(transfer['hash'], counter)
        asset = transfer['tokenSymbol']
        decimal = int(transfer['tokenDecimal'])
        size = int(transfer['value']) / (10 ** decimal)
        if transfer['to'] == address:
            action = 'BUY'
        else:
            action = 'SELL'
        # figure out basis here
        net_fiat = 0
        relevant_transfers.append([trade_id, action, size, asset, net_fiat])
        counter += 1
    return relevant_transfers


def get_csv_rows(address):
    rows = []
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
            transfers = get_transfers_from_blockno(address, blockno, txid)
            if not transfers:
                rows.append([txid, 'BURN', date, txn_fee_amount, 'ETH', trading_fee, 0])
                continue
            for transfer in transfers:
                trade_id, action, size, asset, net_fiat = transfer
                rows.append([trade_id, action, date, size,
                            asset, trading_fee, net_fiat])
    return sorted(rows, key=lambda x: x[2])


if __name__ == '__main__':
    rows = get_csv_rows(wallets.secrets.PRIMARY_WALLET_ADDRESS)
    process_trades(rows)
