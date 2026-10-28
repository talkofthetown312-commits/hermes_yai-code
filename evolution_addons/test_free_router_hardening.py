import unittest
from evolution_addons.free_router import eligible
B={"id":"x:free","pricing":{"prompt":"0","completion":"0"},"supported_parameters":["tools"]}
class Hardening(unittest.TestCase):
 def test_request(self): self.assertFalse(eligible({**B,"pricing":{**B["pricing"],"request":"0.1"}}))
 def test_tools(self):
  for x in ("tools",{},True,123,[None]): self.assertFalse(eligible({**B,"supported_parameters":x}))
 def test_prices(self):
  for x in (True,"NaN","Infinity",[],{}): self.assertFalse(eligible({**B,"pricing":{"prompt":x,"completion":"0"}}))
 def test_unknown(self): self.assertFalse(eligible({**B,"pricing":{**B["pricing"],"unknown":"0"}}))
