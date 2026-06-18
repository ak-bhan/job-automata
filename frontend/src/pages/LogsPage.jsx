import { useState, useEffect } from 'react';
import { getLogs } from '../api.js';

/**
 * Format an ISO-8601 UTC timestamp into a human-readable local date string.
 */
function formatDate(isoString) {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

/**
 * Truncate a URL for display while keeping the full value as a tooltip.
 */
function TruncatedUrl({ url }) {
  const MAX = 60;
  const display = url.length > MAX ? url.slice(0, MAX) + '…' : url;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={url}
      className="text-indigo-600 hover:text-indigo-800 hover:underline text-sm font-medium break-all transition-colors"
    >
      {display}
    </a>
  );
}

function StatPill({ value, label, color }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      <span className="font-bold">{value}</span>
      <span className="opacity-70">{label}</span>
    </span>
  );
}

function LogCard({ log }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0 flex-1">
          <TruncatedUrl url={log.url} />
        </div>
        <time className="text-xs text-slate-400 flex-shrink-0 mt-0.5">
          {formatDate(log.created_at)}
        </time>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <StatPill value={log.fields_detected} label="detected" color="bg-slate-100 text-slate-600" />
        <StatPill value={log.fields_filled} label="filled" color="bg-green-100 text-green-700" />
        <StatPill value={log.fields_skipped} label="skipped" color="bg-amber-100 text-amber-700" />
      </div>
    </div>
  );
}

export default function LogsPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getLogs(20)
      .then((data) => setLogs(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Fill Logs</h1>
        <p className="text-slate-500 text-sm mt-1">
          History of your recent form-fill attempts.
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-24">
          <svg className="animate-spin h-7 w-7 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <div>
            <p className="font-semibold">Failed to load logs</p>
            <p className="mt-0.5 text-red-600">{error}</p>
          </div>
        </div>
      )}

      {!loading && !error && logs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-14 h-14 bg-slate-100 rounded-full flex items-center justify-center mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <h2 className="text-base font-semibold text-slate-600 mb-1">No fill attempts yet</h2>
          <p className="text-sm text-slate-400">
            Head over to "Fill a Form" to get started.
          </p>
        </div>
      )}

      {!loading && !error && logs.length > 0 && (
        <div className="space-y-3">
          {logs.map((log) => (
            <LogCard key={log.id} log={log} />
          ))}
          {logs.length === 20 && (
            <p className="text-xs text-slate-400 text-center pt-2">
              Showing the 20 most recent entries.
            </p>
          )}
        </div>
      )}
    </>
  );
}
