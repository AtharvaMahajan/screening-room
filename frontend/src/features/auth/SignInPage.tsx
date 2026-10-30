import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, Navigate, useSearchParams } from "react-router";
import { z } from "zod";

import { Button } from "../../components/Button";
import { TextField } from "../../components/TextField";
import { useLogin, useSession } from "./api";
import { AuthCard, FormError } from "./AuthCard";
import { showServerErrors } from "./formErrors";
import { safeNextPath } from "./redirect";

const schema = z.object({
  email: z.email({ error: "Enter a valid email address." }),
  // Only "not empty" here: a short password is just a wrong password.
  password: z.string().min(1, { error: "Enter your password." }),
});
type SignInValues = z.infer<typeof schema>;

export function SignInPage() {
  const session = useSession();
  const login = useLogin();
  const [searchParams] = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const form = useForm<SignInValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  // Signed in (already, or just now: a successful login updates the session).
  if (session.data?.user) {
    return <Navigate to={next} replace />;
  }

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await login.mutateAsync(values);
    } catch (error) {
      showServerErrors(error, form.setError, ["email", "password"]);
    }
  });
  const { errors, isSubmitting } = form.formState;

  return (
    <AuthCard
      title="Sign in"
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="font-medium text-amber-700 underline dark:text-amber-500">
            Create an account
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-4">
        <FormError message={errors.root?.server?.message} />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register("email")}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...form.register("password")}
        />
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthCard>
  );
}
