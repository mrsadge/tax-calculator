v0

## Repo components:


	src/

    .. exchanges/   # CEX modules
		
    .. fiat_ramps/  # empty - gateways to connect wallets with fiat accounts
		
    .. wallets/     # L1 chain modules
		
    .. tests/       # unit tests
		
	< PLACE YOUR CSV FILES IN THE BASE DIR >

## CSV file instructions:

__Coinbase__: self explanatory - note only supports statements with 1 default portfolio
- Default name: coinbase_trades.csv

__Kraken__: self explanatory - note does not support kraken staking
- Default name: kraken_trades.csv

__Binance__: only allows you to download 3 months at a time max, so be sure to navigate to Orders --> Trade History --> Generate All Trade Statements

This might take up to 30mins - but be sure to do this instead of aggregating four 3-month statements; the csv format slightly varies between these two exports.
- Default name: binance_trades.csv

__Etherscan__: export csv for your respective address(es) from the etherscan explorer.
- Default name(s): etherscan_{address}.csv
- The etherscan runtime also requires a `secrets.py` file. Place this file in `src/wallets/secrets.py` with the constant `ETHERSCAN_API_KEY=<YOUR KEY>`

## Execution instructions:

	(Python3)

Running a module

`PYTHONPATH=. python src/exchanges/binance.py`

Running a unit test

`PYTHONPATH=. python src/tests/binance_test.py`
