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
