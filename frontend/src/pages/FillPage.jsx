import { useState, useCallback, useEffect } from 'react';
import { fillForm, markApplied } from '../api.js';

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

export default function FillPage({ initialUrl = '' }) {
  const [url, setUrl] = useState(initialUrl);

  useEffect(() => {
    if (initialUrl) setUrl(initialUrl);
  }, [initialUrl]);
  const [filling, setFilling] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);

  // Mark as applied state
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [marking, setMarking] = useState(false);
  const [marked, setMarked] = useState(false);
  const [markError, setMarkError] = useState('');

  const inferFromTitle = useCallback((pageTitle, jobUrl) => {
    // Common patterns: "Role at Company", "Role - Company", "Company | Role",
    // "Company - Role", "Role | Company — Careers"
    if (pageTitle) {
      const atMatch = pageTitle.match(/^(.+?)\s+at\s+(.+?)(?:\s[|\-–—].*)?$/i);
      if (atMatch) return { role: atMatch[1].trim(), company: atMatch[2].trim() };

      const dashMatch = pageTitle.match(/^(.+?)\s*[|\-–—]\s*(.+?)(?:\s[|\-–—].*)?$/);
      if (dashMatch) {
        // Heuristic: shorter part is usually the company
        const [a, b] = [dashMatch[1].trim(), dashMatch[2].trim()];
        return a.length <= b.length
          ? { company: a, role: b }
          : { company: b, role: a };
      }
    }
    // Fallback: extract company from domain (e.g. jobs.doctolib.com → Doctolib)
    try {
      const hostname = new URL(jobUrl).hostname;
      const parts = hostname.replace(/^www\./, '').split('.');
      const name = parts.length >= 2 ? parts[parts.length - 2] : parts[0];
      return { company: name.charAt(0).toUpperCase() + name.slice(1), role: '' };
    } catch {
      return { company: '', role: '' };
    }
  }, []);

  const handleFill = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setFilling(true);
    setResult(null);
    setError('');
    setShowAll(false);
    setMarked(false);
    setMarkError('');
    try {
      const data = await fillForm(trimmed);
      setResult(data);
      const inferred = inferFromTitle(data.page_title, trimmed);
      if (inferred.company && !company) setCompany(inferred.company);
      if (inferred.role && !role) setRole(inferred.role);
    } catch (err) {
      setError(err.message);
    } finally {
      setFilling(false);
    }
  }, [url, company, role, inferFromTitle]);

  const handleMarkApplied = async () => {
    setMarking(true);
    setMarkError('');
    try {
      await markApplied(url.trim(), company.trim(), role.trim());
      setMarked(true);
    } catch (err) {
      setMarkError(err.message);
    } finally {
      setMarking(false);
    }
  };

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
          A Chromium window will open. Review the filled fields and submit manually. Successful submissions are saved to your tracker automatically.
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

          {/* Mark as Applied */}
          {marked ? (
            <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700 font-medium">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              Application saved! You can view all applications in the Applications tab.
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-700">Not auto-saved yet?</h2>
                <p className="text-xs text-slate-400 mt-0.5">Submission is usually detected automatically. Use this if it wasn't saved to your tracker after submitting.</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Company name"
                  className="rounded-lg border-slate-200 text-sm text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
                <input
                  type="text"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="Job title / role"
                  className="rounded-lg border-slate-200 text-sm text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
              {markError && (
                <p className="text-xs text-red-600">{markError}</p>
              )}
              <button
                onClick={handleMarkApplied}
                disabled={marking}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg shadow-sm transition-colors"
              >
                {marking ? (
                  <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                )}
                {marking ? 'Saving…' : 'Mark as Applied'}
              </button>
            </div>
          )}

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
