import { useState } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { TextField } from "../../components/TextField";
import { describeError } from "../../lib/errors";
import { useDeleteAccount, useSession } from "./api";

/** /account: who you're signed in as, and deleting the account (security.md §6). */
export function AccountPage() {
  const user = useSession().data?.user;
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const remove = useDeleteAccount(() => {
    void navigate("/goodbye", { replace: true });
  });
  const wrongPassword = remove.error instanceof ApiError && remove.error.code === "wrong_password";

  return (
    <div className="space-y-8 py-2">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Your account</h1>
        <p className="text-stone-600 dark:text-stone-400">
          Signed in as {user?.email}
          {user?.display_name && ` (${user.display_name})`}
        </p>
      </header>

      <section
        aria-labelledby="delete-heading"
        className="space-y-4 rounded-md border border-red-300 p-4 dark:border-red-900"
      >
        <h2 id="delete-heading" className="text-lg font-semibold">
          Delete account
        </h2>
        <p className="text-sm">
          This permanently deletes your account and everything in it: your taste profile, watchlist,
          viewing history, ratings, “not for me” list and recommendation history. It can't be
          undone.
        </p>
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (password) {
              remove.mutate(password);
            }
          }}
          className="space-y-3"
        >
          <TextField
            label="Your password, to confirm"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
            error={wrongPassword ? "That password isn't right." : undefined}
          />
          {remove.isError && !wrongPassword && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {describeError(remove.error)}
            </p>
          )}
          <Button type="submit" variant="danger" disabled={!password || remove.isPending}>
            {remove.isPending ? "Deleting…" : "Delete my account and all its data"}
          </Button>
        </form>
      </section>
    </div>
  );
}
