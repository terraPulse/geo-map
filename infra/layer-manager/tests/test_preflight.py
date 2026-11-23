import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preflight_identity.py"
SPEC = importlib.util.spec_from_file_location("preflight_identity", SCRIPT)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_profile_tp_accepts_a_different_iam_name(self):
        identity = {"Account": "544020760996", "Arn": "arn:aws:iam::544020760996:user/mfeng"}
        self.assertEqual(preflight.evaluate("tp", "us-west-2", identity), [])

    def test_assumed_role_in_the_account_is_accepted(self):
        identity = {
            "Account": "544020760996",
            "Arn": "arn:aws:sts::544020760996:assumed-role/Deployer/session",
        }
        self.assertEqual(preflight.evaluate("tp", "us-west-2", identity), [])

    def test_mfeng_and_6g_profiles_are_refused(self):
        identity = {"Account": "544020760996", "Arn": "arn:aws:iam::544020760996:user/mfeng"}
        mfeng = preflight.evaluate("mfeng", "us-west-2", identity)
        self.assertTrue(any("not configured" in item for item in mfeng))
        refused = preflight.evaluate("6g", "us-west-2", identity)
        self.assertTrue(any("6g" in item for item in refused))

    def test_wrong_account_is_refused_even_with_profile_tp(self):
        identity = {"Account": "000000000000", "Arn": "arn:aws:iam::000000000000:user/tp"}
        errors = preflight.evaluate("tp", "us-west-2", identity)
        self.assertTrue(any("544020760996" in item for item in errors))

    def test_wrong_region_is_refused(self):
        errors = preflight.evaluate("tp", "us-east-1", None)
        self.assertTrue(any("us-west-2" in item for item in errors))

    def test_operations_use_profile_tp(self):
        text = Path(__file__).resolve().parents[3].joinpath("management/docs/operations.md").read_text(encoding="utf-8")
        self.assertIn("--profile tp", text)
        self.assertNotIn("--profile mfeng", text)
        self.assertIn("tp-geomap-layers-544020760996", text)
        self.assertIn("lambda/layer-manager-lambda.zip", text)


if __name__ == "__main__":
    unittest.main()
