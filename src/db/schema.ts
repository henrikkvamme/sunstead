import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const users = sqliteTable("users", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  createdAt: integer("created_at", { mode: "timestamp" })
    .$defaultFn(() => new Date())
    .notNull(),
});

export const plants = sqliteTable(
  "plants",
  {
    id: text("id").primaryKey(),
    name: text("name").notNull(),
    room: text("room").notNull(),
    light: text("light").notNull(),
    notes: text("notes").notNull().default(""),
    needsWater: integer("needs_water", { mode: "boolean" }).notNull().default(false),
    lastWateredAt: integer("last_watered_at", { mode: "timestamp" }),
    createdAt: integer("created_at", { mode: "timestamp" })
      .$defaultFn(() => new Date())
      .notNull(),
    updatedAt: integer("updated_at", { mode: "timestamp" })
      .$defaultFn(() => new Date())
      .notNull(),
  },
  (table) => [index("plants_room_idx").on(table.room)],
);
