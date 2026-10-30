import { useSession } from "../auth/api";

/** Home, for signed-in users only (behind RequireAuth). */
export function HomePage() {
  const user = useSession().data?.user;

  return (
    <div className="space-y-3 py-4">
      <h1 className="text-2xl font-semibold tracking-tight">
        Welcome{user ? `, ${user.display_name ?? user.email}` : ""}
      </h1>
      <p className="text-stone-600 dark:text-stone-400">
        Personalized recommendations arrive in a later milestone. For now, you're signed in and
        everything is set up.
      </p>
    </div>
  );
}
