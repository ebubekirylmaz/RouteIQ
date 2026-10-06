import { NavLink, Outlet } from "react-router-dom";

import { useConfig } from "../hooks/useConfig";
import styles from "./Layout.module.css";

const NAV = [
  { to: "review", label: "Review queue" },
  { to: "overview", label: "Overview" },
  { to: "charts", label: "Charts" },
  { to: "evaluation", label: "Evaluation" },
  { to: "history", label: "History" },
  { to: "try", label: "Try it" },
];

export function Layout() {
  const config = useConfig();
  const synthetic = config.data?.data_source === "synthetic";
  const demo = config.data?.demo === true;

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <span className={styles.brand}>RouteIQ</span>
        <nav className={styles.nav} aria-label="Main">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      {demo && (
        <p className={styles.banner} role="note">
          <strong>Public demo.</strong> What you send is stored, can be seen by everyone using this demo, and is deleted when the demo
          resets, about once a day. Please do not enter personal data. The number of texts that can be sent is limited.
        </p>
      )}

      {synthetic && (
        <p className={styles.banner} role="note">
          <strong>Synthetic data.</strong> The configuration “{config.data?.domain}” was built from
          generated text. Its accuracy says nothing about real data.
        </p>
      )}

      <main className={styles.main}>
        <Outlet />
      </main>

      <footer className={styles.footer}>
        This dashboard shows customer texts and the API has no authentication. Use it on a trusted
        network or behind a gateway.
      </footer>
    </div>
  );
}
