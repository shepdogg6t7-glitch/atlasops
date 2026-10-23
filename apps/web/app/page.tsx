"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : null);

const TOKEN_KEY = "atlasops_access_token";

const SAMPLE_QUESTIONS = [
  "What happens when a critical incident is reported?",
  "How long are database backups kept?",
  "What should be checked before a document migration?",
];

const SAMPLE_PASSAGES = [
  {
    document: "Incident response playbook",
    page: 4,
    excerpt:
      "For a Sev 1 incident, the incident commander pages the primary on-call engineer immediately. If there is no acknowledgement within five minutes, page the backup engineer and notify the operations lead.",
    keywords: ["incident", "severity", "sev", "critical", "on-call", "oncall", "page", "acknowledgement", "escalation"],
  },
  {
    document: "Incident response playbook",
    page: 6,
    excerpt:
      "The incident commander posts an initial status update within 15 minutes, then shares updates every 30 minutes until service is restored. Record decisions and timestamps in the incident log.",
    keywords: ["incident", "commander", "status", "update", "minutes", "restore", "log", "decision"],
  },
  {
    document: "Data retention policy",
    page: 2,
    excerpt:
      "Automated database backups are retained for 30 days. Monthly archives are kept for one year. Restoration requests must be approved by the data owner and recorded in the change log.",
    keywords: ["database", "backup", "retention", "restore", "restoration", "archive", "data", "days", "year"],
  },
  {
    document: "Document migration checklist",
    page: 1,
    excerpt:
      "Before migrating a document collection, confirm the destination bucket, verify checksums for the source files, and run a small test batch. Keep the source read-only until the migrated sample has been reviewed.",
    keywords: ["document", "migration", "migrating", "bucket", "checksum", "source", "destination", "test", "batch", "files"],
  },
];

type DemoPassage = (typeof SAMPLE_PASSAGES)[number] & { score: number };
type Organization = { id: string; name: string };
type Project = { id: string; name: string; organization_id: string };
type AuthResponse = {
  access_token: string;
  organizations: Organization[];
};
type DocumentRecord = {
  id: string;
  filename: string;
  size_bytes: number;
  status: string;
  is_indexed: boolean;
};
type SearchResult = {
  chunk_id: string;
  document_id: string;
  filename: string;
  chunk_index: number;
  text: string;
  similarity_score: number;
};

function findSamplePassages(query: string): DemoPassage[] {
  const words = query.toLowerCase().match(/[a-z0-9-]+/g) ?? [];
  const ignored = new Set(["a", "an", "and", "are", "for", "how", "is", "of", "our", "the", "to", "what", "when", "where", "which", "who", "with"]);
  const terms = words.filter((word) => word.length > 2 && !ignored.has(word));

  return SAMPLE_PASSAGES
    .map((passage) => ({
      ...passage,
      score: terms.filter((term) =>
        passage.keywords.some((keyword) => keyword.includes(term) || term.includes(keyword)),
      ).length,
    }))
    .filter((passage) => passage.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 3);
}

function statusLabel(document: DocumentRecord): string {
  if (document.status === "indexed" || document.is_indexed) return "Indexed";
  if (document.status === "uploaded") return "Indexing";
  if (document.status === "error") return "Error";
  return document.status;
}

function statusColor(status: string, isIndexed: boolean): string {
  if (status === "indexed" || isIndexed) return "text-emerald-700 bg-emerald-50 border-emerald-100";
  if (status === "error") return "text-red-700 bg-red-50 border-red-100";
  return "text-blue-700 bg-blue-50 border-blue-100";
}

