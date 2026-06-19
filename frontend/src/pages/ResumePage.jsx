import { useState, useEffect, useRef, useCallback } from 'react';
import { getProfile, uploadResume, uploadCoverLetter, uploadReferenceLetter } from '../api.js';

function Toast({ message, type }) {
  if (!message) return null;
  const colors =
    type === 'success'
      ? 'bg-green-100 text-green-700 border-green-200'
      : 'bg-red-100 text-red-700 border-red-200';
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl border shadow-lg text-sm font-medium flex items-center gap-2 ${colors}`}
    >
      {type === 'success' ? (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
      )}
      {message}
    </div>
  );
}

/** Extract a human-readable filename from a full filesystem path */
function baseName(path) {
  if (!path) return null;
  return path.split('/').pop() || path.split('\\').pop() || path;
}

/** Reusable upload card for a single document type */
function DocumentUploadCard({ title, description, currentPath, currentName, uploadFn, pathKey, nameKey, loading, onSuccess, onError }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const currentFileName = currentName || baseName(currentPath);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    try {
      const result = await uploadFn(selectedFile);
      onSuccess(result[pathKey], result[nameKey] || selectedFile.name);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      onError(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
        <p className="text-xs text-slate-400 mt-0.5">{description}</p>
      </div>

      {/* Current file */}
      {loading ? (
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Loading…
        </div>
      ) : currentFileName ? (
        <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
          <div className="w-9 h-9 bg-red-50 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate" title={currentPath}>{currentFileName}</p>
            <p className="text-xs text-slate-400 truncate mt-0.5" title={currentPath}>{currentPath}</p>
          </div>
          <span className="ml-auto flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
            Active
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-lg border border-dashed border-slate-300">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-sm text-slate-400">No file uploaded yet</p>
        </div>
      )}

      {/* Picker + upload */}
      <div
        className="relative flex flex-col items-center justify-center p-6 border-2 border-dashed border-slate-200 rounded-lg hover:border-indigo-300 hover:bg-indigo-50/30 transition-colors cursor-pointer"
        onClick={() => fileInputRef.current?.click()}
      >
        <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleFileChange} className="sr-only" />
        <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-slate-300 mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
        {selectedFile ? (
          <p className="text-sm font-medium text-indigo-600">{selectedFile.name}</p>
        ) : (
          <>
            <p className="text-sm font-medium text-slate-600">Click to select a PDF</p>
            <p className="text-xs text-slate-400 mt-1">{currentFileName ? 'Replaces current file' : 'PDF files only'}</p>
          </>
        )}
      </div>

      <button
        onClick={handleUpload}
        disabled={!selectedFile || uploading}
        className="w-full inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg shadow-sm transition-colors"
      >
        {uploading && (
          <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        )}
        {uploading ? 'Uploading…' : `Upload ${title}`}
      </button>
    </div>
  );
}

export default function ResumePage() {
  const [resumePath, setResumePath] = useState(null);
  const [resumeName, setResumeName] = useState(null);
  const [coverLetterPath, setCoverLetterPath] = useState(null);
  const [coverLetterName, setCoverLetterName] = useState(null);
  const [referenceLetterPath, setReferenceLetterPath] = useState(null);
  const [referenceLetterName, setReferenceLetterName] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    getProfile()
      .then((p) => {
        setResumePath(p.resumePath || null);
        setResumeName(p.resumeName || null);
        setCoverLetterPath(p.coverLetterPath || null);
        setCoverLetterName(p.coverLetterName || null);
        setReferenceLetterPath(p.referenceLetterPath || null);
        setReferenceLetterName(p.referenceLetterName || null);
      })
      .catch((err) => showToast(`Could not load profile: ${err.message}`, 'error'))
      .finally(() => setLoadingProfile(false));
  }, []);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Documents</h1>
        <p className="text-slate-500 text-sm mt-1">
          Upload your application documents — they will be attached to the matching file fields automatically.
        </p>
      </div>

      <div className="space-y-4">
        <DocumentUploadCard
          title="Resume"
          description="Attached to CV / Lebenslauf upload fields."
          currentPath={resumePath}
          currentName={resumeName}
          uploadFn={uploadResume}
          pathKey="resume_path"
          nameKey="resume_name"
          loading={loadingProfile}
          onSuccess={(path, name) => { setResumePath(path); setResumeName(name); showToast('Resume uploaded successfully!'); }}
          onError={(msg) => showToast(`Upload failed: ${msg}`, 'error')}
        />

        <DocumentUploadCard
          title="Cover Letter"
          description="Attached to cover letter / Anschreiben upload fields."
          currentPath={coverLetterPath}
          currentName={coverLetterName}
          uploadFn={uploadCoverLetter}
          pathKey="cover_letter_path"
          nameKey="cover_letter_name"
          loading={loadingProfile}
          onSuccess={(path, name) => { setCoverLetterPath(path); setCoverLetterName(name); showToast('Cover letter uploaded successfully!'); }}
          onError={(msg) => showToast(`Upload failed: ${msg}`, 'error')}
        />

        <DocumentUploadCard
          title="Reference Letter"
          description="Attached to reference / Zeugnis upload fields."
          currentPath={referenceLetterPath}
          currentName={referenceLetterName}
          uploadFn={uploadReferenceLetter}
          pathKey="reference_letter_path"
          nameKey="reference_letter_name"
          loading={loadingProfile}
          onSuccess={(path, name) => { setReferenceLetterPath(path); setReferenceLetterName(name); showToast('Reference letter uploaded successfully!'); }}
          onError={(msg) => showToast(`Upload failed: ${msg}`, 'error')}
        />
      </div>

      {toast && <Toast message={toast.message} type={toast.type} />}
    </>
  );
}
