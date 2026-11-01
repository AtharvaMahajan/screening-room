/** Small line icons for the main navigation. Decorative: the link text names them. */
import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="h-4 w-4 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export function DiscoverIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5 L13.5 13.5 L8.5 15.5 L10.5 10.5 Z" />
    </Icon>
  );
}

export function SearchIcon() {
  return (
    <Icon>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20 L16 16" />
    </Icon>
  );
}

export function LibraryIcon() {
  return (
    <Icon>
      <path d="M6 4 H18 V20 L12 16 L6 20 Z" />
    </Icon>
  );
}

export function TasteIcon() {
  return (
    <Icon>
      <path d="M12 20 C6 16 3 12.5 3 9 A4.5 4.5 0 0 1 12 7 A4.5 4.5 0 0 1 21 9 C21 12.5 18 16 12 20 Z" />
    </Icon>
  );
}

export function AccountIcon() {
  return (
    <Icon>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21 C4 16.5 7.5 14 12 14 C16.5 14 20 16.5 20 21" />
    </Icon>
  );
}
