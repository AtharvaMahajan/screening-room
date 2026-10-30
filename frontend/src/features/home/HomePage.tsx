import { HealthStatus } from "../health/HealthStatus";

export function HomePage() {
  return (
    <>
      <h1>Screening Room</h1>
      <p>Personalized movie and TV discovery. Recommendations arrive in a later milestone.</p>
      <HealthStatus />
    </>
  );
}
