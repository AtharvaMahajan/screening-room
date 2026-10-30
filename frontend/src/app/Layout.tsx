import { Link, Outlet } from "react-router";

/** The shell around every page. Pages render into <Outlet />. */
export function Layout() {
  return (
    <div className="layout">
      <header className="layout__header">
        <Link to="/" className="layout__brand">
          Screening Room
        </Link>
      </header>
      <main className="layout__main">
        <Outlet />
      </main>
    </div>
  );
}
