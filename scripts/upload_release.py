import os
import sys

import boto3


def main() -> int:
    bucket = os.environ["ARTIFACT_BUCKET"]
    s3 = boto3.client("s3")
    release_files = {
        "release-bundle/models/model.joblib": "artifacts/current/model.joblib",
        "release-bundle/src/serve.py": "artifacts/current/serve.py",
        "release-bundle/src/__init__.py": "artifacts/current/__init__.py",
    }

    for local_path, object_key in release_files.items():
        s3.upload_file(local_path, bucket, object_key)

    return 0


if __name__ == "__main__":
    sys.exit(main())