export default function Home() {
  const [view, setView] = useState<"home" | "demo" | "auth">("home");
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [token, setToken] = useState<string | null>(() => {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
});
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [uploadResult, setUploadResult] = useState<DocumentRecord | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [query, setQuery] = useState(SAMPLE_QUESTIONS[0]);
  const [demoResults, setDemoResults] = useState<DemoPassage[] | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!token || organizationId) return;
    (async () => {
      try {
        const response = await fetch(`${API_BASE}/organizations`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Could not load organizations.");
        const list = (await response.json()) as Organization[];
        setOrganizations(list);
        if (list[0]) {
          setOrganizationId(list[0].id);
          await loadProjects(list[0].id, token);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load organizations.");
      }
    })();
  }, [token, organizationId]);

  const stopPolling = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  async function loadProjects(orgId: string, accessToken: string) {
    if (!API_BASE) throw new Error("Live API is not configured for this deployment.");
    const response = await fetch(`${API_BASE}/organizations/${orgId}/projects`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error(await response.text());
    const projectList = (await response.json()) as Project[];
    setProjects(projectList);
    if (!projectId || !projectList.find((project) => project.id === projectId)) {
      setProjectId(projectList[0]?.id ?? "");
    }
  }

  async function loadDocuments() {
    if (!token || !projectId || !API_BASE) return;
    setDocumentsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/projects/${projectId}/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(await response.text());
      setDocuments((await response.json()) as DocumentRecord[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load documents.");
    } finally {
      setDocumentsLoading(false);
    }
  }

  useEffect(() => {
    const indexing = documents.some((document) => document.status === "uploaded");
    if (indexing && projectId) {
      timerRef.current = setInterval(loadDocuments, 2000);
    } else {
      stopPolling();
    }
    return stopPolling;
  }, [documents, projectId]);

  async function handleAuth(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!API_BASE) {
      setError("Live sign-in is not connected on this demo deployment. You can still try the interactive demo.");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/auth/${registering ? "register" : "login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          registering
            ? { email, password, organization_name: organizationName }
            : { email, password },
        ),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as AuthResponse;
      setToken(data.access_token);
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setOrganizations(data.organizations);
      const firstOrganizationId = data.organizations[0]?.id ?? "";
      setOrganizationId(firstOrganizationId);
      setView("home");
      if (firstOrganizationId) await loadProjects(firstOrganizationId, data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    stopPolling();
    setToken(null);
    localStorage.removeItem(TOKEN_KEY);
    setOrganizations([]);
    setOrganizationId("");
    setProjects([]);
    setProjectId("");
    setDocuments([]);
    setProjectName("");
    setFile(null);
    setFileInputKey((key) => key + 1);
    setUploadResult(null);
    setSearchResults(null);
    setSearchQuery("");
    setPassword("");
    setError(null);
    setView("home");
  }

  async function handleOrganizationChange(nextOrganizationId: string) {
    setOrganizationId(nextOrganizationId);
    setProjectId("");
    setDocuments([]);
    if (!token) return;
    setError(null);
    try {
      await loadProjects(nextOrganizationId, token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load projects.");
    }
  }

  async function handleCreateProject(event: FormEvent) {
    event.preventDefault();
    if (!token || !organizationId || !API_BASE) return;
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/organizations/${organizationId}/projects`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: projectName }),
      });
      if (!response.ok) throw new Error(await response.text());
      const project = (await response.json()) as Project;
      setProjects((current) => [...current, project]);
      setProjectId(project.id);
      setProjectName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project creation failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setUploadResult(null);
    if (!token || !projectId || !file || !API_BASE) {
      setError("Choose a project and PDF file.");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/projects/${projectId}/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!response.ok) throw new Error(await response.text());
      const result = (await response.json()) as DocumentRecord;
      setUploadResult(result);
      setFile(null);
      setFileInputKey((key) => key + 1);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setSearchError(null);
    setSearchResults(null);
    if (!token || !projectId || !searchQuery.trim() || !API_BASE) {
      setSearchError("Choose a project and enter a question.");
      return;
    }

    setSearchLoading(true);
    try {
      const response = await fetch(`${API_BASE}/projects/${projectId}/search`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: searchQuery, limit: 10 }),
      });
      if (!response.ok) throw new Error(await response.text());
      setSearchResults((await response.json()) as SearchResult[]);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearchLoading(false);
    }
  }

  function searchDemo(event: FormEvent) {
    event.preventDefault();
    setDemoResults(findSamplePassages(query));
  }

  return (
    <main className="min-h-screen bg-[#f6f8fb] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <button type="button" onClick={() => setView("home")} className="flex items-center gap-3 text-left">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-700 text-sm font-bold text-white">
              A
            </span>
            <span className="text-lg font-semibold tracking-tight">AtlasOps</span>
          </button>
          <nav className="flex items-center gap-3">
            {!token && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setView("demo");
                    setDemoResults(findSamplePassages(SAMPLE_QUESTIONS[0]));
                  }}
                  className="hidden rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 sm:inline-flex"
                >
                  Try the demo
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setView("auth");
                  }}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
                >
                  Sign in
                </button>
              </>
            )}
            {token && (
              <>
                <button type="button" onClick={logout} className="text-sm font-medium text-slate-600 hover:text-slate-900">
                  Sign out
                </button>
              </>
            )}
          </nav>
        </div>
      </header>

      {!token && view === "home" && (
        <section className="mx-auto grid max-w-6xl gap-12 px-6 py-16 md:grid-cols-[1.05fr_0.95fr] md:items-center md:py-24">
          <div>
            <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-800">
              <span className="h-2 w-2 rounded-full bg-blue-600" />
              Private document intelligence
            </p>
            <h1 className="max-w-xl text-4xl font-semibold leading-tight tracking-tight text-slate-950 sm:text-5xl">
              Find the answer hiding in your documents.
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-8 text-slate-600">
              Bring your team&apos;s PDFs together and ask useful questions in plain language.
              AtlasOps helps you find the passages that matter.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => {
                  setView("demo");
                  setDemoResults(findSamplePassages(SAMPLE_QUESTIONS[0]));
                }}
                className="rounded-xl bg-blue-700 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-800"
              >
                Try the interactive demo
              </button>
              <button
                type="button"
                onClick={() => {
                  setError(null);
                  setView("auth");
                }}
                className="rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Sign in to your workspace
              </button>
            </div>
            <p className="mt-4 text-sm text-slate-500">No account or upload required to explore the demo.</p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-200/60 sm:p-7">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">Operations knowledge base</p>
                <p className="mt-1 text-xs text-slate-500">3 sample documents · 4 sample passages</p>
              </div>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">Ready</span>
            </div>
            <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Ask your documents</p>
              <p className="mt-3 text-sm leading-6 text-slate-800">What happens when a critical incident is reported?</p>
            </div>
            <div className="mt-5 rounded-xl border border-blue-100 bg-blue-50/70 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-slate-900">Incident response playbook</p>
                <span className="text-xs text-slate-500">Page 4</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                For a Sev 1 incident, the incident commander pages the primary on-call engineer immediately...
              </p>
              <p className="mt-3 text-xs font-medium text-blue-800">Sample passage · demo preview</p>
            </div>
          </div>
        </section>
      )}

      {!token && view === "demo" && (
        <section className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
          <button type="button" onClick={() => setView("home")} className="mb-6 text-sm font-medium text-slate-600 hover:text-slate-900">
            ← Back to overview
          </button>
          <div className="grid gap-6 lg:grid-cols-[0.72fr_1.28fr]">
            <aside className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Interactive demo</p>
                  <h1 className="mt-2 text-xl font-semibold tracking-tight">Operations knowledge base</h1>
                </div>
                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">Sample data</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Ask a question and explore matching passages from a small, bundled sample corpus.
              </p>
              <div className="mt-6">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Sample documents</p>
                <ul className="space-y-2">
                  {[
                    ["Incident response playbook", "12 pages"],
                    ["Data retention policy", "6 pages"],
                    ["Document migration checklist", "3 pages"],
                  ].map(([name, pages]) => (
                    <li key={name} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2.5">
                      <span className="text-sm font-medium text-slate-800">{name}</span>
                      <span className="shrink-0 text-xs text-slate-500">{pages}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-3.5">
                <p className="text-xs font-semibold text-amber-900">Demo mode</p>
                <p className="mt-1 text-xs leading-5 text-amber-800">
                  Results come from bundled sample text and keyword matching. No account, upload, live API, or AI search is used.
                </p>
              </div>
            </aside>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
              <form onSubmit={searchDemo}>
                <label htmlFor="demo-query" className="block text-sm font-semibold text-slate-900">
                  Ask a question
                </label>
                <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                  <input
                    id="demo-query"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    maxLength={300}
                    placeholder="e.g. How long are database backups kept?"
                    className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none ring-blue-600 transition focus:ring-2"
                  />
                  <button
                    type="submit"
                    disabled={!query.trim()}
                    className="rounded-xl bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                  >
                    Search samples
                  </button>
                </div>
              </form>

              <div className="mt-5">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Try asking</p>
                <div className="flex flex-wrap gap-2">
                  {SAMPLE_QUESTIONS.map((question) => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => {
                        setQuery(question);
                        setDemoResults(findSamplePassages(question));
                      }}
                      className="rounded-full border border-slate-200 px-3 py-1.5 text-left text-xs text-slate-700 hover:border-blue-300 hover:bg-blue-50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-8 border-t border-slate-100 pt-6">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-slate-900">
                    {demoResults === null ? "Sample results" : `Matching passages (${demoResults.length})`}
                  </h2>
                  <span className="text-xs text-slate-500">Bundled demo corpus</span>
                </div>
                {demoResults === null ? (
                  <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                    Search a question above to explore matching sample passages.
                  </p>
                ) : demoResults.length === 0 ? (
                  <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                    No sample passage matched those words. Try one of the suggested questions.
                  </p>
                ) : (
                  <ul className="mt-4 space-y-3">
                    {demoResults.map((result) => (
                      <li key={`${result.document}-${result.page}`} className="rounded-xl border border-slate-200 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">{result.document}</p>
                          <span className="text-xs text-slate-500">Page {result.page}</span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-slate-700">{result.excerpt}</p>
                        <p className="mt-3 text-xs font-medium text-blue-700">Sample match · {result.score} matching terms</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="mt-7 flex flex-col justify-between gap-3 rounded-xl bg-slate-900 p-4 text-white sm:flex-row sm:items-center">
                <div>
                  <p className="text-sm font-semibold">Ready to use your own documents?</p>
                  <p className="mt-1 text-xs text-slate-300">Connect to a configured AtlasOps API to upload and search real PDFs.</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setView("auth");
                  }}
                  className="shrink-0 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100"
                >
                  Sign in
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {!token && view === "auth" && (
        <section className="mx-auto max-w-lg px-6 py-12">
          <button type="button" onClick={() => setView("home")} className="mb-6 text-sm font-medium text-slate-600 hover:text-slate-900">
            ← Back to overview
          </button>
          <form onSubmit={handleAuth} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">AtlasOps workspace</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">{registering ? "Create an account" : "Sign in"}</h1>
            {!API_BASE && (
              <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm leading-5 text-amber-900">
                Live API access is not configured on this deployment. The interactive demo is ready to try without an account.
              </p>
            )}
            <div className="mt-6 flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">Email</span>
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-600"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">Password</span>
                <input
                  type="password"
                  required
                  minLength={registering ? 12 : 1}
                  maxLength={128}
                  autoComplete={registering ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-600"
                />
              </label>
              {registering && (
                <label className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium">Organization</span>
                  <input
                    required
                    maxLength={200}
                    value={organizationName}
                    onChange={(event) => setOrganizationName(event.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-600"
                  />
                </label>
              )}
              <button
                type="submit"
                disabled={loading || !API_BASE}
                className="rounded-lg bg-blue-700 px-4 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {loading ? "Please wait..." : registering ? "Create account" : "Sign in"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setError(null);
                  setRegistering(!registering);
                }}
                className="text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                {registering ? "Already have an account? Sign in" : "Create an account"}
              </button>
            </div>
          </form>
        </section>
      )}

      {token && (
        <section className="mx-auto max-w-6xl px-6 py-10">
          <div className="flex items-center justify-between mb-8">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Workspace</p>
              <h1 className="mt-2 text-2xl font-semibold">Your documents</h1>
            </div>
            <button type="button" onClick={logout} className="text-sm font-medium text-slate-600 hover:text-slate-900">
              Sign out
            </button>
          </div>

          {error && (
            <div role="alert" className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-[1.4fr_2.6fr]">
            <aside className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex flex-col gap-4">
                <label className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium">Organization</span>
                  {organizations.length > 1 ? (
                    <select
                      value={organizationId}
                      onChange={(event) => void handleOrganizationChange(event.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
                    >
                      {organizations.map((organization) => (
                        <option key={organization.id} value={organization.id}>{organization.name}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="rounded-lg border border-slate-300 bg-slate-50 px-3 py-2.5 text-sm text-slate-500">
                      {organizations[0]?.name ?? "No organization"}
                    </span>
                  )}
                </label>
                <form onSubmit={handleCreateProject} className="flex flex-col gap-3">
                  <label className="flex flex-col gap-1.5">
                    <span className="text-sm font-medium">New project</span>
                    <input
                      required
                      maxLength={200}
                      value={projectName}
                      onChange={(event) => setProjectName(event.target.value)}
                      placeholder="Project name"
                      className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={loading || !organizationId}
                    className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold disabled:opacity-50"
                  >
                    Create project
                  </button>
                </form>
                {projects.length === 0 && organizationId && (
                  <p className="mt-4 text-xs text-slate-500">No projects yet. Create one above to start uploading PDFs.</p>
                )}
                {projects.length > 0 && (
                  <div className="mt-4 flex flex-col gap-2">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Projects</p>
                    {projects.map((project) => (
                      <button
                        key={project.id}
                        type="button"
                        onClick={() => {
                          setProjectId(project.id);
                          setDocuments([]);
                        }}
                        className={`w-full text-left rounded-lg px-3 py-2.5 text-sm border ${
                          projectId === project.id
                            ? "border-blue-300 bg-blue-50 text-blue-900 font-medium"
                            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        {project.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </aside>

            {!projectId ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
                <p className="text-sm font-medium text-slate-900">Select a project, or create one.</p>
                <p className="mt-1 text-xs text-slate-500">Projects hold your PDFs and their search index.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Project · {projects.find((p) => p.id === projectId)?.name}</p>
                    <h2 className="mt-1 text-lg font-semibold">Documents</h2>
                  </div>
                </div>

                <form onSubmit={handleUpload} className="mb-6 flex flex-col gap-4 border border-slate-200 rounded-xl p-5 sm:p-6">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="flex flex-col gap-1.5">
                      <span className="text-sm font-medium">PDF document</span>
                      <input
                        key={fileInputKey}
                        type="file"
                        accept="application/pdf,.pdf"
                        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                        className="block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
                      />
                    </label>
                    <div className="flex items-end">
                      <button
                        type="submit"
                        disabled={loading || !file}
                        className="rounded-lg bg-blue-700 px-4 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                      >
                        {loading ? "Uploading…" : "Upload PDF"}
                      </button>
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">PDF files up to 25 MB. Text extraction and embedding happen in the background after upload.</p>
                </form>

                {uploadResult && (
                  <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
                    <p className="font-semibold text-emerald-900">Upload received · {statusLabel(uploadResult)}</p>
                    <p className="mt-1 text-emerald-800">
                      {uploadResult.filename} · {uploadResult.size_bytes} bytes
                    </p>
                  </div>
                )}

                <div className="rounded-xl border border-slate-200 bg-white">
                  <div className="border-b border-slate-100 px-5 py-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      {documents.length} document{documents.length !== 1 ? "s" : ""}
                      {documentsLoading ? ` · ${documents.some((d) => d.status === "uploaded") ? "indexing…" : ""}` : ""}
                    </p>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {documents.length === 0 ? (
                      <div className="px-5 py-8 text-center">
                        <p className="text-sm text-slate-500">No documents yet. Upload a PDF above.</p>
                      </div>
                    ) : (
                      documents.map((document) => (
                        <div key={document.id} className="px-5 py-3.5 flex items-center justify-between gap-3 sm:px-6">
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium text-slate-900 truncate">{document.filename}</p>
                            <p className="text-xs text-slate-500">{document.size_bytes} bytes</p>
                          </div>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(document.status, document.is_indexed)}`}
                          >
                            {statusLabel(document)}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <form onSubmit={handleSearch} className="mt-8 flex flex-col gap-4 border border-slate-200 rounded-xl p-5 sm:p-6">
                  <div>
                    <label className="block text-sm font-semibold text-slate-900">Search your documents</label>
                    <p className="mt-1 text-xs text-slate-500">Ask in plain language; results are ranked by semantic similarity.</p>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-3">
                    <input
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      placeholder="e.g. how are database backups retained?"
                      className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-600"
                    />
                    <button
                      type="submit"
                      disabled={searchLoading || !searchQuery.trim()}
                      className="rounded-xl bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                    >
                      {searchLoading ? "Searching…" : "Search"}
                    </button>
                  </div>
                  {searchError && (
                    <p className="text-sm text-red-700">{searchError}</p>
                  )}
                  {searchLoading && !searchResults && (
                    <p className="text-sm text-slate-500">Embedding your question and ranking passages…</p>
                  )}
                </form>

                {searchResults !== null && (
                  <div className="mt-6 space-y-3">
                    <h2 className="text-sm font-semibold text-slate-900">
                      Matching passages ({searchResults.length})
                    </h2>
                    {searchResults.length === 0 ? (
                      <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                        No relevant passages found. Try rephrasing your question.
                      </p>
                    ) : (
                      searchResults.map((result) => (
                        <div key={result.chunk_id} className="rounded-xl border border-slate-200 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                            <p className="text-sm font-semibold text-slate-900 truncate">{result.filename}</p>
                            <span className="text-xs text-slate-500">Chunk {result.chunk_index + 1}</span>
                            <span
                              className="rounded-full px-2 py-0.5 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-100"
                            >
                              {(result.similarity_score * 100).toFixed(0)}% match
                            </span>
                          </div>
                          <p className="text-sm leading-6 text-slate-700">{result.text}</p>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      )}

      {error && (
        <div role="alert" className="mx-auto mb-8 max-w-2xl px-6 text-sm text-red-700">
          {error}
        </div>
      )}
    </main>
  );
}
