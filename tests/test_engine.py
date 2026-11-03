import unittest
from api.engine import analyze, verify
P = {"description":"Reduce Starter price from $29.90 to $19.90","type":"pricing","entity":"Starter","old_value":"$29.90","new_value":"$19.90","scenario":"pricing-incomplete"}
class EngineTests(unittest.TestCase):
    def test_pre_change(self):
        self.assertEqual({x["route"] for x in analyze(P)["related_pages"]}, {"/", "/pricing", "/faq", "/resources", "/contact", "/integrations"})
    def test_incomplete(self):
        self.assertTrue(any(f["route"] == "/faq" and f["status"] == "needs_review" for f in verify(P)["findings"]))
    def test_complete(self):
        self.assertEqual(verify({**P, "scenario": "pricing-complete"})["decision"], "no_detected_blockers")
    def test_nav(self):
        self.assertTrue(any(f["category"] == "navigation" for f in verify({"description":"Simplify navigation","type":"navigation","scenario":"navigation-removed"})["findings"]))
    def test_selective(self):
        self.assertNotIn("accessibility", verify(P)["analysis_categories"])
if __name__ == "__main__":
    unittest.main()
