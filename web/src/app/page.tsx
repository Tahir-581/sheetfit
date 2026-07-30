"use client";

import { useMemo, useState } from "react";

type InfoResponse = {
  pages: number;
  threshold: number;
  target: number;
  will_expand: boolean;
  will_pad: boolean;
  passthrough: boolean;
};

type ExpandResponse = {
  job_id: string;
  download_url: string;
  report_url: string;
  report: {
    source_pages: number;
    output_pages: number;
    action: string;
    word_count: number;
    image_count: number;
    title: string;
    author: string;
    params: Record<string, unknown>;
    blank_pages_added: number;
    notes: string[];
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_SHEETFIT_API ?? "http://127.0.0.1:8765";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [info, setInfo] = useState<InfoResponse | null>(null);
  const [result, setResult] = useState<ExpandResponse | null>(null);
  const [busy, setBusy] = useState<"info" | "expand" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  const canExpand = useMemo(() => {
    if (!info) return false;
    return info.will_expand || info.will_pad;
  }, [info]);

  async function onPick(f: File | null) {
    setFile(f);
    setInfo(null);
    setResult(null);
    setError(null);
    setStatus("");
    if (!f) return;

    setBusy("info");
    setStatus("Counting pages…");
    try {
      const body = new FormData();
      body.append("file", f);
      const res = await fetch(`${API_BASE}/info`, { method: "POST", body });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as InfoResponse;
      setInfo(data);
      setStatus(
        data.will_expand
          ? `Detected ${data.pages} pages — will retypeset toward ${data.target}.`
          : data.will_pad
            ? `Detected ${data.pages} pages — will pad blanks to ${data.target}.`
            : `Detected ${data.pages} pages — already at/above target; no expand.`,
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not reach the Sheetfit engine. Is it running on :8765?",
      );
    } finally {
      setBusy(null);
    }
  }

  async function onExpand() {
    if (!file) return;
    setBusy("expand");
    setError(null);
    setResult(null);
    setStatus(
      "Extracting, searching typography, and rendering… this can take a few minutes.",
    );
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API_BASE}/expand`, { method: "POST", body });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `Expand failed (${res.status})`);
      }
      const data = (await res.json()) as ExpandResponse;
      setResult(data);
      setStatus(
        `Done: ${data.report.source_pages} → ${data.report.output_pages} pages (${data.report.action}).`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Expand failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 py-14 sm:py-20">
      <header className="mb-12">
        <p className="font-display text-sm tracking-[0.22em] text-[var(--muted)] uppercase">
          100 sheets · 4 pages each
        </p>
        <h1 className="font-display mt-3 text-5xl leading-tight sm:text-6xl">
          Sheetfit
        </h1>
        <p className="mt-4 max-w-xl text-lg leading-relaxed text-[var(--muted)]">
          Drop a short book PDF. If it has fewer than 350 pages, Sheetfit
          retypesets it toward 400 reading pages — ready for landscape duplex
          printing on 100 sheets.
        </p>
      </header>

      <section className="rounded-sm border border-[var(--line)] bg-white/55 p-6 shadow-[0_20px_50px_-30px_rgba(60,40,20,0.45)] backdrop-blur-sm sm:p-8">
        <label className="block">
          <span className="font-display text-sm tracking-wide text-[var(--muted)]">
            PDF
          </span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="mt-3 block w-full text-sm file:mr-4 file:rounded-sm file:border-0 file:bg-[var(--ink)] file:px-4 file:py-2 file:text-sm file:font-medium file:text-[var(--paper)] hover:file:bg-[#2a241f]"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
            disabled={busy !== null}
          />
        </label>

        {status && (
          <p className="mt-5 text-sm leading-relaxed text-[var(--muted)]">
            {status}
          </p>
        )}

        {error && (
          <p className="mt-4 border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}

        {info && (
          <dl className="mt-6 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-[var(--muted)]">Pages</dt>
              <dd className="font-display text-2xl">{info.pages}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Threshold</dt>
              <dd className="font-display text-2xl">{info.threshold}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Target</dt>
              <dd className="font-display text-2xl">{info.target}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Action</dt>
              <dd className="font-display text-lg capitalize">
                {info.will_expand
                  ? "Retypeset"
                  : info.will_pad
                    ? "Pad"
                    : "Skip"}
              </dd>
            </div>
          </dl>
        )}

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onExpand}
            disabled={!file || !canExpand || busy !== null}
            className="rounded-sm bg-[var(--accent)] px-5 py-2.5 text-sm font-medium text-[#fff8f0] transition enabled:hover:bg-[#6f3610] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy === "expand" ? "Working…" : "Expand to ~400 pages"}
          </button>
          {result && (
            <a
              href={`${API_BASE}${result.download_url}`}
              className="rounded-sm border border-[var(--ink)] px-5 py-2.5 text-sm font-medium text-[var(--ink)] hover:bg-[var(--ink)] hover:text-[var(--paper)]"
            >
              Download PDF
            </a>
          )}
        </div>
      </section>

      {result && (
        <section className="mt-8 border-t border-[var(--line)] pt-8">
          <h2 className="font-display text-2xl">Result</h2>
          <p className="mt-2 text-[var(--muted)]">
            {result.report.title}
            {result.report.author ? ` — ${result.report.author}` : ""}
          </p>
          <ul className="mt-4 space-y-1 text-sm text-[var(--muted)]">
            <li>
              {result.report.source_pages} → {result.report.output_pages} pages
              ({result.report.action})
            </li>
            <li>
              {result.report.word_count.toLocaleString()} words ·{" "}
              {result.report.image_count} images ·{" "}
              {result.report.blank_pages_added} blank pads
            </li>
            {result.report.params?.font_size_pt != null && (
              <li>
                Body {String(result.report.params.font_size_pt)}pt · leading{" "}
                {String(result.report.params.line_height)} · margins{" "}
                {String(result.report.params.margin_x_in)}in
              </li>
            )}
          </ul>
          {result.report.notes?.length > 0 && (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-[var(--muted)]">
              {result.report.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <footer className="mt-auto pt-16 text-sm text-[var(--muted)]">
        Engine API: <code className="text-[var(--ink)]">{API_BASE}</code>
        {" · "}
        After expand, impose with FoldPress for landscape 2-up duplex sheets.
      </footer>
    </main>
  );
}
