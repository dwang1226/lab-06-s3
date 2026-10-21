#!/bin/bash
set -euo pipefail

#check for three arguments
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <book-url> <bucket-name> <expires-in-seconds>" >&2
    exit 1
fi

URL="$1"
BUCKET="$2"
EXPIRES="$3"
FILENAME="$(basename "$URL")"

#download the book into books/
mkdir -p books
curl --fail --location --output "books/$FILENAME" "$URL"

#create the bucket unless it already exists
if ! aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    aws s3 mb "s3://$BUCKET"
fi

#upload the book
aws s3 cp "books/$FILENAME" "s3://$BUCKET/$FILENAME" --content-type "text/plain; charset=utf-8"

#presign a url to the book and print it
aws s3 presign "s3://$BUCKET/$FILENAME" --expires-in "$EXPIRES"