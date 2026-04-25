"""Upload a file to Cloudflare R2 using S3-compatible API."""
import os
import sys
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url="https://8296802a8e82f8aeb71d92251662cf9d.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", "d017eab3e9bf90c9d30d7b2f9abb0cc5"),
    aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", "cc4ca53011a323f139c6d4b2947652515a7f10c02d57f04be75be9bcbd043c45"),
    region_name="auto",
)

BUCKET = "hermes-downloads"

def upload(local_path, remote_key):
    print(f"[UPLOAD] {local_path} -> {remote_key}")
    s3.upload_file(local_path, BUCKET, remote_key)
    print(f"[OK] Uploaded: https://dl.hermdash.com/{remote_key}")

if __name__ == "__main__":
    # Usage: python upload_to_r2.py <local_path> <remote_key>
    upload(sys.argv[1], sys.argv[2])
