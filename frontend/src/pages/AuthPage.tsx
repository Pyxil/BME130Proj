import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { ApiError, USE_MOCKS } from "../services/api";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(USE_MOCKS ? "demo@example.com" : "");
  const [password, setPassword] = useState(USE_MOCKS ? "practice123" : "");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name);
      navigate("/practice");
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const input = "mt-1 block min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-lg dark:border-slate-700 dark:bg-slate-900";
  return (
    <div className="mx-auto max-w-md space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="mt-2 text-slate-700 dark:text-slate-300">Practise words, hear examples and track your progress.</p>
      </div>
      <Card>
        <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
          {mode === "register" && (
            <div>
              <label htmlFor="name" className="font-bold">Your name (optional)</label>
              <input id="name" className={input} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </div>
          )}
          <div>
            <label htmlFor="email" className="font-bold">Email</label>
            <input id="email" type="email" required className={input} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </div>
          <div>
            <label htmlFor="password" className="font-bold">Password</label>
            <input id="password" type="password" required minLength={8} className={input} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"}
              aria-describedby="pw-help" />
            <p id="pw-help" className="mt-1 text-sm text-slate-600 dark:text-slate-400">At least 8 characters.</p>
          </div>
          {error && <Alert kind="error">{error}</Alert>}
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>
      </Card>
      <p className="text-center">
        {mode === "login" ? (
          <>New here? <Link to="/register" className="font-bold text-brand-800 underline dark:text-brand-200">Create an account</Link></>
        ) : (
          <>Already have an account? <Link to="/login" className="font-bold text-brand-800 underline dark:text-brand-200">Sign in</Link></>
        )}
      </p>
    </div>
  );
}
