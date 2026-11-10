import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../services/api";
import { api } from "../services/endpoints";

export default function SettingsPage() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [confirmText, setConfirmText] = useState("");
  if (!user) return null;

  const save = async (patch: Parameters<typeof api.updateMe>[0], text = "Saved.") => {
    try {
      setUser(await api.updateMe(patch));
      setMsg({ kind: "success", text });
    } catch (e) {
      setMsg({ kind: "error", text: (e as ApiError).message });
    }
  };
  const run = async (fn: () => Promise<unknown>, text: string) => {
    try {
      await fn();
      setMsg({ kind: "success", text });
    } catch (e) {
      setMsg({ kind: "error", text: (e as ApiError).message });
    }
  };
  const exportData = async () => {
    const data = await api.exportData();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "my-pronunciation-data.json";
    a.click();
    URL.revokeObjectURL(url);
  };
  const select = "mt-1 min-h-12 rounded-xl border border-slate-300 bg-white px-3 text-lg dark:border-slate-700 dark:bg-slate-900";

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Settings</h1>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <Card className="space-y-5">
        <h2 className="text-xl font-bold">Profile</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="font-bold">Name
            <input className={`${select} w-full`} defaultValue={user.display_name}
              onBlur={(e) => e.target.value !== user.display_name && void save({ display_name: e.target.value })} />
          </label>
          <label className="font-bold">Example accent
            <select className={`${select} w-full`} value={user.preferred_accent}
              onChange={(e) => void save({ preferred_accent: e.target.value as "us" | "gb" })}>
              <option value="us">American English</option>
              <option value="gb">British English</option>
            </select>
          </label>
          <label className="font-bold">Feedback style
            <select className={`${select} w-full`} value={user.audience}
              onChange={(e) => void save({ audience: e.target.value as "adult" | "child" })}>
              <option value="adult">Adult</option>
              <option value="child">Child-friendly</option>
            </select>
          </label>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400">Both American and British pronunciations are always accepted when scoring.</p>
      </Card>

      <Card className="space-y-4">
        <h2 className="text-xl font-bold">Privacy</h2>
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1.5 h-6 w-6 accent-brand-700" checked={user.store_recordings_consent}
            onChange={(e) => void save({ store_recordings_consent: e.target.checked },
              e.target.checked ? "Recordings will be saved so you can listen back." : "New recordings will not be saved.")} />
          <span>
            <span className="block text-lg font-bold">Save my recordings</span>
            <span className="text-slate-700 dark:text-slate-300">
              Off by default. When on, your recordings are stored on the server so you can replay them in History.
              When off, audio is analysed and then discarded; only scores are kept.
            </span>
          </span>
        </label>
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => void run(api.deleteRecordings, "All saved recordings were deleted.")}>Delete all recordings</Button>
          <Button variant="secondary" onClick={() => void run(exportData, "Your data was downloaded.")}>Download my data</Button>
          <Button variant="secondary" onClick={() => void run(api.deleteData, "All practice data was deleted.")}>Delete practice history</Button>
        </div>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-xl font-bold text-rose-800 dark:text-rose-300">Delete account</h2>
        <p>This permanently deletes your account, scores and recordings. Type <strong>DELETE</strong> to confirm.</p>
        <div className="flex flex-wrap gap-3">
          <input aria-label="Type DELETE to confirm" className={select} value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          <Button variant="danger" disabled={confirmText !== "DELETE"}
            onClick={() => void api.deleteAccount().then(() => { logout(); navigate("/register"); })}>
            Delete my account
          </Button>
        </div>
      </Card>
    </div>
  );
}
