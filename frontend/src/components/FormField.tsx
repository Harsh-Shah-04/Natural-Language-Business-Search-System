interface FormFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string;
  required?: boolean;
  multiline?: boolean;
  type?: 'text' | 'email' | 'tel' | 'url';
  placeholder?: string;
  disabled?: boolean;
  /** When set, renders a <select> instead of a text input. */
  options?: readonly string[];
}

/** A labelled text input, textarea, or select with inline validation error.
 *  Reused for every registration field so labels, required markers, and error
 *  display stay consistent. */
export function FormField({
  id,
  label,
  value,
  onChange,
  onBlur,
  error,
  required,
  multiline,
  type = 'text',
  placeholder,
  disabled,
  options,
}: FormFieldProps) {
  const errorId = error ? `${id}-error` : undefined;
  const className = `form-field__input${error ? ' form-field__input--error' : ''}`;
  const shared = {
    id,
    value,
    onBlur,
    disabled,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': errorId,
    className,
  };

  return (
    <div className="form-field">
      <label className="form-field__label" htmlFor={id}>
        {label}
        {required && <span className="form-field__required" aria-hidden="true"> *</span>}
      </label>
      {options ? (
        <select
          {...shared}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">{placeholder ?? 'Select…'}</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : multiline ? (
        <textarea
          {...shared}
          placeholder={placeholder}
          rows={3}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          {...shared}
          type={type}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {error && (
        <p className="form-field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
