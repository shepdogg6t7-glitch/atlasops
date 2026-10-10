"use client";

import { type FormEvent, useState } from "react";

type UploadResult = {
  id: string;
  filename: string;
  size_bytes: number;
  status: string;
};

type AnswerSource = {
  chunk_id: string;
  filename: string;
  chunk_index: number;
  text: string;
  similarity_score: number;
};

type AnswerResult = {
  answer: string;
  sources: AnswerSource[];
};

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

async function getErrorMessage(response: Response) {
  const payload = await response.json().catch(() => null);
  return (
    payload?.detail ??
    `Request failed with status ${response.status}`
  );
}

export default function Home() {
  const [projectId, setProjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [answerResult, setAnswerResult] = useState<AnswerResult | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError(null);
    setUploadResult(null);

    if (!projectId || !file) {
      setUploadError("Enter a project ID and choose a file.");
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(
        `${API_BASE}/projects/${projectId}/documents`,
        { method: "POST", body: formData },
      );
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      setUploadResult((await response.json()) as UploadResult);
    } catch (error: unknown) {
      setUploadError(
        error instanceof Error ? error.message : "Upload failed.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAskError(null);
    setAnswerResult(null);

    if (!projectId || !question.trim()) {
      setAskError("Enter a project ID and a question.");
      return;
    }

    setAsking(true);
    try {
      const response = await fetch(
        `${API_BASE}/projects/${projectId}/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: question.trim() }),
        },
      );
      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }
      setAnswerResult((await response.json()) as AnswerResult);
    } catch (error: unknown) {
      setAskError(
        error instanceof Error ? error.message : "Could not answer question.",
      );
    } finally {
      setAsking(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center gap-8 p-8">
      <header className="w-full max-w-2xl">
        <h1 className="text-3xl font-bold">AtlasOps</h1>
        <p className="mt-2 text-gray-600">
          Upload PDFs and ask questions about indexed project documents.
        </p>
      </header>

      <section className="w-full max-w-2xl rounded-lg border p-6">
        <h2 className="text-xl font-semibold">Project</h2>
        <label className="mt-4 flex flex-col gap-1">
          <span className="text-sm font-medium">Project ID</span>
          <input
            type="text"
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            placeholder="Paste project UUID here"
            className="rounded border px-3 py-2"
          />
        </label>
      </section>

      <section className="w-full max-w-2xl rounded-lg border p-6">
        <h2 className="text-xl font-semibold">Upload a PDF</h2>
        <form onSubmit={handleUpload} className="mt-4 flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">File</span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="rounded border px-3 py-2"
            />
          </label>
          <button
            type="submit"
            disabled={uploading}
            className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
          >
            {uploading ? "Uploading..." : "Upload PDF"}
          </button>
        </form>

        {uploadError && (
          <p role="alert" className="mt-4 text-red-600">
            {uploadError}
          </p>
        )}
        {uploadResult && (
          <div className="mt-4 rounded border p-4">
            <p className="font-semibold text-green-700">
              Status: {uploadResult.status}
            </p>
            <p>Filename: {uploadResult.filename}</p>
            <p>Size: {uploadResult.size_bytes} bytes</p>
            <p className="break-all text-xs text-gray-500">
              ID: {uploadResult.id}
            </p>
          </div>
        )}
      </section>

      <section className="w-full max-w-2xl rounded-lg border p-6">
        <h2 className="text-xl font-semibold">Ask your documents</h2>
        <form onSubmit={handleAsk} className="mt-4 flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">Question</span>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="What do my documents say about..."
              className="rounded border px-3 py-2"
            />
          </label>
          <p className="text-sm text-gray-600">
            Your question and matching document excerpts are sent to Google
            Gemini to generate an answer. Do not use confidential documents
            unless that data handling is acceptable.
          </p>
          <button
            type="submit"
            disabled={asking}
            className="rounded bg-black px-4 py-2 text-white disabled:opacity-50"
          >
            {asking ? "Searching documents..." : "Ask"}
          </button>
        </form>

        {askError && (
          <p role="alert" className="mt-4 text-red-600">
            {askError}
          </p>
        )}
        {answerResult && (
          <div className="mt-4 space-y-4 rounded border p-4">
            <div>
              <h3 className="font-semibold">Answer</h3>
              <p className="mt-2 whitespace-pre-wrap">{answerResult.answer}</p>
            </div>
            {answerResult.sources.length > 0 && (
              <div>
                <h3 className="font-semibold">Sources</h3>
                <ul className="mt-2 list-inside list-disc space-y-2">
                  {answerResult.sources.map((source) => (
                    <li key={source.chunk_id}>
                      <span className="font-medium">
                        {source.filename}, chunk {source.chunk_index + 1}
                      </span>
                      <p className="ml-5 text-sm text-gray-600">
                        {source.text}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
