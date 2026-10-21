#!/usr/bin/env python3
"""download books listed in book_urls.txt, create a public bucket, upload the books and index.html to it, and make the bucket publicly readable"""
import json
import logging
import os
import sys
import time
import boto3
import requests
from botocore.exceptions import ClientError

#logger setup
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

#create S3 client 
s3 = boto3.client("s3", region_name="us-east-1")

def parse_args():
    """read the command line arguments and return tuple (list_file, index_path, bucket) as strings"""
    if len(sys.argv) < 4:
        log.error("Usage: stage_books.py <list_file> <index_path> <bucket>")
        sys.exit(1)
    list_file = sys.argv[1]
    index_path = sys.argv[2]
    bucket = sys.argv[3]
    return (list_file, index_path, bucket)

def download_books(list_file, dest_dir):
    """download every book listed in list_file into dest_dir and return list of local paths of the books that are available"""
    os.makedirs(dest_dir, exist_ok=True)
    #read the URLs, skip blank lines
    try:
        with open(list_file) as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as e:
        log.error(f"Could not read {list_file}: {e}")
        return []

    paths = []
    for url in urls:
        #save under the last part of the URL
        path = os.path.join(dest_dir, url.rsplit("/", 1)[-1])
        if os.path.exists(path):
            log.info(f"Already downloaded, skipping: {path}")
            paths.append(path)
            continue
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as f:
                f.write(response.content)
            log.info(f"Downloaded {url} -> {path}")
            paths.append(path)
        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")
        time.sleep(1)
    log.info(f"{len(paths)} of {len(urls)} books available locally")
    return paths

def create_bucket(bucket):
    """create bucket and return true if exists and false if it doesnt exist"""
    #head_bucket succeeds if the bucket exists and we can access it
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket {bucket} exists")
        return True
    except ClientError:
        log.info(f"Bucket {bucket} does not exist")

    #us-east-1 needs no LocationConstraint
    try:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket {bucket}")
        return True
    except ClientError as e:
        log.error(f"Could not create bucket {bucket}: {e}")
        return False

def make_public(bucket):
    """turn off Block Public Access and attach a public-read bucket policy. return true if success and false if not"""
    #the policy is rejected unless Block Public Access is off first
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        log.info(f"Block Public Access turned off for {bucket}")

        #allow anyone to read objects
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info(f"Public read policy attached to {bucket}")
        return True
    except ClientError as e:
        log.error(f"Could not make bucket {bucket} public: {e}")
        return False

def upload_files(bucket, file_paths):
    """loop over file_paths and upload each file to the top level of the bucket, using the file name as the key. return the number of files uploaded successfully"""
    count = 0
    for path in file_paths:
        key = os.path.basename(path)
        try:
            with open(path, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="text/plain; charset=utf-8",
                )
            log.info(f"Uploaded {path} -> s3://{bucket}/{key}")
            count += 1
        except ClientError as e:
            log.error(f"Error uploading {path}: {e}")
    log.info(f"Uploaded {count} of {len(file_paths)} books")
    return count

def upload_index(bucket, index_path):
    """upload the index page as index.html with a text/html content type and return true on success or false otherwise"""
    try:
        with open(index_path, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key="index.html",
                Body=f,
                ContentType="text/html",
            )
        log.info(f"Uploaded {index_path} -> s3://{bucket}/index.html")
        return True
    except FileNotFoundError:
        log.error(f"Index file not found: {index_path}")
        return False
    except ClientError as e:
        log.error(f"Error uploading {index_path}: {e}")
        return False

def main():
    """download the books, create the bucket and make it public, then upload everything"""
    list_file, index_path, bucket = parse_args()

    # step 1 - get books locally
    books = download_books(list_file, "books")
    if not books:
        log.error("No books downloaded. Ending.")
        sys.exit(1)

    # step 2 - create bucket and make it publicly readable
    if not create_bucket(bucket):
        sys.exit(1)
    if not make_public(bucket):
        sys.exit(1)

    # step 3 - upload the books and index page
    uploaded = upload_files(bucket, books)
    index_ok = upload_index(bucket, index_path)

    # report outcome
    if uploaded == len(books) and index_ok:
        log.info("Success. Search collection at:")
    else:
        log.error("Finished with errors. Index page would be at:")
    log.info(f"https://{bucket}.s3.amazonaws.com/index.html")


if __name__ == "__main__":
    main()
