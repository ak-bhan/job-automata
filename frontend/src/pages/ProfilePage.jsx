import { useState, useEffect, useCallback } from 'react';
import { getProfile, saveProfile } from '../api.js';

const EMPTY_PROFILE = {
  salutation: '',
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  phoneCountryCode: '',
  dateOfBirth: '',
  nationality: '',
  address: '',
  city: '',
  zip: '',
  country: '',
  linkedin: '',
  github: '',
  portfolio: '',
  currentTitle: '',
  currentCompany: '',
  yearsExp: '',
  workAuth: '',
  salaryExpect: '',
  noticePeriod: '',
  startDate: '',
  university: '',
  degree: '',
  gradYear: '',
  customFields: {},
};

function SectionHeading({ children }) {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3 mt-6 first:mt-0">
      {children}
    </h2>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

function TextInput({ name, value, onChange, placeholder = '', type = 'text', className = '' }) {
  return (
    <input
      type={type}
      name={name}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className={[
        'block w-full rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm',
        'focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
        'placeholder:text-slate-400',
        className,
      ].join(' ')}
    />
  );
}

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

export default function ProfilePage({ onProfileSaved }) {
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    getProfile()
      .then((data) => {
        setProfile({
          ...EMPTY_PROFILE,
          ...data,
          customFields: data.customFields || {},
        });
      })
      .catch((err) => {
        showToast(`Failed to load profile: ${err.message}`, 'error');
      })
      .finally(() => setLoading(false));
  }, []);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const handleChange = useCallback((e) => {
    const { name, value } = e.target;
    setProfile((p) => ({ ...p, [name]: value }));
  }, []);

  const handleCustomFieldChange = useCallback((index, key, value) => {
    setProfile((p) => {
      const entries = Object.entries(p.customFields);
      entries[index] = [key, value];
      return { ...p, customFields: Object.fromEntries(entries) };
    });
  }, []);

  const addCustomField = useCallback(() => {
    setProfile((p) => ({
      ...p,
      customFields: { ...p.customFields, '': '' },
    }));
  }, []);

  const removeCustomField = useCallback((index) => {
    setProfile((p) => {
      const entries = Object.entries(p.customFields);
      entries.splice(index, 1);
      return { ...p, customFields: Object.fromEntries(entries) };
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveProfile(profile);
      const name = `${profile.firstName} ${profile.lastName}`.trim();
      onProfileSaved?.(name);
      showToast('Profile saved successfully!', 'success');
    } catch (err) {
      showToast(`Save failed: ${err.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <svg className="animate-spin h-7 w-7 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      </div>
    );
  }

  const customEntries = Object.entries(profile.customFields);

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Your Profile</h1>
        <p className="text-slate-500 text-sm mt-1">
          This data is used to fill job application forms automatically.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
        {/* Personal */}
        <SectionHeading>Personal</SectionHeading>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Salutation" hint="e.g. Mr., Ms., Dr., Mx.">
            <TextInput name="salutation" value={profile.salutation} onChange={handleChange} placeholder="Ms." />
          </Field>
          <Field label="First name">
            <TextInput name="firstName" value={profile.firstName} onChange={handleChange} placeholder="Jane" />
          </Field>
          <Field label="Last name">
            <TextInput name="lastName" value={profile.lastName} onChange={handleChange} placeholder="Smith" />
          </Field>
          <Field label="Email">
            <TextInput name="email" type="email" value={profile.email} onChange={handleChange} placeholder="jane@example.com" />
          </Field>
          <Field label="Phone country code" hint="e.g. +49 — prepended automatically when the form has no separate dial code field">
            <TextInput name="phoneCountryCode" type="tel" value={profile.phoneCountryCode} onChange={handleChange} placeholder="+49" />
          </Field>
          <Field label="Phone (without country code)">
            <TextInput name="phone" type="tel" value={profile.phone} onChange={handleChange} placeholder="151 23456789" />
          </Field>
          <Field label="Date of birth">
            <TextInput name="dateOfBirth" type="date" value={profile.dateOfBirth} onChange={handleChange} />
          </Field>
          <Field label="Nationality">
            <TextInput name="nationality" value={profile.nationality} onChange={handleChange} placeholder="e.g. American" />
          </Field>
        </div>

        {/* Address */}
        <div className="border-t border-slate-100 pt-4">
          <SectionHeading>Address</SectionHeading>
          <div className="grid grid-cols-1 gap-4">
            <Field label="Street address">
              <TextInput name="address" value={profile.address} onChange={handleChange} placeholder="123 Main St, Apt 4B" />
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-4 mt-4">
            <Field label="City">
              <TextInput name="city" value={profile.city} onChange={handleChange} placeholder="San Francisco" />
            </Field>
            <Field label="ZIP / Postal code">
              <TextInput name="zip" value={profile.zip} onChange={handleChange} placeholder="94102" />
            </Field>
            <Field label="Country">
              <TextInput name="country" value={profile.country} onChange={handleChange} placeholder="United States" />
            </Field>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Tip: use the form's language — e.g. "Deutschland" for German sites.
          </p>
        </div>

        {/* Links */}
        <div className="border-t border-slate-100 pt-4">
          <SectionHeading>Links</SectionHeading>
          <div className="grid grid-cols-1 gap-4">
            <Field label="LinkedIn">
              <TextInput name="linkedin" type="url" value={profile.linkedin} onChange={handleChange} placeholder="https://linkedin.com/in/janesmith" />
            </Field>
            <Field label="GitHub">
              <TextInput name="github" type="url" value={profile.github} onChange={handleChange} placeholder="https://github.com/janesmith" />
            </Field>
            <Field label="Portfolio / Website">
              <TextInput name="portfolio" type="url" value={profile.portfolio} onChange={handleChange} placeholder="https://janesmith.dev" />
            </Field>
          </div>
        </div>

        {/* Work */}
        <div className="border-t border-slate-100 pt-4">
          <SectionHeading>Work</SectionHeading>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Current title">
              <TextInput name="currentTitle" value={profile.currentTitle} onChange={handleChange} placeholder="Senior Engineer" />
            </Field>
            <Field label="Current company">
              <TextInput name="currentCompany" value={profile.currentCompany} onChange={handleChange} placeholder="Acme Corp" />
            </Field>
            <Field label="Years of experience">
              <TextInput name="yearsExp" value={profile.yearsExp} onChange={handleChange} placeholder="5" />
            </Field>
            <Field label="Work authorization">
              <TextInput name="workAuth" value={profile.workAuth} onChange={handleChange} placeholder="Authorized to work in the US" />
            </Field>
            <Field label="Salary expectation">
              <TextInput name="salaryExpect" value={profile.salaryExpect} onChange={handleChange} placeholder="$120,000" />
            </Field>
            <Field label="Notice period">
              <TextInput name="noticePeriod" value={profile.noticePeriod} onChange={handleChange} placeholder="2 weeks" />
            </Field>
            <Field label="Available start date">
              <TextInput name="startDate" type="date" value={profile.startDate} onChange={handleChange} />
            </Field>
          </div>
        </div>

        {/* Education */}
        <div className="border-t border-slate-100 pt-4">
          <SectionHeading>Education</SectionHeading>
          <div className="grid grid-cols-2 gap-4">
            <Field label="University / School">
              <TextInput name="university" value={profile.university} onChange={handleChange} placeholder="MIT" />
            </Field>
            <Field label="Degree">
              <TextInput name="degree" value={profile.degree} onChange={handleChange} placeholder="B.S. Computer Science" />
            </Field>
            <Field label="Graduation year">
              <TextInput name="gradYear" value={profile.gradYear} onChange={handleChange} placeholder="2019" />
            </Field>
          </div>
        </div>

        {/* Custom Fields */}
        <div className="border-t border-slate-100 pt-4">
          <SectionHeading>Custom Fields</SectionHeading>
          <p className="text-xs text-slate-400 mb-3">
            Add any additional fields you want the filler to use.
          </p>
          <div className="space-y-2">
            {customEntries.map(([key, value], index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  type="text"
                  value={key}
                  onChange={(e) => handleCustomFieldChange(index, e.target.value, value)}
                  placeholder="Field name"
                  className="block w-40 rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
                />
                <span className="text-slate-400 text-sm">→</span>
                <input
                  type="text"
                  value={value}
                  onChange={(e) => handleCustomFieldChange(index, key, e.target.value)}
                  placeholder="Value"
                  className="block flex-1 rounded-lg border-slate-200 bg-white text-slate-900 text-sm shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
                />
                <button
                  onClick={() => removeCustomField(index)}
                  className="text-slate-400 hover:text-red-500 transition-colors flex-shrink-0 p-1"
                  aria-label="Remove field"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={addCustomField}
            className="mt-3 text-sm text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clipRule="evenodd" />
            </svg>
            Add field
          </button>
        </div>
      </div>

      {/* Save button */}
      <div className="mt-6 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg shadow-sm transition-colors"
        >
          {saving && (
            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          )}
          {saving ? 'Saving…' : 'Save Profile'}
        </button>
      </div>

      {toast && <Toast message={toast.message} type={toast.type} />}
    </>
  );
}
