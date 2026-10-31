import type { ComponentProps } from "react";

const VARIANTS = {
  primary:
    "bg-amber-600 text-white hover:bg-amber-700 disabled:bg-amber-600/60 focus-visible:outline-amber-600",
  danger:
    "bg-red-700 text-white hover:bg-red-800 disabled:bg-red-700/50 focus-visible:outline-red-700",
  quiet:
    "text-stone-700 hover:bg-stone-200 disabled:text-stone-400 focus-visible:outline-stone-500 dark:text-stone-300 dark:hover:bg-stone-800",
} as const;

type ButtonProps = ComponentProps<"button"> & { variant?: keyof typeof VARIANTS };

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-md px-4 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
