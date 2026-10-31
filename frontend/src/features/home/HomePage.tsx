import { Link } from "react-router";

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
        The Discover page arrives next. Meanwhile, you can{" "}
        <Link to="/taste" className="text-amber-700 underline dark:text-amber-500">
          tell us your taste
        </Link>
        .
      </p>
    </div>
  );
}
