export default function Navbar() {
  return (
    <header className="navbar">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img">
            <path d="M4 14.2 12 7l8 7.2" />
            <path d="M7.2 13.4h9.6l-2.4 4.4H9.6z" />
          </svg>
        </div>
        <span className="brand-wordmark">PitchPoint</span>
      </div>
      <nav className="nav-links" aria-label="Primary">
        <a href="#reports">Reports</a>
        <a href="#history">History</a>
        <span className="beta-badge">Beta</span>
      </nav>
    </header>
  );
}
