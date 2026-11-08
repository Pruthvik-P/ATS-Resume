import type {
  ChangeDecisionResponse,
  JDAnalysisResponse,
  JobRead,
  ResumeRead,
  ScoreReport,
} from "@/lib/api-types";

const API_ROOT = "/api/backend";

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(
    message: string,
    options: { code?: string; status?: number; details?: unknown } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code ?? "api_error";
    this.status = options.status ?? 0;
    this.details = options.details;
  }
}

async function readError(response: Response): Promise<ApiError> {
  let body: ErrorEnvelope | null = null;
  try {
    body = (await response.json()) as ErrorEnvelope;
  } catch {
    // Next.js may return HTML for a framework-level error. Keep the status.
  }

  return new ApiError(
    body?.error?.message ??
      `The engine returned HTTP ${response.status}. Check the API logs for details.`,
    {
      code: body?.error?.code ?? `http_${response.status}`,
      status: response.status,
      details: body?.error?.details,
    },
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      cache: "no-store",
      ...init,
      headers: {
        accept: "application/json",
        ...init.headers,
      },
    });
  } catch (error) {
    throw new ApiError(
      "Could not reach the local engine. Check that the FastAPI server is running.",
      {
        code: "network_error",
        details: error instanceof Error ? error.message : undefined,
      },
    );
  }

  if (!response.ok) {
    throw await readError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function uploadResume(file: File): Promise<ResumeRead> {
  const form = new FormData();
  form.append("file", file);

  return request<ResumeRead>("/resumes", {
    method: "POST",
    body: form,
  });
}

export function createJd(text: string): Promise<JDAnalysisResponse> {
  return request<JDAnalysisResponse>("/jds", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export function createScore(
  resumeId: string,
  jdId: string,
): Promise<ScoreReport> {
  return request<ScoreReport>("/score", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId, jd_id: jdId }),
  });
}

export function createOptimise(
  resumeId: string,
  jdId: string,
): Promise<JobRead> {
  return request<JobRead>("/optimise", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId, jd_id: jdId }),
  });
}

export function getJob(jobId: string): Promise<JobRead> {
  return request<JobRead>(`/jobs/${encodeURIComponent(jobId)}`);
}

export function decideChange(
  jobId: string,
  changeId: string,
  status: "accepted" | "rejected",
): Promise<ChangeDecisionResponse> {
  return request<ChangeDecisionResponse>(
    `/jobs/${encodeURIComponent(jobId)}/changes/${encodeURIComponent(changeId)}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
}

export function jobEventsUrl(jobId: string): string {
  return `${API_ROOT}/jobs/${encodeURIComponent(jobId)}/events`;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
