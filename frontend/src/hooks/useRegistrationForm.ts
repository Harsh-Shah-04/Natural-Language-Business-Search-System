import { useCallback, useState } from 'react';

import { ApiError } from '../api/client';
import { registerBusiness } from '../api/businesses';
import type {
  BusinessRegistration,
  RegisteredBusiness,
  RegistrationField,
} from '../types/api';
import { EMAIL_RE, WEBSITE_RE } from '../types/api';

/** Declarative field config — drives both rendering and validation so the two
 *  never drift. Order here is the on-screen order. */
export interface FieldConfig {
  name: RegistrationField;
  label: string;
  required: boolean;
  multiline?: boolean;
  type?: 'text' | 'email' | 'tel' | 'url';
  placeholder?: string;
}

export const REGISTRATION_FIELDS: FieldConfig[] = [
  { name: 'business_name', label: 'Business Name', required: true },
  { name: 'industry', label: 'Industry', required: true },
  { name: 'nature', label: 'Nature of Business', required: true, placeholder: 'e.g. Goods or Services' },
  { name: 'sub_category', label: 'Sub Category', required: true },
  { name: 'business_description', label: 'Business Description', required: true, multiline: true },
  { name: 'products_services', label: 'Products / Services', required: true, multiline: true },
  { name: 'keywords', label: 'Keywords', required: false, multiline: true, placeholder: 'Comma-separated terms buyers might search' },
  { name: 'city', label: 'City', required: true },
  { name: 'state', label: 'State', required: true },
  { name: 'address', label: 'Address', required: false },
  { name: 'phone', label: 'Phone', required: false, type: 'tel' },
  { name: 'email', label: 'Email', required: false, type: 'email' },
  { name: 'website', label: 'Website', required: false, type: 'url', placeholder: 'example.com' },
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
