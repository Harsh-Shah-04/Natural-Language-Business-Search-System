import { useCallback, useState } from 'react';

import { ApiError } from '../api/client';
import { registerBusiness } from '../api/businesses';
import type {
  BusinessRegistration,
  RegisteredBusiness,
  RegistrationField,
} from '../types/api';
import { EMAIL_RE, WEBSITE_RE } from '../types/api';

export type FieldGroup = 'business' | 'location' | 'contact';

/** Declarative field config — drives both rendering and validation so the two
 *  never drift. Order here is the on-screen order. */
export interface FieldConfig {
  name: RegistrationField;
  label: string;
  group: FieldGroup;
  required: boolean;
  multiline?: boolean;
  type?: 'text' | 'email' | 'tel' | 'url';
  placeholder?: string;
  /** Constrained choices — renders as a select in FormField. */
  options?: readonly string[];
}

/** Section headings for the grouped registration form, in display order. */
export const FIELD_GROUPS: { id: FieldGroup; title: string }[] = [
  { id: 'business', title: 'Business Information' },
  { id: 'location', title: 'Location' },
  { id: 'contact', title: 'Contact Information' },
];

export const REGISTRATION_FIELDS: FieldConfig[] = [
  { name: 'business_name', label: 'Business Name', group: 'business', required: true },
  { name: 'industry', label: 'Industry', group: 'business', required: true },
  { name: 'nature', label: 'Nature of Business', group: 'business', required: true, placeholder: 'Select Goods or Services', options: ['Goods', 'Services'] as const },
  { name: 'sub_category', label: 'Sub Category', group: 'business', required: true },
  { name: 'business_description', label: 'Business Description', group: 'business', required: true, multiline: true },
  { name: 'products_services', label: 'Products / Services', group: 'business', required: true, multiline: true },
  { name: 'keywords', label: 'Keywords', group: 'business', required: false, multiline: true, placeholder: 'Comma-separated terms buyers might search' },
  { name: 'city', label: 'City', group: 'location', required: true },
  { name: 'state', label: 'State', group: 'location', required: true },
  { name: 'address', label: 'Address', group: 'location', required: false },
  { name: 'phone', label: 'Phone', group: 'contact', required: false, type: 'tel' },
  { name: 'email', label: 'Email', group: 'contact', required: false, type: 'email' },
  { name: 'website', label: 'Website', group: 'contact', required: false, type: 'url', placeholder: 'example.com' },
];

export type FormValues = Record<RegistrationField, string>;
export type FormErrors = Partial<Record<RegistrationField, string>>;
export type RegistrationStatus = 'editing' | 'submitting' | 'success' | 'error';

const EMPTY_VALUES: FormValues = {
  business_name: '',
  industry: '',
  nature: '',
  sub_category: '',
  business_description: '',
  products_services: '',
  keywords: '',
  city: '',
  state: '',
  address: '',
  phone: '',
  email: '',
  website: '',
};

/** Validate one field; returns an error message or undefined. */
function validateField(name: RegistrationField, value: string): string | undefined {
  const config = REGISTRATION_FIELDS.find((f) => f.name === name);
  const trimmed = value.trim();

  if (config?.required && trimmed === '') {
    return `${config.label} is required`;
  }
  if (trimmed === '') return undefined; // optional + empty is fine

  if (name === 'email' && !EMAIL_RE.test(trimmed)) {
    return 'Enter a valid email address';
  }
  if (name === 'website' && !WEBSITE_RE.test(trimmed)) {
    return 'Enter a valid website URL';
  }
  if (name === 'nature' && trimmed !== '' && trimmed !== 'Goods' && trimmed !== 'Services') {
    return 'Nature must be Goods or Services';
  }
  return undefined;
}

function validateAll(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  for (const field of REGISTRATION_FIELDS) {
    const error = validateField(field.name, values[field.name]);
    if (error) errors[field.name] = error;
  }
  return errors;
}

/** Build the API payload: trim everything, drop empty optionals. */
function toPayload(values: FormValues): BusinessRegistration {
  const payload: Record<string, string> = {};
  for (const field of REGISTRATION_FIELDS) {
    const trimmed = values[field.name].trim();
    if (trimmed !== '') payload[field.name] = trimmed;
  }
  return payload as unknown as BusinessRegistration;
}

/**
 * Owns registration form state: values, per-field errors, submit lifecycle.
 * Validation is field-level on blur and full on submit; the submit is blocked
 * until every field passes so the backend only ever sees well-formed input.
 */
export function useRegistrationForm() {
  const [values, setValues] = useState<FormValues>(EMPTY_VALUES);
  const [errors, setErrors] = useState<FormErrors>({});
  const [status, setStatus] = useState<RegistrationStatus>('editing');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [registered, setRegistered] = useState<RegisteredBusiness | null>(null);

  const setField = useCallback((name: RegistrationField, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    // Clear a field's error as the user edits it; re-checked on blur/submit.
    setErrors((prev) => (prev[name] ? { ...prev, [name]: undefined } : prev));
  }, []);

  const blurField = useCallback(
    (name: RegistrationField) => {
      setErrors((prev) => ({ ...prev, [name]: validateField(name, values[name]) }));
    },
    [values],
  );

  const reset = useCallback(() => {
    setValues(EMPTY_VALUES);
    setErrors({});
    setStatus('editing');
    setSubmitError(null);
    setRegistered(null);
  }, []);

  const submit = useCallback(async () => {
    const nextErrors = validateAll(values);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      setStatus('editing');
      return;
    }

    setStatus('submitting');
    setSubmitError(null);
    try {
      const result = await registerBusiness(toPayload(values));
      setRegistered(result);
      setStatus('success');
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Something went wrong while registering. Please try again.';
      setSubmitError(message);
      setStatus('error');
    }
  }, [values]);

  return {
    values,
    errors,
    status,
    submitError,
    registered,
    setField,
    blurField,
    submit,
    reset,
  };
}
