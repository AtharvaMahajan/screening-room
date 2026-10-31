import { useEffect } from "react";
import { Link } from "react-router";

import { useRefreshSession } from "./api";
import { AuthCard } from "./AuthCard";

/**
 * /goodbye: shown after deleting an account. Public (outside the sign-in guard),
 * so it can update the session to "signed out" without being redirected away.
 */
export function GoodbyePage() {
  const refreshSession = useRefreshSession();
  useEffect(() => {
    void refreshSession();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- once, on arrival

  return (
    <AuthCard
      title="Account deleted"
      footer={
        <Link to="/register" className="font-medium text-amber-700 underline dark:text-amber-500">
          Create a new account
        </Link>
      }
    >
      <p role="status">Your account and all its data were deleted.</p>
    </AuthCard>
  );
}
