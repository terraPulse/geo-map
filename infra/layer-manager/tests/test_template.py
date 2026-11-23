import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra" / "layer-manager"
SCRIPTS = INFRA / "scripts"


class CfnLoader(yaml.SafeLoader):
    pass


def _cfn(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


CfnLoader.add_multi_constructor("!", _cfn)


def load(name):
    return yaml.load((INFRA / name).read_text(encoding="utf-8"), Loader=CfnLoader)


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = load("template.yaml")
        self.bootstrap = load("bootstrap-artifact-bucket.yaml")
        self.text = (INFRA / "template.yaml").read_text(encoding="utf-8")

    def test_account_region_and_isolation(self):
        rules = self.template["Rules"]["AuthorizedTarget"]["Assertions"]
        joined = json.dumps(rules)
        self.assertIn("544020760996", joined)
        self.assertIn("us-west-2", joined)
        resources = "\n".join(
            resource["Type"] for resource in self.template["Resources"].values() if "Type" in resource
        )
        self.assertNotIn("Route53", resources)
        self.assertNotIn("AWS::S3::BucketWebsite", self.text)
        defaults = json.dumps({key: value.get("Default", "") for key, value in self.template["Parameters"].items()})
        self.assertNotIn("admin.terrapulse.com", defaults)
        self.assertNotIn("geo-map-tiles", defaults)
        self.assertNotIn("map-tiles-dev", defaults)
        self.assertNotIn("s3:DeleteObject", self.text)
        self.assertNotIn("dynamodb:DeleteItem", self.text)
        self.assertNotIn("dynamodb:Scan", self.text)

    def test_api_is_authenticated_and_cors_is_explicit(self):
        route = self.template["Resources"]["ApiRoute"]["Properties"]
        self.assertEqual(route["AuthorizationType"], "JWT")
        self.assertEqual(route["RouteKey"], "ANY /v1/{proxy+}")
        options = self.template["Resources"]["OptionsRoute"]["Properties"]
        self.assertEqual(options["AuthorizationType"], "NONE")
        self.assertEqual(options["RouteKey"], "OPTIONS /v1/{proxy+}")
        self.assertNotIn("AuthorizerId", options)
        origins = self.template["Resources"]["HttpApi"]["Properties"]["CorsConfiguration"]["AllowOrigins"]
        self.assertNotIn("*", origins)
        self.assertIn("Distribution.DomainName", str(origins[0]))
        user_pool = self.template["Resources"]["UserPool"]["Properties"]
        self.assertTrue(user_pool["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"])
        self.assertEqual(user_pool["MfaConfiguration"], "ON")
        self.assertNotIn("AWS::Cognito::UserPoolUser", self.text)

    def test_tile_backend_is_optional_and_logs_are_bounded(self):
        backend = self.template["Parameters"]["TileBackendBaseUrl"]
        self.assertEqual(backend["Default"], "")
        self.assertEqual(self.template["Parameters"]["TilePathOrder"]["Default"], "map")
        self.assertEqual(self.template["Resources"]["ApiLogGroup"]["Properties"]["RetentionInDays"], 14)
        log_format = self.template["Resources"]["ApiStage"]["Properties"]["AccessLogSettings"]["Format"]
        self.assertNotIn("authorization", log_format.lower())
        self.assertNotIn("jwt", log_format.lower())
        env = self.template["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
        self.assertEqual(env["LAYER_MANAGER_SEED_FIXTURES"], "0")
        self.assertEqual(env["LAYER_MANAGER_ALLOW_FIXTURE_AUTH"], "0")
        role = json.dumps(self.template["Resources"]["ApiRole"])
        self.assertNotIn("s3:", role)

    def test_bootstrap_bucket_is_private_and_named(self):
        bucket = self.bootstrap["Resources"]["ArtifactBucket"]["Properties"]
        block = bucket["PublicAccessBlockConfiguration"]
        self.assertTrue(all(block.values()))
        self.assertIn("AWS::AccountId", str(bucket["BucketName"]))
        self.assertIn("544020760996", json.dumps(self.bootstrap["Rules"]))

    def test_package_contains_code_and_not_the_console_catalog(self):
        import sys

        sys.path.insert(0, str(SCRIPTS))
        import package_lambda
        import package_site

        with tempfile.TemporaryDirectory() as tmp:
            archive = package_lambda.build(Path(tmp) / "lambda.zip")
            site = package_site.build(Path(tmp) / "site")
            names = zipfile.ZipFile(archive).namelist()
            self.assertIn("layer_manager_lambda.py", names)
            self.assertIn("layer_manager/synthetic_fixtures.json", names)
            self.assertTrue(all(not name.startswith("ui/") for name in names))
            self.assertFalse((site / "config.js").exists())
            self.assertTrue((site / "index.html").is_file())
            rendered = __import__("render_config").render(
                {
                    "HttpApiEndpoint": "https://abc.execute-api.us-west-2.amazonaws.com",
                    "UserPoolClientId": "public-client",
                    "HostedUiBaseUrl": "https://example.auth.us-west-2.amazoncognito.com",
                    "DistributionDomainName": "d111111abcdef8.cloudfront.net",
                    "TileBackendBaseUrl": "",
                    "TilePathOrder": "map",
                }
            )
            self.assertIn('"integrated": false', rendered)
            self.assertIn('"baseUrl": null', rendered)


if __name__ == "__main__":
    unittest.main()
