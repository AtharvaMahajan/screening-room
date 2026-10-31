import { Link, Outlet, useNavigate } from "react-router";

import { Button } from "../components/Button";
import { useLogout, useSession } from "../features/auth/api";
import { HealthStatus } from "../features/health/HealthStatus";

/** The shell around every page. Pages render into <Outlet />. */
export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-stone-200 dark:border-stone-800">
        {/* Phones: brand and account on one row, page links on a second row below. */}
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <Link to="/" className="font-semibold tracking-tight">
            Screening Room
          </Link>
          <AccountMenu />
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto w-full max-w-3xl px-4 py-4">
        <HealthStatus />
      </footer>
    </div>
  );
}

/** Page links, the signed-in user and a sign-out button; nothing when signed out. */
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
      <nav
        aria-label="Main"
        className="order-last flex w-full gap-4 text-sm sm:order-none sm:w-auto sm:gap-3"
      >
        <Link to="/" className="text-stone-700 hover:underline dark:text-stone-300">
          Discover
        </Link>
        <Link to="/search" className="text-stone-700 hover:underline dark:text-stone-300">
          Search
        </Link>
        <Link to="/library" className="text-stone-700 hover:underline dark:text-stone-300">
          Library
        </Link>
        <Link to="/taste" className="text-stone-700 hover:underline dark:text-stone-300">
          Your taste
        </Link>
      </nav>
      <div className="flex min-w-0 items-center gap-2 text-sm">
        {/* A long email is cut short rather than pushing "Sign out" off screen. */}
        <Link
          to="/account"
          className="max-w-28 truncate text-stone-600 hover:underline sm:max-w-40 dark:text-stone-400"
        >
          {user.display_name ?? user.email}
        </Link>
        <Button variant="quiet" onClick={signOut} disabled={logout.isPending}>
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
