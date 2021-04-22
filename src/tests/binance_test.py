from src.exchanges.binance import prepare_rows_helper
from src.exchanges.utils import get_request_with_retry

import datetime
import mock
import unittest

STANDARD_CSV_FIELDS = ['trade id', 'action', 'date',
                       'size', 'asset', 'trading_fee', 'total_dollars']
class BinanceTest(unittest.TestCase):

    @mock.patch('src.exchanges.utils.get_request_with_retry')
    def test_simple_buy_row(self, request_mock):
        row = '6/23/2020 17:12,KAVAUSDT,BUY,0.50,4.000KAVA,2.000USDT,0.04000KAVA'.split(',')

        request_mock.return_value = [[1609383540000, '0.5', '0.5', '0.5', '0.5',
                                      '937.05200000', 1609383599999, '34885.95061710', 50, '781.94600000', '29111.25965560', '0']]
        expected_date = datetime.datetime.strptime('6/23/2020 17:12', "%m/%d/%Y %H:%M")
        expected = [['BINANCE:1', 'BUY', expected_date, 4.0, 'KAVA', 0.02, 2.02]]

        self.assertEqual(prepare_rows_helper(row, 1), expected)

    @mock.patch('src.exchanges.utils.get_request_with_retry')
    def test_crypto_to_crypto_trade(self, request_mock):
        # Assume 1 BTC = $1,000, 1 LEND = $50.
        # ==> 1 LEND = 0.05 BTC.
        row = '4/25/2020 19:54,LENDBTC,BUY,0.05,"40.000LEND",0.1000BTC,0.1000LEND'.split(
            ',')

        btc_reference_side_effect = [[1609383540000, '1000', '1000', '1000', '1000',
                                      '937.05200000', 1609383599999, '34885.95061710', 50, '781.94600000', '29111.25965560', '0']]
        lend_fee_side_effect = [[1609383540000, '50', '50', '50', '50',
                                 '937.05200000', 1609383599999, '34885.95061710', 50, '781.94600000', '29111.25965560', '0']]
        request_mock.side_effect = [btc_reference_side_effect, lend_fee_side_effect]

        expected_date = datetime.datetime.strptime('4/25/2020 19:54', "%m/%d/%Y %H:%M")
        expected = [
            ['BINANCE:1', 'BUY', expected_date, 40.0, 'LEND', 0, 100.0],
            ['BINANCE:1-AUXILIARY', 'SELL', expected_date, 0.1, 'BTC', 5.0, 95.0]
        ]

        self.assertEqual(prepare_rows_helper(row, 1), expected)


if __name__ == '__main__':
    unittest.main()
