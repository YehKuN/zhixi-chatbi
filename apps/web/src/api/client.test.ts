import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthSession, writeAuthSession } from "@/lib/authStorage";
import { requestBinary, requestJson } from "./client";

describe("requestJson", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuthSession();
  });

  it("returns data from a successful envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          data: { id: "session_1" },
          request_id: "req_1",
          error: null,
        }),
      ),
    );

    await expect(requestJson<{ id: string }>("/sessions")).resolves.toEqual({ id: "session_1" });
  });

  it("throws a typed error for a failed envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          {
            data: null,
            request_id: "req_2",
            error: {
              code: "VALIDATION_ERROR",
              message: "Request validation failed",
              details: {},
            },
          },
          { status: 422 },
        ),
      ),
    );

    await expect(requestJson("/sessions")).rejects.toMatchObject({
      code: "VALIDATION_ERROR",
      requestId: "req_2",
    });
  });

  it("uses JSON headers by default and preserves custom headers", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      Response.json({ data: null, request_id: "req_3", error: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await requestJson("/datasources", {
      headers: { "x-request-source": "datasources-view" },
    });

    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("Expected requestJson to call fetch");
    }
    const headers = new Headers(call[1]?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-request-source")).toBe("datasources-view");
  });

  it("does not set a JSON content type for FormData uploads", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      Response.json({ data: null, request_id: "req_4", error: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const body = new FormData();
    body.append("file", new Blob(["id,name\\n1,Ada\\n"], { type: "text/csv" }), "people.csv");
    await requestJson("/datasources", { method: "POST", body });

    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("Expected requestJson to call fetch");
    }
    const headers = new Headers(call[1]?.headers);
    expect(headers.has("content-type")).toBe(false);
  });

  it("attaches the bearer token from the stored auth session", async () => {
    writeAuthSession({
      token: "token_123",
      user: {
        id: "user_1",
        username: "admin",
        display_name: "管理员",
        role: "enterprise_admin",
        created_at: "2026-11-05T00:00:00Z",
      },
      enterprise: {
        code: "ZX-ABC123",
        name: "测试企业",
        industry: null,
        company_size: null,
      },
      expiresAt: null,
    });
    const fetchMock = vi.fn<typeof fetch>(async () =>
      Response.json({ data: null, request_id: "req_5", error: null }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await requestJson("/sessions");

    const call = fetchMock.mock.calls.at(0);
    if (!call) {
      throw new Error("Expected requestJson to call fetch");
    }
    expect(new Headers(call[1]?.headers).get("authorization")).toBe("Bearer token_123");
  });

  it("reads binary Artifact responses and keeps response headers", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      new Response(new Blob(["csv,data\n1,2\n"], { type: "text/csv" }), {
        status: 200,
        headers: {
          "content-type": "text/csv",
          "content-disposition": 'attachment; filename="result.csv"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestBinary("/artifacts/a_1/download");
    expect(result.blob.size).toBeGreaterThan(0);
    expect(result.contentType).toBe("text/csv");
    expect(result.filename).toBe("result.csv");
  });

  it("parses a JSON error envelope even for binary requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          {
            data: null,
            request_id: "req_binary_error",
            error: { code: "ARTIFACT_NOT_FOUND", message: "Artifact 不存在", details: {} },
          },
          { status: 404 },
        ),
      ),
    );

    await expect(requestBinary("/artifacts/missing/content")).rejects.toMatchObject({
      code: "ARTIFACT_NOT_FOUND",
      requestId: "req_binary_error",
    });
  });
});
