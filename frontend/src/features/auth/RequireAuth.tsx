import { Navigate, Outlet, useLocation } from "react-router";

import { Button } from "../../components/Button";
import { useSession } from "./api";
import { describeError } from "./formErrors";
import { signInPath } from "./redirect";

/**
 * Route guard: renders the child routes only for a signed-in user. Anyone else
 * goes to sign-in, and comes back here afterwards.
 */
export function RequireAuth() {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    return <p className="py-8 text-stone-500">Loading…</p>;
  }
  if (session.isError) {
    return (
      <div className="space-y-3 py-8">
        <p role="alert">{describeError(session.error)}</p>
        <Button variant="quiet" onClick={() => void session.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  if (!session.data.user) {
    return <Navigate to={signInPath(location.pathname + location.search)} replace />;
  }
  return <Outlet />;
}
