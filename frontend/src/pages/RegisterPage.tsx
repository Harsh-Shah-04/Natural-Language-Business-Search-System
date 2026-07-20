import { FormField } from '../components/FormField';
import { StatusMessage } from '../components/StatusMessage';
import {
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
      <div className="register-success">
        <StatusMessage
          variant="empty"
          title="Business registered"
          detail={`“${registered.business_name}” is now in the directory and searchable.`}
        />
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

      <div className="register-form__grid">
        {REGISTRATION_FIELDS.map((field) => (
          <div
            key={field.name}
            className={field.multiline ? 'register-form__cell--full' : undefined}
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
        ))}
      </div>

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
