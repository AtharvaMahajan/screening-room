import type { ReactNode } from "react";

/** The shared frame of the sign-in and registration pages. */
export function AuthCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-sm py-8">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="rounded-lg border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900">
        {children}
      </div>
      <p className="mt-4 text-center text-sm text-stone-600 dark:text-stone-400">{footer}</p>
    </div>
  );
}

/** A form-level error, announced to screen readers. */
export function FormError({ message }: { message: string | undefined }) {
  if (!message) {
    return null;
  }
  return (
    <p
      role="alert"
      className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
    >
      {message}
    </p>
  );
}
