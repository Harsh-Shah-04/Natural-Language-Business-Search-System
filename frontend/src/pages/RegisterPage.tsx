import { FormField } from '../components/FormField';
import {
  FIELD_GROUPS,
  REGISTRATION_FIELDS,
  useRegistrationForm,
} from '../hooks/useRegistrationForm';

interface RegisterPageProps {
  /** Called when the user chooses to search the business they just registered. */
  onSearchBusiness: (businessName: string) => void;
}

export function RegisterPage({ onSearchBusiness }: RegisterPageProps) {
  const {
    values,
    errors,
    status,
    submitError,
    registered,
    setField,
    blurField,
    submit,
    reset,
  } = useRegistrationForm();

  if (status === 'success' && registered) {
    return (
      <div className="register-success" role="status">
        <div className="register-success__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m5 13 4 4L19 7"
            />
          </svg>
        </div>
        <h2 className="register-success__title">Business registered</h2>
        <p className="register-success__detail">
          <strong>{registered.business_name}</strong> is now in the directory and
          searchable through the existing search pipeline.
        </p>
        <div className="register-success__actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => onSearchBusiness(registered.business_name)}
          >
            Search this business
          </button>
          <button type="button" className="button button--ghost" onClick={reset}>
            Register another
          </button>
        </div>
      </div>
    );
  }

  const submitting = status === 'submitting';

  return (
    <form
      className="register-form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <p className="register-form__hint">
        Fields marked <span className="form-field__required">*</span> are required.
      </p>

      {FIELD_GROUPS.map((group) => (
        <fieldset key={group.id} className="register-form__group">
          <legend className="register-form__legend">{group.title}</legend>
          <div className="register-form__grid">
            {REGISTRATION_FIELDS.filter((field) => field.group === group.id).map(
              (field) => (
                <div
                  key={field.name}
                  className={
                    field.multiline ? 'register-form__cell--full' : undefined
                  }
                >
                  <FormField
                    id={`reg-${field.name}`}
                    label={field.label}
                    value={values[field.name]}
                    onChange={(value) => setField(field.name, value)}
                    onBlur={() => blurField(field.name)}
                    error={errors[field.name]}
                    required={field.required}
                    multiline={field.multiline}
                    type={field.type}
                    placeholder={field.placeholder}
                    disabled={submitting}
                  />
                </div>
              ),
            )}
          </div>
        </fieldset>
      ))}

      {status === 'error' && submitError && (
        <p className="register-form__submit-error" role="alert">
          {submitError}
        </p>
      )}

      <div className="register-form__actions">
        <button
          type="submit"
          className="button button--primary"
          disabled={submitting}
        >
          {submitting ? 'Registering…' : 'Register business'}
        </button>
      </div>
    </form>
  );
}
