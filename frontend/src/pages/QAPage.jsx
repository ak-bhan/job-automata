import { useState, useEffect, useCallback } from 'react';
import { getQAPairs, addQAPair, updateQAPair, deleteQAPair } from '../api.js';

function Toast({ message, type }) {
  if (!message) return null;
  const colors =
    type === 'success'
      ? 'bg-green-100 text-green-700 border-green-200'
      : 'bg-red-100 text-red-700 border-red-200';
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl border shadow-lg text-sm font-medium ${colors}`}>
      {message}
    </div>
  );
}

function PairCard({ pair, onSave, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [question, setQuestion] = useState(pair.question);
  const [answer, setAnswer] = useState(pair.answer);
  const [tags, setTags] = useState(pair.tags || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(pair.id, question, answer, tags);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setQuestion(pair.question);
    setAnswer(pair.answer);
    setTags(pair.tags || '');
    setEditing(false);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
      {editing ? (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Question</label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Answer</label>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={4}
              className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Tags (optional)</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="e.g. ai, motivation, remote"
              className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={handleCancel}
              className="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-800 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !question.trim() || !answer.trim()}
              className="px-3 py-1.5 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg transition-colors"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-medium text-slate-800 leading-snug">{pair.question}</p>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => setEditing(true)}
                className="p-1.5 text-slate-400 hover:text-indigo-600 transition-colors rounded"
                aria-label="Edit"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                </svg>
              </button>
              <button
                onClick={() => onDelete(pair.id)}
                className="p-1.5 text-slate-400 hover:text-red-500 transition-colors rounded"
                aria-label="Delete"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>
          <p className="text-sm text-slate-600 mt-2 whitespace-pre-wrap leading-relaxed">{pair.answer}</p>
          {pair.tags && (
            <div className="flex flex-wrap gap-1 mt-2">
              {pair.tags.split(',').map((t) => t.trim()).filter(Boolean).map((tag) => (
                <span key={tag} className="inline-block px-2 py-0.5 bg-slate-100 text-slate-500 text-xs rounded-full">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AddPairForm({ onAdd }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [tags, setTags] = useState('');
  const [saving, setSaving] = useState(false);

  const handleAdd = async () => {
    setSaving(true);
    try {
      await onAdd(question, answer, tags);
      setQuestion('');
      setAnswer('');
      setTags('');
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2.5 border-2 border-dashed border-slate-300 hover:border-indigo-400 text-slate-500 hover:text-indigo-600 rounded-xl text-sm font-medium transition-colors w-full justify-center"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd" />
        </svg>
        Add Q&amp;A pair
      </button>
    );
  }

  return (
    <div className="bg-white rounded-xl border-2 border-indigo-300 shadow-sm p-4 space-y-3">
      <p className="text-sm font-semibold text-slate-700">New Q&amp;A pair</p>
      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Question</label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          placeholder="How do you use AI in your daily work?"
          className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Answer</label>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={4}
          placeholder="I use AI tools like…"
          className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Tags (optional)</label>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="e.g. ai, motivation, remote"
          className="block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
        />
      </div>
      <div className="flex gap-2 justify-end">
        <button
          onClick={() => { setOpen(false); setQuestion(''); setAnswer(''); setTags(''); }}
          className="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-800 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleAdd}
          disabled={saving || !question.trim() || !answer.trim()}
          className="px-3 py-1.5 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg transition-colors"
        >
          {saving ? 'Adding…' : 'Add'}
        </button>
      </div>
    </div>
  );
}

export default function QAPage() {
  const [pairs, setPairs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  useEffect(() => {
    getQAPairs()
      .then(setPairs)
      .catch((err) => showToast(`Failed to load Q&A pairs: ${err.message}`, 'error'))
      .finally(() => setLoading(false));
  }, [showToast]);

  const handleAdd = async (question, answer, tags) => {
    try {
      const newPair = await addQAPair(question, answer, tags);
      setPairs((prev) => [newPair, ...prev]);
      showToast('Q&A pair added.');
    } catch (err) {
      showToast(`Failed to add: ${err.message}`, 'error');
      throw err;
    }
  };

  const handleSave = async (id, question, answer, tags) => {
    try {
      await updateQAPair(id, question, answer, tags);
      setPairs((prev) =>
        prev.map((p) => (p.id === id ? { ...p, question, answer, tags } : p))
      );
      showToast('Q&A pair updated.');
    } catch (err) {
      showToast(`Failed to save: ${err.message}`, 'error');
      throw err;
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this Q&A pair?')) return;
    try {
      await deleteQAPair(id);
      setPairs((prev) => prev.filter((p) => p.id !== id));
      showToast('Q&A pair deleted.');
    } catch (err) {
      showToast(`Failed to delete: ${err.message}`, 'error');
    }
  };

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Screening Q&amp;A</h1>
        <p className="text-slate-500 text-sm mt-1">
          Pre-written answers for common screening questions. The filler matches them to textarea fields automatically.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <svg className="animate-spin h-7 w-7 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        </div>
      ) : (
        <div className="space-y-3">
          <AddPairForm onAdd={handleAdd} />
          {pairs.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">
              No Q&amp;A pairs yet. Add one above.
            </p>
          ) : (
            pairs.map((pair) => (
              <PairCard
                key={pair.id}
                pair={pair}
                onSave={handleSave}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} />}
    </>
  );
}
