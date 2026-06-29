import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getSearchConfig, saveSearchConfig, fetchJobs,
  getJobs, getJobCounts, updateJobStatus, deleteJob,
} from '../api.js';

const SOURCE_LABELS = { arbeitnow: 'Arbeitnow', remotive: 'Remotive' };
const SOURCE_COLORS = {
  arbeitnow: 'bg-blue-100 text-blue-700',
  remotive: 'bg-emerald-100 text-emerald-700',
};

function relativeTime(isoStr) {
  if (!isoStr) return '';
  const diff = Date.now() - new Date(isoStr).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function Toast({ message, type }) {
  if (!message) return null;
  const colors = type === 'success'
    ? 'bg-green-100 text-green-700 border-green-200'
    : 'bg-red-100 text-red-700 border-red-200';
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl border shadow-lg text-sm font-medium ${colors}`}>
      {message}
    </div>
  );
}

function SearchSettings({ onFetched }) {
  const [config, setConfig] = useState({
    keywords: '', location: '', max_age_hours: 24, sources: ['arbeitnow', 'remotive'],
  });
  const [saving, setSaving] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    getSearchConfig().then(setConfig).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try { await saveSearchConfig(config); } finally { setSaving(false); }
  };

  const handleFetch = async () => {
    setSaving(true);
    try { await saveSearchConfig(config); } catch { /* ignore */ } finally { setSaving(false); }
    setFetching(true);
    setLastResult(null);
    try {
      const result = await fetchJobs();
      setLastResult(result);
      onFetched();
    } catch (err) {
      setLastResult({ error: err.message });
    } finally {
      setFetching(false);
    }
  };

  const toggleSource = (src) => {
    setConfig((c) => {
      const active = c.sources.includes(src)
        ? c.sources.filter((s) => s !== src)
        : [...c.sources, src];
      return { ...c, sources: active };
    });
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm mb-5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 text-sm font-semibold text-slate-700 hover:bg-slate-50 rounded-xl transition-colors"
      >
        <span className="flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-slate-400" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
          </svg>
          Search Settings
        </span>
        <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div className="px-5 pb-5 border-t border-slate-100 pt-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Keywords</label>
              <input
                type="text"
                value={config.keywords}
                onChange={(e) => setConfig((c) => ({ ...c, keywords: e.target.value }))}
                placeholder="python developer, react, data engineer…"
                className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Location</label>
              <input
                type="text"
                value={config.location}
                onChange={(e) => setConfig((c) => ({ ...c, location: e.target.value }))}
                placeholder="Berlin, remote, Munich…"
                className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
              />
            </div>
          </div>

          <div className="flex items-end gap-6">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Max age</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={720}
                  value={config.max_age_hours}
                  onChange={(e) => setConfig((c) => ({ ...c, max_age_hours: Number(e.target.value) }))}
                  className="w-20 rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
                <span className="text-sm text-slate-500">hours</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Sources</label>
              <div className="flex items-center gap-4">
                {Object.entries(SOURCE_LABELS).map(([id, label]) => (
                  <label key={id} className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config.sources.includes(id)}
                      onChange={() => toggleSource(id)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            <button
              onClick={handleFetch}
              disabled={fetching || config.sources.length === 0}
              className="inline-flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg shadow-sm transition-colors ml-auto"
            >
              {fetching ? (
                <>
                  <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Fetching…
                </>
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                  </svg>
                  Fetch Jobs
                </>
              )}
            </button>
          </div>

          {lastResult && (
            <div className={`text-xs rounded-lg px-3 py-2 ${lastResult.error ? 'bg-red-50 text-red-600' : 'bg-slate-50 text-slate-600'}`}>
              {lastResult.error
                ? `Error: ${lastResult.error}`
                : `Fetched ${lastResult.fetched} jobs — ${lastResult.inserted} new, ${lastResult.skipped} already known.${lastResult.errors?.length ? ' Errors: ' + lastResult.errors.join('; ') : ''}`}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function JobRow({ job, onFill, onStatusChange, onDelete }) {
  const [updating, setUpdating] = useState(false);

  const handleStatus = async (newStatus) => {
    setUpdating(true);
    try { await onStatusChange(job.id, newStatus); } finally { setUpdating(false); }
  };

  const isSaved = job.status === 'saved';

  return (
    <tr className="hover:bg-slate-50/60 transition-colors border-b border-slate-100 last:border-0">
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-slate-800 leading-snug">{job.title}</p>
        <p className="text-xs text-slate-500 mt-0.5">{job.company}</p>
      </td>
      <td className="px-4 py-3 text-xs text-slate-600">
        <span>{job.location}</span>
        {job.remote && (
          <span className="ml-1.5 inline-block px-1.5 py-0.5 bg-violet-100 text-violet-700 rounded text-xs font-medium">Remote</span>
        )}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${SOURCE_COLORS[job.source] || 'bg-slate-100 text-slate-600'}`}>
          {SOURCE_LABELS[job.source] || job.source}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
        {relativeTime(job.posted_at)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onFill(job.apply_url)}
            className="inline-flex items-center gap-1 px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition-colors"
            title="Fill this application"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
              <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
            </svg>
            Fill
          </button>
          <button
            onClick={() => handleStatus(isSaved ? 'new' : 'saved')}
            disabled={updating}
            className={`p-1.5 rounded transition-colors ${isSaved ? 'text-amber-500 hover:text-amber-700' : 'text-slate-300 hover:text-amber-500'}`}
            title={isSaved ? 'Unsave' : 'Save'}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M5 4a2 2 0 012-2h6a2 2 0 012 2v14l-5-2.5L5 18V4z" />
            </svg>
          </button>
          <button
            onClick={() => handleStatus('hidden')}
            disabled={updating}
            className="p-1.5 text-slate-300 hover:text-slate-500 rounded transition-colors"
            title="Hide"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M3.707 2.293a1 1 0 00-1.414 1.414l14 14a1 1 0 001.414-1.414l-1.473-1.473A10.014 10.014 0 0019.542 10C18.268 5.943 14.478 3 10 3a9.958 9.958 0 00-4.512 1.074l-1.78-1.781zm4.261 4.26l1.514 1.515a2.003 2.003 0 012.45 2.45l1.514 1.514a4 4 0 00-5.478-5.478z" clipRule="evenodd" />
              <path d="M12.454 16.697L9.75 13.992a4 4 0 01-3.742-3.741L2.335 6.578A9.98 9.98 0 00.458 10c1.274 4.057 5.065 7 9.542 7 .847 0 1.669-.105 2.454-.303z" />
            </svg>
          </button>
          <button
            onClick={() => onDelete(job.id)}
            className="p-1.5 text-slate-300 hover:text-red-500 rounded transition-colors"
            title="Delete"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function JobsPage({ onFill }) {
  const [jobs, setJobs] = useState([]);
  const [counts, setCounts] = useState({ new: 0, saved: 0, hidden: 0 });
  const [activeTab, setActiveTab] = useState('new');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const searchTimeout = useRef(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const loadJobs = useCallback(async (tab = activeTab, q = search) => {
    setLoading(true);
    try {
      const [jobList, countData] = await Promise.all([
        getJobs({ status: tab === 'all' ? 'all' : tab, q: q || undefined }),
        getJobCounts(),
      ]);
      setJobs(jobList);
      setCounts(countData);
    } catch (err) {
      showToast(`Failed to load jobs: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  }, [activeTab, search, showToast]);

  useEffect(() => { loadJobs(); }, []); // eslint-disable-line

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    loadJobs(tab, search);
  };

  const handleSearch = (val) => {
    setSearch(val);
    clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => loadJobs(activeTab, val), 300);
  };

  const handleStatusChange = async (id, newStatus) => {
    await updateJobStatus(id, newStatus);
    // Optimistically update list
    if (newStatus === 'hidden') {
      setJobs((prev) => prev.filter((j) => j.id !== id));
    } else {
      setJobs((prev) => prev.map((j) => j.id === id ? { ...j, status: newStatus } : j));
    }
    const countData = await getJobCounts();
    setCounts(countData);
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this job listing?')) return;
    try {
      await deleteJob(id);
      setJobs((prev) => prev.filter((j) => j.id !== id));
      const countData = await getJobCounts();
      setCounts(countData);
      showToast('Job deleted.');
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const TABS = [
    { id: 'new', label: 'New', count: counts.new },
    { id: 'saved', label: 'Saved', count: counts.saved },
    { id: 'all', label: 'All' },
    { id: 'hidden', label: 'Hidden', count: counts.hidden },
  ];

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Job Listings</h1>
        <p className="text-slate-500 text-sm mt-1">
          Fetch fresh job openings, save the ones you like, and fill the application form in one click.
        </p>
      </div>

      <SearchSettings onFetched={() => loadJobs(activeTab, search)} />

      {/* Tabs + search */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex gap-1 p-1 bg-slate-100 rounded-lg">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={[
                'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'bg-white text-slate-800 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700',
              ].join(' ')}
            >
              {tab.label}
              {tab.count !== undefined && tab.count > 0 && (
                <span className="ml-1.5 text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full font-semibold">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Filter by title or company…"
          className="block flex-1 rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
        />
      </div>

      {/* Job table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <svg className="animate-spin h-6 w-6 text-indigo-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          </div>
        ) : jobs.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            {activeTab === 'new'
              ? 'No new jobs. Hit "Fetch Jobs" to pull the latest listings.'
              : 'No jobs here yet.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Job</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Location</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Source</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Posted</th>
                  <th className="px-4 py-2.5 w-40"></th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    onFill={onFill}
                    onStatusChange={handleStatusChange}
                    onDelete={handleDelete}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {jobs.length > 0 && (
          <div className="px-4 py-2.5 border-t border-slate-100 text-xs text-slate-400">
            {jobs.length} listing{jobs.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      {toast && <Toast message={toast.message} type={toast.type} />}
    </>
  );
}
