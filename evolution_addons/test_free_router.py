import unittest
from evolution_addons.free_router import eligible, select_free_models, NoFreeModel

class FreeRouterTests(unittest.TestCase):
    def test_free_tools(self):
        m={'id':'example:free','pricing':{'prompt':'0','completion':'0'},'supported_parameters':['tools']}
        self.assertTrue(eligible(m))
        self.assertEqual(select_free_models([m,m]),['example:free'])
    def test_paid_rejected(self):
        m={'id':'example:free','pricing':{'prompt':'0','completion':'0.001'},'supported_parameters':['tools']}
        self.assertFalse(eligible(m))
        with self.assertRaises(NoFreeModel): select_free_models([m])
    def test_missing_price_rejected(self):
        self.assertFalse(eligible({'id':'x:free','pricing':{'prompt':'0'},'supported_parameters':['tools']}))
    def test_no_tools_rejected(self):
        self.assertFalse(eligible({'id':'x:free','pricing':{'prompt':'0','completion':'0'}}))
    def test_nonfree_id_rejected(self):
        self.assertFalse(eligible({'id':'x','pricing':{'prompt':'0','completion':'0'},'supported_parameters':['tools']}))
if __name__ == '__main__': unittest.main()
