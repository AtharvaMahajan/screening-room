import type { RouteObject } from "react-router";

import { RegisterPage } from "../features/auth/RegisterPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { SignInPage } from "../features/auth/SignInPage";
import { HomePage } from "../features/home/HomePage";
import { TitlePage } from "../features/titles/TitlePage";
import { Layout } from "./Layout";
import { NotFoundPage } from "./NotFoundPage";

// The route table, kept separate from the router instance so tests can mount
// it in a memory router.
export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      // Signed-in users only: everyone else is sent to sign-in.
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "titles/:titleId", element: <TitlePage /> },
        ],
      },
      { path: "sign-in", element: <SignInPage /> },
      { path: "register", element: <RegisterPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
