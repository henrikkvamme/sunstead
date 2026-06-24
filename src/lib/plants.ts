import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

import { lightLevels, rooms } from "#/lib/plants.shared";

const plantInputSchema = z.object({
  name: z.string().trim().min(2).max(80),
  room: z.enum(rooms),
  light: z.enum(lightLevels),
  notes: z.string().trim().max(240).optional().default(""),
  needsWater: z.boolean().default(false),
});

const plantIdSchema = z.object({
  id: z.string().min(1),
});

type PlantRow = {
  id: string;
  name: string;
  room: string;
  light: string;
  notes: string;
  needsWater: boolean;
  lastWateredAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
};

function serializePlant(plant: PlantRow) {
  return {
    id: plant.id,
    name: plant.name,
    room: plant.room,
    light: plant.light,
    notes: plant.notes,
    needsWater: plant.needsWater,
    lastWateredAt: plant.lastWateredAt?.toISOString() ?? null,
    createdAt: plant.createdAt.toISOString(),
    updatedAt: plant.updatedAt.toISOString(),
  };
}

async function getDatabaseModules() {
  const [{ count, desc, eq }, { db }, { plants }, { randomUUID }] = await Promise.all([
    import("drizzle-orm"),
    import("#/db/client.server"),
    import("#/db/schema"),
    import("node:crypto"),
  ]);

  return { count, db, desc, eq, plants, randomUUID };
}

async function ensureDemoPlants() {
  const { count, db, plants, randomUUID } = await getDatabaseModules();
  const [{ value }] = await db.select({ value: count() }).from(plants);

  if (value > 0) {
    return;
  }

  const now = new Date();

  await db.insert(plants).values([
    {
      id: randomUUID(),
      name: "Meyer lemon",
      room: "Patio",
      light: "Direct",
      notes: "Rotate weekly and watch for dry soil after hot afternoons.",
      needsWater: true,
      createdAt: now,
      updatedAt: now,
    },
    {
      id: randomUUID(),
      name: "Bird of paradise",
      room: "Living room",
      light: "Bright indirect",
      notes: "Wipe leaves when dusty so it can keep soaking up light.",
      needsWater: false,
      lastWateredAt: now,
      createdAt: now,
      updatedAt: now,
    },
  ]);
}

export const listPlants = createServerFn({ method: "GET" }).handler(async () => {
  await ensureDemoPlants();

  const { db, desc, plants } = await getDatabaseModules();
  const rows = await db.select().from(plants).orderBy(desc(plants.updatedAt));

  return rows.map(serializePlant);
});

export const createPlant = createServerFn({ method: "POST" })
  .validator(plantInputSchema)
  .handler(async ({ data }) => {
    const { db, plants, randomUUID } = await getDatabaseModules();
    const now = new Date();
    const [plant] = await db
      .insert(plants)
      .values({
        id: randomUUID(),
        name: data.name,
        room: data.room,
        light: data.light,
        notes: data.notes,
        needsWater: data.needsWater,
        createdAt: now,
        updatedAt: now,
      })
      .returning();

    return serializePlant(plant);
  });

export const waterPlant = createServerFn({ method: "POST" })
  .validator(plantIdSchema)
  .handler(async ({ data }) => {
    const { db, eq, plants } = await getDatabaseModules();
    const now = new Date();
    const [plant] = await db
      .update(plants)
      .set({
        needsWater: false,
        lastWateredAt: now,
        updatedAt: now,
      })
      .where(eq(plants.id, data.id))
      .returning();

    if (!plant) {
      throw new Error("Plant not found");
    }

    return serializePlant(plant);
  });

export const flagPlantForWater = createServerFn({ method: "POST" })
  .validator(plantIdSchema)
  .handler(async ({ data }) => {
    const { db, eq, plants } = await getDatabaseModules();
    const [plant] = await db
      .update(plants)
      .set({
        needsWater: true,
        updatedAt: new Date(),
      })
      .where(eq(plants.id, data.id))
      .returning();

    if (!plant) {
      throw new Error("Plant not found");
    }

    return serializePlant(plant);
  });

export const deletePlant = createServerFn({ method: "POST" })
  .validator(plantIdSchema)
  .handler(async ({ data }) => {
    const { db, eq, plants } = await getDatabaseModules();

    await db.delete(plants).where(eq(plants.id, data.id));

    return { id: data.id };
  });
