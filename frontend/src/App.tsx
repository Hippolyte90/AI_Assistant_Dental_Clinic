import { useEffect, useState } from "react";
import { api } from "./api/client";
import { LogoMark } from "./components/Logo";
import { LoginPage } from "./pages/LoginPage";
import { SessionPage } from "./pages/SessionPage";
import type { AccountUser } from "./types";

type Access = "loading" | "signed-out" | "open" | "signed-in" | "offline";

export function App() {
  const [access, setAccess] = useState<Access>("loading");
  const [user, setUser] = useState<AccountUser | null>(null);

  useEffect(() => {
    api
      .authStatus()
      .then((status) => {
        setUser(status.user);
        setAccess(!status.required ? "open" : status.authenticated ? "signed-in" : "signed-out");
      })
      .catch(() => setAccess("offline"));
    const expired = () => {
      setUser(null);
      setAccess("signed-out");
    };
    window.addEventListener("cuspia:signed-out", expired);
    return () => window.removeEventListener("cuspia:signed-out", expired);
  }, []);

  if (access === "signed-out") {
    return (
      <LoginPage
        onSuccess={(signedIn) => {
          setUser(signedIn);
          setAccess("signed-in");
        }}
      />
    );
  }
  if (access === "loading" || access === "offline") {
    return (
      <main className="login">
        <div className="login-card" role="status">
          <LogoMark size={56} />
          <p className="muted">
            {access === "loading" ? "Loading…" : "Cuspia is unavailable right now."}
          </p>
        </div>
      </main>
    );
  }

  const signOut =
    access === "signed-in"
      ? () => {
          void api.logout().finally(() => {
            setUser(null);
            setAccess("signed-out");
          });
        }
      : undefined;
  return <SessionPage onSignOut={signOut} userName={user?.name} />;
}
