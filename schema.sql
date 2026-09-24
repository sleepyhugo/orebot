BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "player_upgrades" (
	"user_id"	INTEGER NOT NULL,
	"upgrade_id"	TEXT NOT NULL,
	"level"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("user_id","upgrade_id"),
	FOREIGN KEY("user_id") REFERENCES "players"("user_id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "players" (
	"user_id"	INTEGER NOT NULL,
	"ore"	REAL NOT NULL DEFAULT 0,
	"lifetime_ore"	REAL NOT NULL DEFAULT 0,
	"last_collected"	REAL NOT NULL,
	"created_at"	REAL NOT NULL,
	PRIMARY KEY("user_id")
);
COMMIT;