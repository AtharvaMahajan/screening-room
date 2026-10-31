import { Link, Outlet, useNavigate } from "react-router";

import { Button } from "../components/Button";
import { useLogout, useSession } from "../features/auth/api";
import { HealthStatus } from "../features/health/HealthStatus";

/** The shell around every page. Pages render into <Outlet />. */
export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-stone-200 dark:border-stone-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3">
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
    <div className="flex items-center gap-3 text-sm">
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
      <span className="text-stone-600 dark:text-stone-400">{user.display_name ?? user.email}</span>
      <Button variant="quiet" onClick={signOut} disabled={logout.isPending}>
        {logout.isPending ? "Signing out…" : "Sign out"}
      </Button>
      {logout.isError && (
        <span role="alert" className="text-red-600">
          Couldn't sign out. Try again.
        </span>
      )}
    </div>
  );
}
