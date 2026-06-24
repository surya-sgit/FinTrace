/**
 * Extract a human-readable string from an Axios/FastAPI error.
 *
 * FastAPI returns `detail` as a plain string for HTTPException, but as an ARRAY of
 * `{type, loc, msg, ...}` objects for 422 validation errors. Rendering that array
 * directly crashes React ("Objects are not valid as a React child"), so always funnel
 * errors through this helper before putting them in state.
 */
export function getErrorMessage(err: unknown, fallback = "Something went wrong."): string {
    const anyErr = err as { response?: { data?: { detail?: unknown } }; message?: string };
    const detail = anyErr?.response?.data?.detail;

    if (typeof detail === "string") return detail;

    if (Array.isArray(detail)) {
        const msgs = detail
            .map((d) => (typeof d === "string" ? d : (d as { msg?: string })?.msg))
            .filter(Boolean);
        if (msgs.length) return msgs.join("; ");
    }

    if (detail && typeof detail === "object") {
        const msg = (detail as { msg?: string }).msg;
        if (typeof msg === "string") return msg;
    }

    return anyErr?.message || fallback;
}
