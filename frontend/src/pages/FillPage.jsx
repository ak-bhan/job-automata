import { useState, useCallback } from 'react';
import { fillForm } from '../api.js';

const STATUS_BADGE = {
  filled: 'bg-green-100 text-green-700',
  skipped: 'bg-amber-100 text-amber-700',
  no_match: 'bg-slate-100 text-slate-500',
  no_value: 'bg-amber-100 text-amber-700',
  error: 'bg-red-100 text-red-700',
};

const STATUS_LABEL = {
  filled: 'Filled',
  skipped: 'Skipped',
  no_match: 'No match',
  no_value: 'No value',
  error: 'Error',
};

/**
 * Pick the best human-readable label from the field's signals object.
 */
function getBestLabel(signals) {
  if (!signals) return '—';
  return (
    signals.label ||
    signals.placeholder ||
    signals.name ||
    signals.id ||
    signals['aria-label'] ||
    '—'
  );
}

function StatBox({ value, label, color }) {
  return (
    <div className={`flex-1 rounded-xl border p-4 text-center ${color}`}>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-xs font-medium mt-1 uppercase tracking-wide opacity-70">{label}</div>
    </div>
  );
}

export default function FillPage() {
  const [url, setUrl] = useState('');
  const [filling, setFilling] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);

  const handleFill = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setFilling(true);
    setResult(null);
    setError('');
    setShowAll(false);
    try {
      const data = await fillForm(trimmed);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setFilling(false);
    }
  }, [url]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !filling) handleFill();
  };

  const detail = result?.detail || [];
  const noiseStatuses = new Set(['no_match', 'skipped']);
  const mainRows = detail.filter((e) => !noiseStatuses.has(e.status));
  const hiddenRows = detail.filter((e) => noiseStatuses.has(e.status));
  const visibleRows = showAll ? detail : mainRows;

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Fill a Form</h1>
        <p className="text-slate-500 text-sm mt-1">
          Paste a job application URL and watch the form get filled in a real browser.
        </p>
      </div>

      {/* URL input card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-5">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          Job application URL
        </label>
        <div className="flex gap-3">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="https://jobs.example.com/apply/..."
            className="block flex-1 rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
          />
          <button
            onClick={handleFill}
            disabled={filling || !url.trim()}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg shadow-sm transition-colors flex-shrink-0"
          >
            {filling ? (
              <>
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Filling…
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
                Fill Form
              </>
            )}
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          A Chromium window will open. Review the filled fields and submit manually.
        </p>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-5 flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <div>
            <p className="font-semibold">Fill failed</p>
            <p className="mt-0.5 text-red-600">{error}</p>
          </div>
        </div>
      )}

      {/* Fill result */}
      {result && (
        <div className="space-y-5">
          {/* Stats */}
          <div className="flex gap-3">
            <StatBox
              value={result.fields_detected}
              label="Detected"
              color="border-slate-200 text-slate-700"
            />
            <StatBox
              value={result.fields_filled}
              label="Filled"
              color="border-green-200 text-green-700 bg-green-50"
            />
            <StatBox
              value={result.fields_skipped}
              label="Skipped"
              color="border-amber-200 text-amber-700 bg-amber-50"
            />
          </div>

          {/* Field detail table */}
          {detail.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">Field Details</h2>
                <span className="text-xs text-slate-400">{detail.length} fields detected</span>
              </div>

              {visibleRows.length === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-400 text-center">
                  No notable fields to display.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Label</th>
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Matched Key</th>
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {visibleRows.map((entry, i) => {
                      const badgeClass = STATUS_BADGE[entry.status] || 'bg-slate-100 text-slate-500';
                      const statusLabel = STATUS_LABEL[entry.status] || entry.status;
                      const label = getBestLabel(entry.signals);
                      return (
                        <tr key={i} className="hover:bg-slate-50/50 transition-colors">
                          <td className="px-5 py-3 text-slate-700 max-w-xs">
                            <span className="truncate block" title={label}>{label}</span>
                          </td>
                          <td className="px-5 py-3">
                            {entry.matched_key ? (
                              <code className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">
                                {entry.matched_key}
                              </code>
                            ) : (
                              <span className="text-slate-300">—</span>
                            )}
                          </td>
                          <td className="px-5 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass}`}>
                              {statusLabel}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              {hiddenRows.length > 0 && (
                <div className="px-5 py-3 border-t border-slate-100">
                  <button
                    onClick={() => setShowAll((v) => !v)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
                  >
                    {showAll
                      ? `Hide ${hiddenRows.length} skipped / unmatched fields`
                      : `Show all fields (${hiddenRows.length} skipped / unmatched)`}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
