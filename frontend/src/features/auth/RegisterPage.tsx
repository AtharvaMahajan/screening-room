import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, Navigate } from "react-router";
import { z } from "zod";

import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { TextField } from "../../components/TextField";
import { useRegister, useSession } from "./api";
import { AuthCard, FormError } from "./AuthCard";
import { showServerErrors } from "./formErrors";

// Mirror the backend's rules (core/security.py, identity/schemas.py) for quick
// feedback. The server still checks everything.
const PASSWORD_MIN = 10;
const PASSWORD_MAX = 128;

const schema = z.object({
  email: z.email({ error: "Enter a valid email address." }),
  display_name: z.string().trim().max(100, { error: "Use at most 100 characters." }),
  password: z
    .string()
    .min(PASSWORD_MIN, { error: `Use at least ${String(PASSWORD_MIN)} characters.` })
    .max(PASSWORD_MAX, { error: `Use at most ${String(PASSWORD_MAX)} characters.` }),
});
type RegisterValues = z.infer<typeof schema>;

export function RegisterPage() {
  const session = useSession();
  const registration = useRegister();
  const form = useForm<RegisterValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", display_name: "", password: "" },
  });

  // Registering signs the user in: a new account goes on to onboarding. Anyone
  // already signed in who opens this page just goes home.
  if (session.data?.user) {
    return <Navigate to={registration.isSuccess ? "/welcome" : "/"} replace />;
  }

  const onSubmit = form.handleSubmit(async ({ email, display_name, password }) => {
    try {
      await registration.mutateAsync({ email, password, display_name: display_name || null });
    } catch (error) {
      if (error instanceof ApiError && error.code === "email_unavailable") {
        form.setError("email", { message: error.message });
      } else {
        showServerErrors(error, form.setError, ["email", "display_name", "password"]);
      }
    }
  });
  const { errors, isSubmitting } = form.formState;

  return (
    <AuthCard
      title="Create your account"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/sign-in" className="font-medium text-amber-700 underline dark:text-amber-500">
            Sign in
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
          label="Name (optional)"
          autoComplete="name"
          error={errors.display_name?.message}
          {...form.register("display_name")}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          hint={`At least ${String(PASSWORD_MIN)} characters.`}
          error={errors.password?.message}
          {...form.register("password")}
        />
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthCard>
  );
}
