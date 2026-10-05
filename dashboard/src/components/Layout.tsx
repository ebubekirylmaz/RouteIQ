import { NavLink, Outlet } from "react-router-dom";

import styles from "./Layout.module.css";

const NAV = [
  { to: "review", label: "Review queue" },
  { to: "overview", label: "Overview" },
  { to: "charts", label: "Charts" },
  { to: "history", label: "History" },
];

export function Layout() {
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
