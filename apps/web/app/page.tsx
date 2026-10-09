"use client";

import { useState } from "react";
import type { FormEvent } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Organization = { id: string; name: string };
type Project = { id: string; name: string; organization_id: string };
type AuthResponse = {
  access_token: string;
  organizations: Organization[];
};

export default function Home() {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ id: string; filename: string; size_bytes: number; status: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadProjects(orgId: string, accessToken: string) {
    const response = await fetch(`${API_BASE}/organizations/${orgId}/projects`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) throw new Error(await response.text());
    const projectList = (await response.json()) as Project[];
    setProjects(projectList);
    setProjectId(projectList[0]?.id ?? "");
  }

  async function handleAuth(event: FormEvent) {
    event.preventDefault();
    setError(null);
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
      setOrganizations(data.organizations);
      const firstOrganizationId = data.organizations[0]?.id ?? "";
      setOrganizationId(firstOrganizationId);
      if (firstOrganizationId) await loadProjects(firstOrganizationId, data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleOrganizationChange(nextOrganizationId: string) {
    setOrganizationId(nextOrganizationId);
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
    if (!token || !organizationId) return;
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/organizations/${organizationId}/projects`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
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
    setResult(null);
    if (!token || !projectId || !file) {
      setError("Choose a project and file.");
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
      const uploaded = (await response.json()) as {
        id: string;
        filename: string;
        size_bytes: number;
        status: string;
      };
      setResult(uploaded);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    setToken(null);
    setOrganizations([]);
    setOrganizationId("");
    setProjects([]);
    setProjectId("");
    setPassword("");
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-bold">AtlasOps — Document Upload</h1>

      {!token ? (
        <form onSubmit={handleAuth} className="flex flex-col gap-4 w-full max-w-md">
          <h2 className="text-lg font-semibold">{registering ? "Create an account" : "Sign in"}</h2>
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="border rounded px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">Password</span>
            <input
              type="password"
              required
              minLength={registering ? 12 : 1}
              maxLength={128}
              autoComplete={registering ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="border rounded px-3 py-2"
            />
          </label>
          {registering && (
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium">Organization</span>
              <input
                required
                maxLength={200}
                value={organizationName}
                onChange={(event) => setOrganizationName(event.target.value)}
                className="border rounded px-3 py-2"
              />
            </label>
          )}
          <button type="submit" disabled={loading} className="bg-black text-white rounded px-4 py-2 disabled:opacity-50">
            {loading ? "Please wait..." : registering ? "Create account" : "Sign in"}
          </button>
          <button type="button" onClick={() => setRegistering(!registering)} className="text-sm underline">
            {registering ? "Already have an account? Sign in" : "Create an account"}
          </button>
        </form>
      ) : (
        <section className="flex flex-col gap-5 w-full max-w-md">
          <div className="flex justify-end">
            <button type="button" onClick={logout} className="text-sm underline">Sign out</button>
          </div>
          {organizations.length > 1 && (
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium">Organization</span>
              <select
                value={organizationId}
                onChange={(event) => void handleOrganizationChange(event.target.value)}
                className="border rounded px-3 py-2"
              >
                {organizations.map((organization) => (
                  <option key={organization.id} value={organization.id}>{organization.name}</option>
                ))}
              </select>
            </label>
          )}

          <form onSubmit={handleCreateProject} className="flex gap-2">
            <input
              required
              maxLength={200}
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="New project name"
              className="border rounded px-3 py-2 flex-1"
            />
            <button type="submit" disabled={loading || !organizationId} className="border rounded px-3 py-2 disabled:opacity-50">
              Create project
            </button>
          </form>

          <form onSubmit={handleUpload} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium">Project</span>
              <select
                required
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                className="border rounded px-3 py-2"
              >
                <option value="" disabled>Select a project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium">File</span>
              <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="border rounded px-3 py-2" />
            </label>
            <button type="submit" disabled={loading} className="bg-black text-white rounded px-4 py-2 disabled:opacity-50">
              {loading ? "Uploading..." : "Upload"}
            </button>
          </form>
        </section>
      )}

      {error && <p role="alert" className="text-red-600">{error}</p>}
      {result && (
        <div className="border rounded p-4 w-full max-w-md">
          <p className="font-semibold text-green-700">Status: {result.status}</p>
          <p>Filename: {result.filename}</p>
          <p>Size: {result.size_bytes} bytes</p>
          <p className="text-xs text-gray-500 break-all">ID: {result.id}</p>
        </div>
      )}
    </main>
  );
}
