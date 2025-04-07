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
    讀取指定 secret_id 的秘密 hihi
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
    

# Constants
AWS_REGION = 'us-east-2'
QUEUE_NAME = 'test-queue'
DB_NAME = "sqsMessagesDB"
COLLECTION_NAME = "raw_messages"


project_id = "jon-backend"  

# Secret Manager read secrets
mongo_uri = get_secret("MONGO_URI", project_id)
aws_access_key_id = get_secret("AWS_ACCESS_KEY_ID", project_id)
aws_secret_access_key = get_secret("AWS_SECRET_ACCESS_KEY", project_id)

# MongoDB Setup
client = MongoClient(mongo_uri)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_queue_url(queue_name, create_if_not_exists=True):
    region_name = 'us-east-2'
    sqs = boto3.client('sqs', region_name=region_name)
    try:
        response = sqs.get_queue_url(QueueName=queue_name)
        logger.info(f"Found existing queue: {queue_name}")
        return response['QueueUrl']
    except ClientError as e:
        if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue' and create_if_not_exists:
            logger.info(f"Queue {queue_name} does not exist. Creating it...")
            response = sqs.create_queue(QueueName=queue_name)
            logger.info(f"Successfully created queue: {queue_name}")
            return response['QueueUrl']
        else:
            logger.error(f"Error getting queue URL: {e}")
            raise


from news_summary import extract_text_from_url, summarize_article, classify_news

def process_message(message):
    message_id = message.get('MessageId', 'unknown')
    receipt_handle = message.get('ReceiptHandle')

    try:
        body = message.get('Body', '{}')
        attributes = message.get('MessageAttributes', {})
        attribute_values = {k: v.get('StringValue') for k, v in attributes.items()}

        try:
            body_json = json.loads(body)
            logger.info(f"Processing JSON message: {message_id}")
        except json.JSONDecodeError:
            body_json = {"raw_text": body}
            logger.info(f"Processing plain text message: {message_id}")

        title = body_json.get("title", "Untitled News")
        url = body_json.get("url")

        # Only extract summary + category if URL is valid
        if url and isinstance(url, str):
            extracted_text = extract_text_from_url(url)
            summary = summarize_article(extracted_text)
            category = classify_news(summary)
        else:
            summary = "No summary available"
            category = "Uncategorized"
            url = "N/A"

        coordinates = [-74.006, 40.7128]

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
                        "density" : 5,
                        "message_id": message_id,
                        "title": title,
                        "summary": summary,
                        "link": url,
                        "category": category,
                        "attributes": attribute_values,
                        "timestamp": time.time()
                    }
                }
            ]
        }

        collection.insert_one(geojson_news)
        logger.info(f"Stored message {message_id} in MongoDB")

        return geojson_news, receipt_handle

    except Exception as e:
        logger.error(f"Error processing message {message_id}: {e}")
        return None, receipt_handle


def delete_message(queue_url, receipt_handle):
    region_name = 'us-east-2'
    sqs = boto3.client('sqs', region_name=region_name)
    try:
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle
        )
        return True
    except ClientError as e:
        logger.error(f"Error deleting message: {e}")
        return False


def consume_messages(queue_name, max_messages=10, wait_time=20, visibility_timeout=30):
    queue_url = get_queue_url(queue_name)
    logger.info(f"Consuming messages from {queue_name}")

    region_name = 'us-east-2'
    sqs = boto3.client('sqs', region_name=region_name)

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time,
                VisibilityTimeout=visibility_timeout,
                MessageAttributeNames=['All']
            )

            messages = response.get('Messages', [])
            if not messages:
                logger.info("No messages received. Continuing to poll...")
                continue

            logger.info(f"Received {len(messages)} messages")

            for message in messages:
                geojson_result, receipt_handle = process_message(message)
                if geojson_result and receipt_handle:
                    deleted = delete_message(queue_url, receipt_handle)
                if deleted:
                    logger.info(f"Deleted message {message.get('MessageId')}")
                else:
                    logger.warning(f"Failed to delete message {message.get('MessageId')}")


        except KeyboardInterrupt:
            logger.info("Stopping consumer...")
            break

        except Exception as e:
            logger.error(f"Error in message consumption loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    QUEUE_NAME = 'test-queue'
    MAX_MESSAGES = 5
    WAIT_TIME = 20
    VISIBILITY_TIMEOUT = 60

    logger.info(f"Starting SQS consumer for queue {QUEUE_NAME}")
    consume_messages(
        queue_name=QUEUE_NAME,
        max_messages=MAX_MESSAGES,
        wait_time=WAIT_TIME,
        visibility_timeout=VISIBILITY_TIMEOUT
    )
