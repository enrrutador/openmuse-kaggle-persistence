"""Parche auto-heal para OpenMuse upstream (idempotente).

1. apps/server/src/app.ts :: /api/main-thread
   Si Intelligence devuelve THREAD_NOT_FOUND/404 para el hilo guardado,
   borra el registro local y crea un UUID fresco (existing:false).
   Sin esto, un hilo borrado en la plataforma deja el chat en 404 eterno.
2. apps/server/src/app.ts :: /api/copilotkit/*
   Traduce THREAD_NOT_FOUND a 409 con mensaje accionable en vez de
   "404 404 page not found".
3. apps/mobile/src/threads.tsx :: ThreadsProvider
   En catch faltaba setLoading(false) -> spinner eterno y menú inutilizable.
4. apps/server/src/app.ts :: GET /api/models + POST /api/models/select
   Selector de modelos del gateway NVIDIA sin reiniciar (config.model vive
   en memoria y se lee por turno). Persiste en DATA_DIR/model-override.json.
5. apps/mobile/src/agent-ui.tsx :: ModelSelector en AppsScreen
   Dropdown con filtro para elegir modelo desde la app (Apps & settings).
"""
from __future__ import annotations

from pathlib import Path

MARK = "// openmuse-kaggle-persistence thread-heal v13"


def _patch(path: Path, old: str, new: str, already: str) -> bool:
    try:
        text = path.read_text()
    except FileNotFoundError:
        print(f"  [patch] no existe {path}, salto")
        return False
    if already in text:
        print(f"  [patch] {path.name} ya parcheado ({already[:28]}...) ✓")
        return True
    if old not in text:
        print(f"  [patch] WARN: no encontré el bloque en {path.name}, salto")
        return False
    path.write_text(text.replace(old, new, 1))
    print(f"  [patch] {path.name} parcheado ✓")
    return True


