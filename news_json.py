import json
import uuid
import boto3
import time
import logging
from datetime import datetime
from pymongo import MongoClient
from botocore.exceptions import ClientError
from news_summary import extract_text_from_url, summarize_article, classify_news
import os

from google.cloud import secretmanager

def get_secret(secret_id, project_id, version_id="latest"):
    """
    讀取指定 secret_id 的秘密 
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
AWS_REGION = 'us-east-2'
QUEUE_NAME = 'test-queue'
DB_NAME = "newsDB"
COLLECTION_NAME = "news"


project_id = "jon-backend"  

# Secret Manager read secrets
mongo_uri = get_secret("MONGO_URI", project_id)
aws_access_key_id = get_secret("AWS_ACCESS_KEY_ID", project_id)
aws_secret_access_key = get_secret("AWS_SECRET_ACCESS_KEY", project_id)

# MongoDB Setup
client = MongoClient(mongo_uri)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# SQS client with credentials from Secret Manager
sqs = boto3.client(
    "sqs",
    region_name=AWS_REGION,
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key
)

def get_queue_url(queue_name):
    """Returns SQS queue URL"""
    try:
        response = sqs.get_queue_url(QueueName=queue_name)
        return response['QueueUrl']
    except ClientError as e:
        logger.error(f"Error getting queue URL: {e}")
        raise

def process_news(news_event):
    """Processes a single news JSON object into GeoJSON format and stores in MongoDB."""
    news_url = news_event.get("url")
    title = news_event.get("title", "Untitled News")

    if not news_url or not isinstance(news_url, str):
        logger.warning(f"Invalid URL: {news_url}")
        return None

    extracted_text = extract_text_from_url(news_url)
    if extracted_text in ["Content extraction failed.", "Failed to fetch the article."]:
        logger.warning(f"Error processing URL: {news_url}")
        return None

    summary = summarize_article(extracted_text)
    category = classify_news(summary)
    news_id = str(uuid.uuid4())

    coordinates = [-74.006, 40.7128]  # Default: New York

    geojson_news = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": coordinates
                },
                "properties": {
                    "title": title,
                    "summary": summary,
                    "link": news_url,
                    "category": category
                }
            }
        ]
    }

    inserted = collection.insert_one(geojson_news)
    geojson_news["_id"] = str(inserted.inserted_id)
    logger.info(f"Stored news: {title}")
    return geojson_news

def consume_messages(queue_url, max_messages=10, wait_time=20, visibility_timeout=30):
    """Continuously consumes and processes messages from SQS."""
    logger.info(f"Listening to SQS queue: {QUEUE_NAME}")
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time,
                VisibilityTimeout=visibility_timeout,
                MessageAttributeNames=["All"]
            )

            messages = response.get("Messages", [])
            if not messages:
                logger.info("No messages received. Polling again...")
                continue

            for message in messages:
                raw_body = message.get("Body", "")
                if not raw_body.strip():
                    logger.warning("Skipped empty message.")
                    continue

                try:
                    parsed_body = json.loads(raw_body)
                    if isinstance(parsed_body, list):
                        for item in parsed_body:
                            process_news(item)
                    else:
                        process_news(parsed_body)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e} — Raw: {raw_body}")

                receipt_handle = message["ReceiptHandle"]
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                logger.info(f"Deleted message: {message.get('MessageId', 'N/A')}")

        except KeyboardInterrupt:
            logger.info("Consumer stopped by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        queue_url = get_queue_url(QUEUE_NAME)
        consume_messages(queue_url)
    except Exception as e:
        logger.critical(f"Failed to start consumer: {e}")
