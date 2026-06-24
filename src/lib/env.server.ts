import { z } from "zod";

const envSchema = z.object({
  DATABASE_URL: z.string().default("file:./local.db"),
  BETTER_AUTH_SECRET: z.string().min(32),
  BETTER_AUTH_URL: z.url().default("http://localhost:3000"),
});

export const env = envSchema.parse(process.env);
