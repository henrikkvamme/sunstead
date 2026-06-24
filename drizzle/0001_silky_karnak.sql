CREATE TABLE `plants` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`room` text NOT NULL,
	`light` text NOT NULL,
	`notes` text DEFAULT '' NOT NULL,
	`needs_water` integer DEFAULT false NOT NULL,
	`last_watered_at` integer,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `plants_room_idx` ON `plants` (`room`);