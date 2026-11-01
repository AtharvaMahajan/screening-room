import type { ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";

import { Button } from "../components/Button";
import {
  AccountIcon,
  DiscoverIcon,
  LibraryIcon,
  SearchIcon,
  TasteIcon,
} from "../components/icons";
import { Logo } from "../components/Logo";
import { TmdbAttribution } from "../features/about/TmdbAttribution";
import { useLogout, useSession } from "../features/auth/api";
import { HealthStatus } from "../features/health/HealthStatus";

/** The shell around every page. Pages render into <Outlet />. */
export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      {/* First stop for keyboard users: past the header, straight to the page. Hidden
          until focused. Moves focus itself, so the URL doesn't gain a #main. */}
      <a
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
        className="sr-only rounded-md bg-amber-700 px-3 py-2 text-sm font-medium text-white focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-10"
      >
        Skip to main content
      </a>
      <header className="border-b border-stone-200 dark:border-stone-800">
        {/* Two rows on every screen: logo and account, then the page tabs. */}
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 pt-3">
          <Link to="/" className="rounded-md">
            <Logo />
          </Link>
          <AccountMenu />
        </div>
        <MainNav />
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 outline-none">
        <Outlet />
      </main>
      <footer className="mx-auto w-full max-w-3xl space-y-2 px-4 py-4">
        <HealthStatus />
        <TmdbAttribution />
      </footer>
    </div>
  );
}

const PAGES: { to: string; label: string; icon: ReactNode }[] = [
  { to: "/", label: "Discover", icon: <DiscoverIcon /> },
  { to: "/search", label: "Search", icon: <SearchIcon /> },
  { to: "/library", label: "Library", icon: <LibraryIcon /> },
  { to: "/taste", label: "Your taste", icon: <TasteIcon /> },
];

/** The page tabs: a pill each, the current one highlighted (and announced as current). */
function MainNav() {
  const user = useSession().data?.user;
  if (!user) {
    return <div className="pb-3" />;
  }
  return (
    <nav aria-label="Main" className="mx-auto max-w-3xl px-4 pt-2 pb-2">
      <ul className="-mx-1 flex gap-1 overflow-x-auto">
        {PAGES.map((page) => (
          <li key={page.to}>
            <NavLink
              to={page.to}
              className={({ isActive }) =>
                `flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium whitespace-nowrap focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 ${
                  isActive
                    ? "bg-amber-700 text-white shadow-sm"
                    : "text-stone-700 hover:bg-stone-200 dark:text-stone-300 dark:hover:bg-stone-800"
                }`
              }
            >
              {/* Icons from tablet width up: on phones the four labels need the room. */}
              <span className="hidden sm:inline-flex">{page.icon}</span>
              {page.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The signed-in user and a sign-out button; nothing when signed out. */
function AccountMenu() {
  const session = useSession();
  const logout = useLogout();
  const navigate = useNavigate();
  const user = session.data?.user;

  if (!user) {
    return null;
  }

  const signOut = () => {
    logout.mutate(undefined, {
      onSuccess: () => {
        void navigate("/sign-in", { replace: true });
      },
    });
  };

  return (
    <>
      <div className="flex min-w-0 items-center gap-2 text-sm">
        {/* A long email is cut short rather than pushing "Sign out" off screen. */}
        <Link
          to="/account"
          className="flex items-center rounded-full text-stone-600 hover:underline dark:text-stone-400"
        >
          {/* Phones: an icon. The name stays the link's accessible name either way. */}
          <span className="p-1 sm:hidden">
            <AccountIcon />
          </span>
          <span className="sr-only sm:not-sr-only sm:inline-block sm:max-w-40 sm:truncate">
            {user.display_name ?? user.email}
          </span>
        </Link>
        <Button
          variant="quiet"
          onClick={signOut}
          disabled={logout.isPending}
          className="px-2 whitespace-nowrap sm:px-4"
        >
          {logout.isPending ? "Signing out…" : "Sign out"}
        </Button>
        {logout.isError && (
          <span role="alert" className="text-red-600">
            Couldn't sign out. Try again.
          </span>
        )}
      </div>
    </>
  );
}
