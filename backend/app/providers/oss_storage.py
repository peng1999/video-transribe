import os
import uuid
from pathlib import Path

import boto3
from botocore.config import Config


class OSSConfigError(RuntimeError):
    pass


def _get_client():
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    access_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    endpoint = os.getenv("S3_ENDPOINT")
    region = os.getenv("S3_REGION", "garage")
    if not all([access_key, access_secret, endpoint]):
        raise OSSConfigError("S3 credentials/endpoint are required")

    session = boto3.session.Session()
    return session.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=access_secret,
        config=Config(s3={"addressing_style": "path"}),
    )


def upload_audio_and_sign_url(audio_path: Path, job_id: str) -> str:
    """Upload audio to S3-compatible storage and return a signed URL."""
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise OSSConfigError("S3_BUCKET is required")

    client = _get_client()
    object_name = f"{job_id}-{uuid.uuid4().hex}{audio_path.suffix}"
    client.upload_file(str(audio_path), bucket, object_name)

    expires = int(os.getenv("S3_SIGN_EXPIRE_SECONDS", "3600"))
    presigned = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_name},
        ExpiresIn=expires,
    )
    public_endpoint = os.getenv("S3_PUBLIC_ENDPOINT")
    if public_endpoint:
        from urllib.parse import urlsplit, urlunsplit

        pe = urlsplit(public_endpoint)
        pu = urlsplit(presigned)
        presigned = urlunsplit(
            (
                pe.scheme or pu.scheme,
                pe.netloc or pu.netloc,
                pu.path,
                pu.query,
                pu.fragment,
            )
        )
    return presigned
