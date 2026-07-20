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
}

/** A labelled text input or textarea with inline validation error. Reused for
 *  every registration field so labels, required markers, and error display
 *  stay consistent. */
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
}: FormFieldProps) {
  const errorId = error ? `${id}-error` : undefined;
  const shared = {
    id,
    value,
    onBlur,
    disabled,
    placeholder,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': errorId,
    className: `form-field__input${error ? ' form-field__input--error' : ''}`,
    onChange: (
      e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) => onChange(e.target.value),
  };

  return (
    <div className="form-field">
      <label className="form-field__label" htmlFor={id}>
        {label}
        {required && <span className="form-field__required" aria-hidden="true"> *</span>}
      </label>
      {multiline ? (
        <textarea {...shared} rows={3} />
      ) : (
        <input {...shared} type={type} />
      )}
      {error && (
        <p className="form-field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
