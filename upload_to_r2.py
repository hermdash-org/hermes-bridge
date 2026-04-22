"""Upload built runtime to Cloudflare R2"""
import boto3
import sys
import os

def upload_to_r2(file_path, bucket_name, object_name):
    """Upload file to R2 bucket using environment variables"""
    account_id = os.environ['CF_ACCOUNT_ID']
    access_key = os.environ['R2_ACCESS_KEY_ID']
    secret_key = os.environ['R2_SECRET_ACCESS_KEY']
    endpoint_url = f'https://{account_id}.r2.cloudflarestorage.com'
    
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    
    print(f"Uploading {file_path} to R2 as {object_name}...")
    s3.upload_file(file_path, bucket_name, object_name)
    print(f"Uploaded successfully to {bucket_name}/{object_name}")

if __name__ == "__main__":
    file_path = sys.argv[1]
    bucket_name = sys.argv[2]
    object_name = sys.argv[3]
    
    upload_to_r2(file_path, bucket_name, object_name)
