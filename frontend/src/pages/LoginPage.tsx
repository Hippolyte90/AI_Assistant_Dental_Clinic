import { type FormEvent, useState } from "react";
import { api } from "../api/client";
import { LogoMark } from "../components/Logo";
import type { AccountUser } from "../types";

export function LoginPage({ onSuccess }: { onSuccess: (user: AccountUser | null) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const registering = mode === "register";

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError("");
    setPassword("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = registering
        ? await api.register(name, email, password)
        : await api.login(email, password);
      onSuccess(result.user);
    } catch (failure) {
      setError((failure as Error).message);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  const label = registering ? "Create account" : "Sign in";

  return (
    <main className="login">
      <div className="login-card">
        <LogoMark size={56} />
        <h1>Cuspia</h1>
        <p className="muted">
          {registering
            ? "Create your treatment planning workspace."
            : "Sign in to your treatment planning workspace."}
        </p>
        <div className="auth-tabs" role="tablist" aria-label="Account">
          <button
            type="button"
            role="tab"
            aria-selected={!registering}
            className={!registering ? "on" : ""}
            onClick={() => switchMode("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={registering}
            className={registering ? "on" : ""}
            onClick={() => switchMode("register")}
          >
            Create account
          </button>
        </div>
        <form onSubmit={submit}>
          {registering && (
            <label className="field">
              <span>Full name</span>
              <input
                value={name}
                maxLength={80}
                autoComplete="name"
                required
                onChange={(event) => setName(event.target.value)}
              />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              autoComplete="email"
              required
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              minLength={registering ? 8 : undefined}
              autoComplete={registering ? "new-password" : "current-password"}
              required
              onChange={(event) => setPassword(event.target.value)}
            />
            {registering && <small>At least 8 characters.</small>}
          </label>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary-wide" disabled={busy}>
            {busy ? "Please wait…" : label}
          </button>
        </form>
      </div>
    </main>
  );
}
