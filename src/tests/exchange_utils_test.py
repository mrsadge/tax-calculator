from src.exchanges.utils import process_buys, process_sells, calculate_hifo_obligation_after_sale

import datetime
import mock
import unittest


class ExchangeUtilsTest(unittest.TestCase):

    def test_process_buys(self):
        date_1 = datetime.datetime.strptime('4/25/2021 10:00', "%m/%d/%Y %H:%M")
        date_2 = datetime.datetime.strptime('4/25/2021 9:00', "%m/%d/%Y %H:%M")
        date_3 = datetime.datetime.strptime('4/25/2021 8:00', "%m/%d/%Y %H:%M")
        buys = [
            ['trade_1', 'BUY', date_1, 1, 'BTC', 0.50, 59999.50],
            ['trade_2', 'BUY', date_2, 2, 'ETH', 0.40, 3999.60],
            ['trade_3', 'BUY', date_3, 1, 'BTC', 0.50, 49999.50]
        ]
        expected_bases = {
            'BTC': [
                (date_3, 49999.50, 1, 'trade_3'),
                (date_1, 59999.50, 1, 'trade_1')
            ],
            'ETH': [
                (date_2, 3999.60 / 2, 2, 'trade_2')
            ],
        }
        expected_fee = 1.40
        self.assertEqual((expected_bases, expected_fee,), process_buys(buys))


if __name__ == '__main__':
    unittest.main()
