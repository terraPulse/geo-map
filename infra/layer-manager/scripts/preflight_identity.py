#!/usr/bin/env python3
"""Check the caller's account, region, and profile before a human deploys.

By default this script does not call AWS. The parent readiness executor may
pass --call-sts after review. Profile 6g is refused. The expected profile
is mfeng, the account is 544020760996, and the region is us-west-2.
"""

import argparse
import json
import os
import sys

EXPECTED_ACCOUNT = "544020760996"
EXPECTED_REGION = "us-west-2"
EXPECTED_PROFILE = "mfeng"
REFUSED_PROFILE = "6g"


def evaluate(profile: str, region: str, identity: dict | None) -> list[str]:
    errors = []
    if profile == REFUSED_PROFILE or profile.startswith(REFUSED_PROFILE):
        errors.append("Refusing profile 6g.")
    if profile != EXPECTED_PROFILE:
        errors.append(f"Profile must be {EXPECTED_PROFILE}.")
    if region != EXPECTED_REGION:
        errors.append(f"Region must be {EXPECTED_REGION}.")
    if identity is not None:
        if str(identity.get("Account")) != EXPECTED_ACCOUNT:
            errors.append(f"Account must be {EXPECTED_ACCOUNT}.")
        arn = str(identity.get("Arn", ""))
        if EXPECTED_ACCOUNT not in arn:
            errors.append("Caller ARN is not in the authorized account.")
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
            print("Refusing STS call unless --profile mfeng is explicit.", file=sys.stderr)
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
            "Identity preflight is structurally valid for profile mfeng in us-west-2. "
            "STS was not called. The parent executor must re-run with --call-sts before deploy."
        )
        return 0
    print(json.dumps({"account": identity.get("Account"), "arn": identity.get("Arn"), "region": args.region}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
