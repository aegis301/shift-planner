export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function messageFromDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (first && typeof first === "object" && "msg" in first && first.msg != null) {
      return String(first.msg);
    }
  }
  return `API request failed: ${status}`;
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  const detail =
    body && typeof body === "object" && body !== null && "detail" in body
      ? (body as { detail: unknown }).detail
      : body;
  return new ApiError(response.status, messageFromDetail(detail, response.status), detail);
}
