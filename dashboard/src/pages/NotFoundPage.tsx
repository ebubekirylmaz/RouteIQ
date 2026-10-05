import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section>
      <h1>Page not found</h1>
      <p>
        <Link to="/review">Back to the review queue</Link>
      </p>
    </section>
  );
}
