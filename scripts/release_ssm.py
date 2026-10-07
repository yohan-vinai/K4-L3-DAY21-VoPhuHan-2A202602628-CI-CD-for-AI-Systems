import os
import shlex
import sys

import boto3
from botocore.exceptions import WaiterError


def main() -> int:
    region = os.environ["AWS_REGION"]
    instance_id = os.environ["EC2_INSTANCE_ID"]
    bucket = os.environ["ARTIFACT_BUCKET"]

    commands = [
        "set -eu",
        "mkdir -p /home/ubuntu/income-api/src",
        "aws --region {region} s3 cp s3://{bucket}/artifacts/current/serve.py /home/ubuntu/income-api/src/serve.py".format(
            region=shlex.quote(region), bucket=shlex.quote(bucket)
        ),
        "aws --region {region} s3 cp s3://{bucket}/artifacts/current/__init__.py /home/ubuntu/income-api/src/__init__.py".format(
            region=shlex.quote(region), bucket=shlex.quote(bucket)
        ),
        "sudo systemctl restart income-api",
        "for attempt in $(seq 1 12); do "
        "if curl --fail --silent http://localhost:8080/healthz; then "
        "echo 'Health check passed.'; exit 0; fi; sleep 5; done; "
        "echo 'Health check failed after 60 seconds.'; exit 1",
    ]

    ssm = boto3.client("ssm", region_name=region)
    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands},
        Comment="Deploy quality-gated income model and restart API",
        TimeoutSeconds=180,
    )
    command_id = response["Command"]["CommandId"]
    waiter = ssm.get_waiter("command_executed")

    try:
        waiter.wait(
            CommandId=command_id,
            InstanceId=instance_id,
            WaiterConfig={"Delay": 5, "MaxAttempts": 40},
        )
    except WaiterError:
        invocation = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id,
        )
        print(invocation.get("StandardOutputContent", ""))
        print(invocation.get("StandardErrorContent", ""), file=sys.stderr)
        raise

    invocation = ssm.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id,
    )
    print(invocation.get("StandardOutputContent", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
