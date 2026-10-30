import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="space-y-3 py-4">
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p>
        <Link to="/" className="text-amber-700 underline dark:text-amber-500">
          Go to the home page
        </Link>
      </p>
    </div>
  );
}
