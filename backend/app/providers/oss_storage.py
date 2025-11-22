import os
import uuid
from pathlib import Path

import oss2


class OSSConfigError(RuntimeError):
    pass


def _get_bucket():
    access_key = os.getenv("OSS_ACCESS_KEY_ID")
    access_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    endpoint = os.getenv("OSS_ENDPOINT")
    bucket_name = os.getenv("OSS_BUCKET")
    if not all([access_key, access_secret, endpoint, bucket_name]):
        raise OSSConfigError("OSS credentials/endpoint/bucket are required")
    auth = oss2.Auth(access_key, access_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)


def upload_audio_and_sign_url(audio_path: Path, job_id: str) -> str:
    """Upload audio to OSS and return a signed HTTPS URL for temporary access."""
    bucket = _get_bucket()
    prefix = os.getenv("OSS_PREFIX", "transcribe/")
    object_name = f"{prefix.rstrip('/')}/{job_id}-{uuid.uuid4().hex}{audio_path.suffix}"
    bucket.put_object_from_file(object_name, str(audio_path))
    expires = int(os.getenv("OSS_SIGN_EXPIRE_SECONDS", "3600"))
    return bucket.sign_url("GET", object_name, expires)
