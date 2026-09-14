import unittest
import numpy as np
from retirement_compare import simulate, bootstrap

class AccountingTests(unittest.TestCase):
    def test_first_year_zero_market_return(self):
        stats,h=simulate(np.zeros((1,12,7)))
        last=h[-1]
        self.assertAlmostEqual(last[1],2905.95)
        self.assertAlmostEqual(last[2],2898)
        self.assertAlmostEqual(last[3],55.95*1.03)
        self.assertAlmostEqual(last[4],48*1.03)
        self.assertAlmostEqual(last[5],2905.95-55.95*1.03)
        self.assertAlmostEqual(last[6],2898-48*1.03)
    def test_second_year_pool_transfer_not_double_counted(self):
        _,h=simulate(np.zeros((1,24,7)))
        self.assertAlmostEqual(h[-1][2],2795.58)
        self.assertAlmostEqual(h[-1][4],(48*1.03+47.58)*1.03)
    def test_surplus_repays_debt_before_reinvestment(self):
        r=np.zeros((1,24,7)); r[0,0,4]=4
        _,h=simulate(r,interest=0)
        self.assertAlmostEqual(h[-1][4],0)
        self.assertAlmostEqual(h[-1][2],5*2592+306-150-48)
    def test_same_paths_for_both_strategies_and_repeatable(self):
        a=np.arange(120*7).reshape(120,7)
        x=bootstrap(a,n=5,years=2)
        np.testing.assert_array_equal(x,bootstrap(a,n=5,years=2))
        self.assertTrue(np.all(x[:,:,1]-x[:,:,0]==1))
    def test_zero_return_reveals_debt_risk(self):
        s,_=simulate(np.zeros((1,480,7)))
        self.assertEqual(s[0]['cross50_pct'],100)
        self.assertEqual(s[1]['cross50_pct'],100)

if __name__=='__main__': unittest.main()

