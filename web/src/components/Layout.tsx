import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import "./Layout.css";

export const ATTRIBUTION = "Built with Muse Spark Open";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="layout">
      <header className="layout-header">
        <Link to="/" className="wordmark" aria-label="Reel2Play home">
          <span className="wordmark-play" aria-hidden="true" />
          Reel2Play
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>
            Make a game
          </NavLink>
          <NavLink to="/try">Try it</NavLink>
          <NavLink to="/studio">Studio</NavLink>
          <NavLink to="/gallery">Gallery</NavLink>
        </nav>
      </header>
      <main className="layout-main">{children}</main>
      <footer className="layout-footer">
        <nav className="footer-nav" aria-label="More">
          <Link to="/templates">Game templates</Link>
          <Link to="/batch">Several products</Link>
          <Link to="/agency">Agency workspace</Link>
        </nav>
        <p>{ATTRIBUTION}</p>
      </footer>
    </div>
  );
}
