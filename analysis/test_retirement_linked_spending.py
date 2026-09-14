import unittest
import numpy as np
from retirement_linked_spending import simulate_linked

class LinkedSpendingTests(unittest.TestCase):
    def test_first_year_same_spending_only_ret1_borrows(self):
        s,h,a=simulate_linked(np.zeros((1,12,7)))
        self.assertAlmostEqual(a[0][1],102)
        self.assertAlmostEqual(a[0][3],7.95)
        self.assertAlmostEqual(h[-1][3],7.95*1.03)
        self.assertAlmostEqual(h[-1][4],2898-7.95*.03)
        self.assertAlmostEqual(h[-1][5],2898)
        self.assertEqual(s['peak_debt_ret5'],0)
    def test_zero_return_no_interest_equal_net_wealth(self):
        _,h,_=simulate_linked(np.zeros((1,480,7)),interest=0)
        np.testing.assert_allclose(np.array(h)[:,4],np.array(h)[:,5],atol=1e-8)
    def test_below_dividend_surplus_pays_down_existing_debt(self):
        r=np.zeros((1,36,7));r[0,0,4]=-.8
        _,h,a=simulate_linked(r,interest=0)
        self.assertLess(a[1][1],a[1][2])
        self.assertAlmostEqual(a[1][4],7.95)
        self.assertAlmostEqual(a[1][5],0)
        self.assertAlmostEqual(a[1][3],0)
    def test_consumption_above150_not_capped(self):
        r=np.zeros((1,24,7));r[0,0,4]=4
        s,h,a=simulate_linked(r)
        self.assertGreater(a[1][1],150)
        self.assertAlmostEqual(a[1][3],a[1][1]-a[1][2])
    def test_interest_only_affects_retirement1(self):
        r=np.zeros((1,120,7))
        _,h1,a1=simulate_linked(r,interest=.01)
        _,h2,a2=simulate_linked(r,interest=.05)
        np.testing.assert_allclose(np.array(h1)[:,5],np.array(h2)[:,5])
        np.testing.assert_allclose(np.array(a1)[:,1],np.array(a2)[:,1])
        self.assertGreater(h2[-1][3],h1[-1][3])

if __name__=='__main__': unittest.main()
