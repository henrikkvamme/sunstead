import { Field } from "@base-ui-components/react/field";
import { Input } from "@base-ui-components/react/input";
import { Switch } from "@base-ui-components/react/switch";
import { Tabs } from "@base-ui-components/react/tabs";
import { createFileRoute, useRouter } from "@tanstack/react-router";
import { Droplets, Plus, RefreshCw, Sprout, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { createPlant, deletePlant, flagPlantForWater, listPlants, waterPlant } from "#/lib/plants";
import { lightLevels, rooms } from "#/lib/plants.shared";

export const Route = createFileRoute("/")({
  loader: async () => listPlants(),
  component: Home,
});

type Plant = Awaited<ReturnType<typeof listPlants>>[number];
type Filter = "all" | "needs-water";

function Home() {
  const plants = Route.useLoaderData();
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("all");
  const [status, setStatus] = useState("Loaded plants from SQLite through a server function.");
  const [isPending, setIsPending] = useState(false);

  const visiblePlants = useMemo(() => {
    if (filter === "needs-water") {
      return plants.filter((plant) => plant.needsWater);
    }

    return plants;
  }, [filter, plants]);

  const needsWaterCount = plants.filter((plant) => plant.needsWater).length;

  async function refreshPlants(message = "Refreshed the route loader.") {
    await router.invalidate();
    setStatus(message);
  }

  function runRequest(request: () => Promise<void>) {
    setIsPending(true);
    void request()
      .catch((error: unknown) => {
        setStatus(error instanceof Error ? error.message : "The request failed.");
      })
      .finally(() => {
        setIsPending(false);
      });
  }

  return (
    <main className="min-h-screen bg-[canvas] text-slate-950">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 py-8 sm:px-8 lg:py-10">
        <header className="grid gap-5 border-b border-slate-200 pb-7 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="max-w-3xl">
            <p className="eyebrow">TanStack Start + Drizzle + Base UI</p>
            <h1 className="mt-3 text-4xl font-semibold tracking-normal text-slate-950 sm:text-5xl">
              Sunstead plant care console
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
              A working example of loader reads, server-function mutations, SQLite/libSQL
              persistence, and unstyled Base UI primitives with app-level styling.
            </p>
          </div>
          <button
            className="button secondary w-fit"
            disabled={isPending}
            type="button"
            onClick={() =>
              runRequest(async () => {
                await refreshPlants("Requested a fresh plant list from the database.");
              })
            }
          >
            <RefreshCw aria-hidden size={18} />
            Refresh
          </button>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <section className="space-y-5">
            <Tabs.Root value={filter} onValueChange={(value) => setFilter(value as Filter)}>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <Tabs.List className="tabs-list" aria-label="Plant list filters">
                  <Tabs.Tab className="tab" value="all">
                    All plants
                  </Tabs.Tab>
                  <Tabs.Tab className="tab" value="needs-water">
                    Needs water
                    <span className="tab-count">{needsWaterCount}</span>
                  </Tabs.Tab>
                  <Tabs.Indicator className="tab-indicator" />
                </Tabs.List>
                <p className="request-status" aria-live="polite">
                  {isPending ? "Request in flight..." : status}
                </p>
              </div>

              <Tabs.Panel className="mt-5" value="all">
                <PlantList
                  isPending={isPending}
                  plants={visiblePlants}
                  runRequest={runRequest}
                  refreshPlants={refreshPlants}
                />
              </Tabs.Panel>
              <Tabs.Panel className="mt-5" value="needs-water">
                <PlantList
                  emptyMessage="No plants need water right now."
                  isPending={isPending}
                  plants={visiblePlants}
                  runRequest={runRequest}
                  refreshPlants={refreshPlants}
                />
              </Tabs.Panel>
            </Tabs.Root>
          </section>

          <aside className="space-y-4">
            <CreatePlantForm
              isPending={isPending}
              refreshPlants={refreshPlants}
              runRequest={runRequest}
            />
            <div className="info-panel">
              <h2>Request map</h2>
              <dl>
                <div>
                  <dt>GET</dt>
                  <dd>
                    <code>listPlants</code> loads and serializes rows for the route loader.
                  </dd>
                </div>
                <div>
                  <dt>POST</dt>
                  <dd>
                    <code>createPlant</code>, <code>waterPlant</code>, and <code>deletePlant</code>{" "}
                    mutate SQLite through Drizzle.
                  </dd>
                </div>
              </dl>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}

function PlantList({
  emptyMessage = "Add a plant to start tracking care.",
  isPending,
  plants,
  refreshPlants,
  runRequest,
}: {
  emptyMessage?: string;
  isPending: boolean;
  plants: Array<Plant>;
  refreshPlants: (message?: string) => Promise<void>;
  runRequest: (request: () => Promise<void>) => void;
}) {
  if (plants.length === 0) {
    return (
      <div className="empty-state">
        <Sprout aria-hidden size={22} />
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="plant-grid">
      {plants.map((plant) => (
        <article className="plant-card" key={plant.id}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="room-label">{plant.room}</p>
              <h2>{plant.name}</h2>
            </div>
            <span className={plant.needsWater ? "badge warning" : "badge"}>{plant.light}</span>
          </div>

          <p className="plant-notes">{plant.notes || "No notes yet."}</p>

          <div className="plant-meta">
            <span>Updated {formatDate(plant.updatedAt)}</span>
            <span>
              {plant.lastWateredAt ? `Watered ${formatDate(plant.lastWateredAt)}` : "Never watered"}
            </span>
          </div>

          <div className="card-actions">
            <label className="switch-row">
              <Switch.Root
                checked={plant.needsWater}
                className="switch"
                disabled={isPending}
                onCheckedChange={(checked) =>
                  runRequest(async () => {
                    if (checked) {
                      await flagPlantForWater({ data: { id: plant.id } });
                      await refreshPlants(`Flagged ${plant.name} for watering.`);
                      return;
                    }

                    await waterPlant({ data: { id: plant.id } });
                    await refreshPlants(`Marked ${plant.name} as watered.`);
                  })
                }
              >
                <Switch.Thumb className="switch-thumb" />
              </Switch.Root>
              <Droplets aria-hidden size={16} />
              <span>{plant.needsWater ? "Needs water" : "Watered"}</span>
            </label>

            <button
              className="icon-button"
              disabled={isPending}
              title={`Delete ${plant.name}`}
              type="button"
              onClick={() =>
                runRequest(async () => {
                  await deletePlant({ data: { id: plant.id } });
                  await refreshPlants(`Deleted ${plant.name}.`);
                })
              }
            >
              <Trash2 aria-hidden size={17} />
              <span className="sr-only">Delete {plant.name}</span>
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function CreatePlantForm({
  isPending,
  refreshPlants,
  runRequest,
}: {
  isPending: boolean;
  refreshPlants: (message?: string) => Promise<void>;
  runRequest: (request: () => Promise<void>) => void;
}) {
  const [needsWater, setNeedsWater] = useState(false);

  return (
    <form
      className="create-panel"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const formData = new FormData(form);
        const name = getFormString(formData, "name");
        const room = getFormString(formData, "room");
        const light = getFormString(formData, "light");
        const notes = getFormString(formData, "notes");

        runRequest(async () => {
          await createPlant({
            data: {
              name,
              room: room as (typeof rooms)[number],
              light: light as (typeof lightLevels)[number],
              notes,
              needsWater,
            },
          });
          form.reset();
          setNeedsWater(false);
          await refreshPlants(`Created ${name}.`);
        });
      }}
    >
      <div>
        <p className="eyebrow">POST example</p>
        <h2>Add a plant</h2>
      </div>

      <Field.Root className="field" name="name">
        <Field.Label className="label">Name</Field.Label>
        <Input className="input" minLength={2} placeholder="String of hearts" required />
      </Field.Root>

      <Field.Root className="field" name="room">
        <Field.Label className="label">Room</Field.Label>
        <select className="input" defaultValue={rooms[0]} name="room" required>
          {rooms.map((room) => (
            <option key={room} value={room}>
              {room}
            </option>
          ))}
        </select>
      </Field.Root>

      <Field.Root className="field" name="light">
        <Field.Label className="label">Light</Field.Label>
        <select className="input" defaultValue={lightLevels[2]} name="light" required>
          {lightLevels.map((light) => (
            <option key={light} value={light}>
              {light}
            </option>
          ))}
        </select>
      </Field.Root>

      <Field.Root className="field" name="notes">
        <Field.Label className="label">Notes</Field.Label>
        <Input className="input" maxLength={240} placeholder="Care detail, location, cadence..." />
      </Field.Root>

      <label className="switch-row rounded-row">
        <Switch.Root
          checked={needsWater}
          className="switch"
          onCheckedChange={(checked) => setNeedsWater(checked)}
        >
          <Switch.Thumb className="switch-thumb" />
        </Switch.Root>
        <span>Needs water now</span>
      </label>

      <button className="button" disabled={isPending} type="submit">
        <Plus aria-hidden size={18} />
        Add plant
      </button>
    </form>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function getFormString(formData: FormData, key: string) {
  const value = formData.get(key);

  return typeof value === "string" ? value : "";
}
