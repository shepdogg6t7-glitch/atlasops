import asyncio
import json
import os
from aiokafka import AIOKafkaConsumer
from sqlalchemy import text, create_engine
from dotenv import load_dotenv

load_dotenv()

REDPANDA_BOOTSTRAP = os.getenv("REDPANDA_BOOTSTRAP", "localhost:19092")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)


async def consume():
    consumer = AIOKafkaConsumer(
        "document.uploaded",
        bootstrap_servers=REDPANDA_BOOTSTRAP,
        group_id="atlasops-document-processor",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    print(f"Consumer started, listening on {REDPANDA_BOOTSTRAP} for topic 'document.uploaded'...")
    try:
        async for msg in consumer:
            event = json.loads(msg.value.decode("utf-8"))
            document_id = event.get("document_id")
            print(f"Received event: {event}")

            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE documents SET status = 'processed' WHERE id = :id"),
                    {"id": document_id},
                )
            print(f"Document {document_id} status updated to 'processed'")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(consume())
