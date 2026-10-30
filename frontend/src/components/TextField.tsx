import { type ComponentProps, useId } from "react";

type TextFieldProps = ComponentProps<"input"> & {
  label: string;
  error?: string | undefined;
  hint?: string;
};

/**
 * A labelled input with its hint or error text linked for screen readers.
 * Works with React Hook Form's `register()`, which passes `ref` as a prop.
 */
export function TextField({ label, error, hint, ...inputProps }: TextFieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;

  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
        className="block w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-base shadow-xs outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-600/30 aria-invalid:border-red-600 dark:border-stone-700 dark:bg-stone-900"
        {...inputProps}
      />
      {message && (
        <p
          id={messageId}
          className={error ? "text-sm text-red-600 dark:text-red-400" : "text-sm text-stone-500"}
        >
          {message}
        </p>
      )}
    </div>
  );
}
