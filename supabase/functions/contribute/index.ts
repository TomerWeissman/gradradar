// POST /contribute
//
// Accepts a single PI enrichment contribution from the CLI. Rate-limits by IP
// (30 accepted contributions per hour), logs every field to
// pi_field_contributions for provenance, then UPSERTs the winning values into
// public.pis using the service_role key.
//
// Payload (application/json):
//   {
//     "pi_id":         "uuid",
//     "source_url":    "https://...",
//     "content_hash":  "sha256:...",
//     "model":         "anthropic/claude-haiku-4-5",
//     "extracted_at":  "2026-04-19T17:00:00Z",
//     "contributor_id":"uuid",
//     "fields": {
//         "research_description": "...",
//         "is_taking_students":   "yes",
//         ...
//     }
//   }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

// Only these PI fields can be contributed. Anything else is silently dropped.
const ALLOWED_FIELDS = new Set([
    "research_description",
    "is_taking_students",
    "taking_students_confidence",
    "taking_students_checked_at",
    "career_stage",
    "department_name",
    "lab_name",
    "short_bio",
    "theory_category",
    "theory_category_source",
    "personal_url",
    "lab_url",
    "google_scholar_url",
    "email",
    "phd_year",
    "phd_institution",
    "year_started_position",
]);

const RATE_LIMIT_PER_HOUR = 30;

function clientIp(req: Request): string {
    return (
        req.headers.get("cf-connecting-ip") ??
        req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
        "unknown"
    );
}

function json(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
    });
}

Deno.serve(async (req) => {
    if (req.method !== "POST") {
        return json({ error: "method_not_allowed" }, 405);
    }

    let payload: any;
    try {
        payload = await req.json();
    } catch {
        return json({ error: "invalid_json" }, 400);
    }

    const { pi_id, source_url, content_hash, model, extracted_at, contributor_id, fields } = payload;

    if (!pi_id || typeof pi_id !== "string") return json({ error: "pi_id_required" }, 400);
    if (!fields || typeof fields !== "object") return json({ error: "fields_required" }, 400);
    if (!contributor_id || typeof contributor_id !== "string") return json({ error: "contributor_id_required" }, 400);

    const ip = clientIp(req);
    const supa = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, { auth: { persistSession: false } });

    // Rate limit: count contributions from this IP in the last hour.
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const { count: recentCount, error: countErr } = await supa
        .from("pi_field_contributions")
        .select("id", { count: "exact", head: true })
        .eq("ip", ip)
        .gte("created_at", oneHourAgo);

    if (countErr) return json({ error: "rate_check_failed", detail: countErr.message }, 500);
    if ((recentCount ?? 0) >= RATE_LIMIT_PER_HOUR) {
        return json({ error: "rate_limited", limit: RATE_LIMIT_PER_HOUR, window: "1h" }, 429);
    }

    // Confirm pi_id exists (cheap guard; UPSERT would silently create a row otherwise).
    const { data: piRow, error: piErr } = await supa
        .from("pis")
        .select("id")
        .eq("id", pi_id)
        .maybeSingle();
    if (piErr) return json({ error: "pi_lookup_failed", detail: piErr.message }, 500);
    if (!piRow) return json({ error: "pi_not_found" }, 404);

    // Filter contributed fields to the allowed set and drop nulls/empties.
    const cleanFields: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(fields)) {
        if (!ALLOWED_FIELDS.has(k)) continue;
        if (v === null || v === undefined) continue;
        if (typeof v === "string" && v.trim() === "") continue;
        cleanFields[k] = v;
    }
    if (Object.keys(cleanFields).length === 0) {
        return json({ error: "no_allowed_fields" }, 400);
    }

    // Log every field to the provenance table.
    const provenanceRows = Object.entries(cleanFields).map(([field_name, field_value]) => ({
        pi_id,
        field_name,
        field_value: typeof field_value === "string" ? field_value : JSON.stringify(field_value),
        source_url: source_url ?? null,
        content_hash: content_hash ?? null,
        model: model ?? null,
        extracted_at: extracted_at ?? null,
        contributor_id,
        ip,
    }));

    const { error: logErr } = await supa.from("pi_field_contributions").insert(provenanceRows);
    if (logErr) return json({ error: "provenance_write_failed", detail: logErr.message }, 500);

    // Apply winning values to public.pis. Contributed values overwrite existing
    // ones; revertibility comes from the provenance log, not from a read-time
    // merge. Non-destructive in practice because we only accept fields via
    // ALLOWED_FIELDS and the extractor produces structured values.
    const updatePayload: Record<string, unknown> = { ...cleanFields };
    updatePayload.scraped_at = extracted_at ?? new Date().toISOString();
    updatePayload.content_hash = content_hash ?? null;
    updatePayload.source_url = source_url ?? null;

    const { error: updateErr } = await supa
        .from("pis")
        .update(updatePayload)
        .eq("id", pi_id);
    if (updateErr) return json({ error: "pi_update_failed", detail: updateErr.message }, 500);

    return json({
        ok: true,
        pi_id,
        fields_written: Object.keys(cleanFields),
        rate_limit: { used: (recentCount ?? 0) + 1, limit: RATE_LIMIT_PER_HOUR, window: "1h" },
    });
});