def apply(openmuse_dir: Path) -> None:
    app = openmuse_dir / "apps" / "server" / "src" / "app.ts"
    threads = openmuse_dir / "apps" / "mobile" / "src" / "threads.tsx"

    old_main = """    try {
      await intelligence.getOrCreateThread({
        threadId: main.threadId,
        userId: owner,
        agentId: "default",
      });
    } catch {
      throw new AppError(
        "Main conversation is unavailable. Check the Rich Threads connection and try again.",
        502,
      );
    }
    return c.json({ threadId: main.threadId, existing: true });"""

    new_main = """    """ + MARK + """
    try {
      await intelligence.getOrCreateThread({
        threadId: main.threadId,
        userId: owner,
        agentId: "default",
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("THREAD_NOT_FOUND") || msg.includes("404")) {
        // Hilo borrado en Intelligence: regenerar UUID fresco.
        const fresh = randomUUID();
        try {
          await db.remove(owner, "conversation-settings", "main");
        } catch {
          /* seguir igual */
        }
        await db.put(owner, "conversation-settings", { id: "main", threadId: fresh });
        await intelligence.getOrCreateThread({ threadId: fresh, userId: owner, agentId: "default" });
        return c.json({ threadId: fresh, existing: false });
      }
      throw new AppError(
        "Main conversation is unavailable. Check the Rich Threads connection and try again.",
        502,
      );
    }
    return c.json({ threadId: main.threadId, existing: true });"""

    _patch(app, old_main, new_main, "threadId: fresh, existing: false")

    old_copilot = """  app.all("/api/copilotkit/*", async (c) => {
    if (!agentConfigured(config))
      throw new AppError(
        "Configure a model and provider API key, or a valid AG-UI endpoint, to start chat",
        503,
      );
    const response = await runtime.fetch(c.req.raw);"""

    new_copilot = """  app.all("/api/copilotkit/*", async (c) => {
    if (!agentConfigured(config))
      throw new AppError(
        "Configure a model and provider API key, or a valid AG-UI endpoint, to start chat",
        503,
      );
    let response;
    try {
      response = await runtime.fetch(c.req.raw);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("THREAD_NOT_FOUND") || (msg.includes("404") && msg.includes("Thread"))) {
        throw new AppError(
          "This conversation was deleted on CopilotKit Intelligence. Start a new chat (menu -> New side chat). If it persists, re-run the Kaggle cell with RESET_DATA=true.",
          409,
        );
      }
      throw e;
    }"""

    _patch(app, old_copilot, new_copilot, "New side chat). If it persists")

    old_catch = """      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : String(e));
      });"""

    new_catch = """      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });"""

    _patch(threads, old_catch, new_catch, "setLoading(false);\n      });")

    # 4a. imports fs/path para model-override.json
    _patch(
        app,
        'import { AppError } from "./errors.ts";',
        'import { AppError } from "./errors.ts";\n'
        'import { writeFile } from "node:fs/promises";\n'
        'import { join } from "node:path";',
        '"node:fs/promises"',
    )

    # 4b. endpoints del selector antes de /api/main-thread
    old_main_anchor = '  app.get("/api/main-thread", async (c) => {'
    new_endpoints = """  // openmuse-kaggle-persistence model-selector v18
  const MODEL_OVERRIDE_FILE = join(config.dataDir, "model-override.json");
  async function gatewayModels(): Promise<string[]> {
    const base = (process.env.OPENAI_BASE_URL ?? "").replace(/\\/$/, "");
    const key = process.env.OPENAI_API_KEY ?? "";
    if (!base || !key) return [];
    try {
      const r = await fetch(`${base}/models`, {
        headers: { Authorization: `Bearer ${key}` },
      });
      if (!r.ok) return [];
      const j = (await r.json()) as { data?: { id?: string }[] };
      return [...new Set((j.data ?? []).map((m) => m?.id).filter((x): x is string => Boolean(x)))].sort();
    } catch {
      return [];
    }
  }
  app.get("/api/models", async (c) => {
    return c.json({
      current: config.model ?? null,
      gateway: process.env.OPENAI_BASE_URL ?? null,
      models: await gatewayModels(),
    });
  });
  app.post("/api/models/select", async (c) => {
    const body = z.object({ model: z.string().min(3).max(200) }).parse(await c.req.json());
    const spec = body.model.trim();
    if (!/^openai\\/[A-Za-z0-9_.\\-/]+$/.test(spec))
      throw new AppError("Elegí un modelo de la lista (formato openai/<id>).", 400);
    config.model = spec;
    try {
      await writeFile(MODEL_OVERRIDE_FILE, JSON.stringify({ model: spec }), "utf8");
    } catch {
      /* sigue en memoria igual */
    }
    return c.json({ ok: true, model: spec });
  };
  app.get("/api/main-thread", async (c) => {"""
    _patch(app, old_main_anchor, new_endpoints, "model-selector v18")

    # 5. ModelSelector en la app móvil (pantalla Apps & settings)
    agent_ui = openmuse_dir / "apps" / "mobile" / "src" / "agent-ui.tsx"
    old_apps_anchor = "export function AppsScreen() {"
    new_selector = """function ModelSelector() {
  const { api } = useWorkspace();
  const [current, setCurrent] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!expanded) return;
    let active = true;
    setError("");
    void api
      .request<{ current: string | null; models: string[] }>("/api/models")
      .then((r) => {
        if (!active) return;
        setCurrent(r.current || "");
        setModels(r.models || []);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      active = false;
    };
  }, [api, expanded]);
  async function select(id: string) {
    setBusy(true);
    setError("");
    try {
      const r = await api.request<{ model: string }>(
        "/api/models/select",
        { model: `openai/${id}` },
        "POST",
      );
      setCurrent(r.model);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const short = (id: string) => id.split("/").pop() || id;
  const shown = models
    .filter((id) => id.toLowerCase().includes(filter.toLowerCase()))
    .slice(0, 30);
  return (
    <View style={{ gap: 10 }}>
      <Button onPress={() => setExpanded(!expanded)}>
        {expanded ? "Close model selector" : `Model: ${short(current.replace(/^openai\\//, "")) || "…"}`}
      </Button>
      {expanded && (
        <Card style={{ gap: 10 }}>
          <ErrorNotice error={error} />
          <Field
            label="Filter models"
            value={filter}
            onChangeText={setFilter}
            placeholder="e.g. glm, kimi, nemotron"
          />
          {shown.map((id) => (
            <Button
              key={id}
              small
              primary={current === `openai/${id}`}
              disabled={busy}
              onPress={() => void select(id)}
            >
              {short(id)}
            </Button>
          ))}
          {models.length > shown.length && (
            <Text style={s.small}>
              Showing {shown.length} of {models.length} — refine the filter.
            </Text>
          )}
          {!models.length && !error && <ActivityIndicator color={colors.blueDark} />}
        </Card>
      )}
    </View>
  );
}
export function AppsScreen() {"""
    _patch(agent_ui, old_apps_anchor, new_selector, "function ModelSelector()")

    _patch(
        agent_ui,
        "      <ConnectionsScreen query={query} />",
        "      <ConnectionsScreen query={query} />\n      <ModelSelector />",
        "<ModelSelector />",
    )
