CREATE TABLE `attachments` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`name` text NOT NULL,
	`mime` text NOT NULL,
	`size` integer NOT NULL,
	`created` text NOT NULL,
	`published` integer DEFAULT 0 NOT NULL,
	FOREIGN KEY (`owner`) REFERENCES `members`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `audit` (
	`id` text PRIMARY KEY NOT NULL,
	`target` text NOT NULL,
	`actor` text NOT NULL,
	`action` text NOT NULL,
	`detail` text NOT NULL,
	`created` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `audit_target` ON `audit` (`target`,`created`);--> statement-breakpoint
CREATE TABLE `entities` (
	`id` text PRIMARY KEY NOT NULL,
	`kind` text NOT NULL,
	`name` text NOT NULL,
	`data` text NOT NULL,
	`version` integer NOT NULL,
	`updated` text NOT NULL,
	`submission_id` text
);
--> statement-breakpoint
CREATE TABLE `history` (
	`id` text PRIMARY KEY NOT NULL,
	`entity_id` text NOT NULL,
	`version` integer NOT NULL,
	`data` text NOT NULL,
	`actor` text NOT NULL,
	`action` text NOT NULL,
	`reason` text,
	`created` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `history_entity_version` ON `history` (`entity_id`,`version`);--> statement-breakpoint
CREATE TABLE `members` (
	`id` text PRIMARY KEY NOT NULL,
	`auth_id` text,
	`email` text NOT NULL,
	`name` text NOT NULL,
	`role` text NOT NULL,
	`status` text NOT NULL,
	`created` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `members_auth` ON `members` (`auth_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `members_email` ON `members` (`email`);--> statement-breakpoint
CREATE TABLE `submissions` (
	`id` text PRIMARY KEY NOT NULL,
	`entity_id` text NOT NULL,
	`kind` text NOT NULL,
	`data` text NOT NULL,
	`base_version` integer NOT NULL,
	`revision` integer NOT NULL,
	`status` text NOT NULL,
	`author` text NOT NULL,
	`reviewer` text,
	`reason` text,
	`token` text,
	`request_key` text NOT NULL,
	`created` text NOT NULL,
	`updated` text NOT NULL,
	FOREIGN KEY (`author`) REFERENCES `members`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `submissions_author` ON `submissions` (`author`,`updated`);--> statement-breakpoint
CREATE INDEX `submissions_status` ON `submissions` (`status`,`updated`);--> statement-breakpoint
CREATE UNIQUE INDEX `submissions_request` ON `submissions` (`author`,`request_key`);