import asyncio
import io
import json
import os
import uuid
from datetime import datetime

import boto3
from aiokafka import AIOKafkaConsumer
from dotenv import load_dotenv
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api import models
from apps.api.database import Base

load_dotenv()

REDPANDA_BOOTSTRAP = os.getenv("REDPANDA_BOOTSTRAP", "localhost:19092")
DATABASE_URL = os.getenv("DATABASE_URL")

S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

s3_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name="us-east-1",
)

MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))

    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        pages.append(page_text)

    return "\n\n".join(pages).strip()


def chunk_text(text_content: str) -> list[str]:
    text_content = " ".join(text_content.split())

    if not text_content:
        return []

    chunks = []
    start = 0

    while start < len(text_content):
        end = min(start + CHUNK_SIZE, len(text_content))
        chunk = text_content[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text_content):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def process_document(document_id: str):
    db = SessionLocal()
    try:
        document = db.query(models.Document).filter(models.Document.id == uuid.UUID(document_id)).first()

        if not document:
            print(f"Document {document_id} not found")
            return

        content_type = document.content_type or ""

        if content_type != "application/pdf" and not document.filename.lower().endswith(".pdf"):
            print(
                f"Skipping {document.filename}: "
                "PDF processing is currently supported only for this milestone."
            )
            return

        print(f"Downloading {document.filename} from MinIO...")

        response = s3_client.get_object(
            Bucket=S3_BUCKET,
            Key=document.storage_key,
        )

        file_bytes = response["Body"].read()

        print(f"Extracting text from {document.filename}...")

        extracted_text = extract_pdf_text(file_bytes)

        if not extracted_text:
            raise ValueError("No extractable text found in PDF")

        chunks = chunk_text(extracted_text)

        if not chunks:
            raise ValueError("PDF produced no usable text chunks")

        print(f"Created {len(chunks)} chunks")

        embeddings = model.encode(
            chunks,
            normalize_embeddings=True,
        )

        # Delete existing chunks
        db.query(models.Chunk).filter(models.Chunk.document_id == document.id).delete()

        # Add new chunks with embeddings
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_obj = models.Chunk(
                id=uuid.uuid4(),
                document_id=document.id,
                chunk_index=index,
                content=chunk,
                embedding=embedding.tolist(),
            )
            db.add(chunk_obj)

        # Update document status
        document.is_indexed = True
        document.indexed_at = datetime.utcnow()
        
        db.commit()

        print(
            f"Document {document_id} processed successfully: "
            f"{len(chunks)} chunks and embeddings stored."
        )

    except Exception as exc:
        print(f"Error processing document {document_id}: {exc}")
        document = db.query(models.Document).filter(models.Document.id == uuid.UUID(document_id)).first()
        if document:
            document.status = "error"
            db.commit()
        raise
    finally:
        db.close()


async def consume():
    consumer = AIOKafkaConsumer(
        "document.uploaded",
        bootstrap_servers=REDPANDA_BOOTSTRAP,
        group_id="atlasops-document-processor",
        auto_offset_reset="earliest",
    )

    await consumer.start()

    print(
        f"Consumer started, listening on {REDPANDA_BOOTSTRAP} "
        "for topic 'document.uploaded'..."
    )

    try:
        async for msg in consumer:
            document_id = None
            try:
                event = json.loads(msg.value.decode("utf-8"))
                document_id = event.get("document_id")

                if not document_id:
                    print(f"Event missing document_id: {event}")
                    continue

                print(f"Received event: {event}")

                process_document(document_id)

            except Exception as exc:
                print(f"Error processing event: {exc}")

                if document_id:
                    db = SessionLocal()
                    try:
                        document = db.query(models.Document).filter(
                            models.Document.id == uuid.UUID(document_id)
                        ).first()
                        if document:
                            document.status = "error"
                            db.commit()
                    finally:
                        db.close()

    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(consume())
