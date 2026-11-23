#!/usr/bin/env python3
"""Check the caller's account, region, and CLI profile before a human deploys.

By default this script does not call AWS. The parent readiness executor may
pass --call-sts after review. The CLI profile is tp. That name is not the
IAM user name. Account 544020760996 and region us-west-2 are required.
Profile 6g is refused. Profile mfeng is not a configured CLI profile.
"""

import argparse
import json
import os
import sys

EXPECTED_ACCOUNT = "544020760996"
EXPECTED_REGION = "us-west-2"
EXPECTED_PROFILE = "tp"
REFUSED_PROFILES = ("6g", "mfeng")


def evaluate(profile: str, region: str, identity: dict | None) -> list[str]:
    """Check CLI profile, region, and account. The ARN user or role name is not compared to the profile."""
    errors = []
    if profile in REFUSED_PROFILES or profile.startswith("6g"):
        if profile == "mfeng" or profile.startswith("mfeng"):
            errors.append(
                "CLI profile mfeng is not configured. Use --profile tp. "
                "The IAM user name does not have to equal the CLI profile name."
            )
        else:
            errors.append("Refusing CLI profile 6g. Use --profile tp.")
    elif profile != EXPECTED_PROFILE:
        errors.append(
            "CLI profile must be tp. The profile name is not an IAM user name."
        )
    if region != EXPECTED_REGION:
        errors.append(f"Region must be {EXPECTED_REGION}.")
    if identity is not None:
        account = str(identity.get("Account", ""))
        arn = str(identity.get("Arn", ""))
        if account != EXPECTED_ACCOUNT:
            errors.append(f"Account must be {EXPECTED_ACCOUNT}.")
        if f":{EXPECTED_ACCOUNT}:" not in arn and not arn.endswith(f":{EXPECTED_ACCOUNT}"):
            errors.append("Caller ARN is not in account 544020760996.")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preflight the staging deploy identity. Network is off unless --call-sts is set.")
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "")))
    parser.add_argument("--identity-json", help="Caller identity JSON. Use this in tests. No network.")
    parser.add_argument("--call-sts", action="store_true", help="Call STS. The implementation agent must not set this.")
    args = parser.parse_args(argv)
    identity = None
    if args.identity_json:
        identity = json.loads(args.identity_json)
    elif args.call_sts:
        if args.profile != EXPECTED_PROFILE:
            print("Refusing STS call unless --profile tp is explicit.", file=sys.stderr)
            return 2
        import boto3

        session = boto3.Session(profile_name=args.profile, region_name=EXPECTED_REGION)
        identity = session.client("sts").get_caller_identity()
    errors = evaluate(args.profile, args.region, identity)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if identity is None and not args.call_sts:
        print(
            "CLI profile tp and region us-west-2 match the expected local settings. "
            "STS was not called, so the account was not checked. "
            "Re-run with --call-sts before deploy. "
            "The IAM principal name does not need to equal the CLI profile name."
        )
        return 0
    print(json.dumps({"account": identity.get("Account"), "arn": identity.get("Arn"), "region": args.region}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
