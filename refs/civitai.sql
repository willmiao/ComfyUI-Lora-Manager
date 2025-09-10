CREATE TABLE models (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            type       TEXT NOT NULL,
            username   TEXT,
            data       TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        ) STRICT;
CREATE TABLE model_versions (
            id           INTEGER PRIMARY KEY,
            model_id     INTEGER NOT NULL,
            position     INTEGER NOT NULL,
            name         TEXT NOT NULL,
            base_model   TEXT NOT NULL,
            published_at INTEGER,
            data         TEXT NOT NULL,
            created_at   INTEGER NOT NULL,
            updated_at   INTEGER NOT NULL
        ) STRICT;
CREATE INDEX model_versions_model_id_idx ON model_versions (model_id);
CREATE TABLE model_files (
            id               INTEGER PRIMARY KEY,
            model_id         INTEGER NOT NULL,
            version_id       INTEGER NOT NULL,
            type             TEXT NOT NULL,
            sha256           TEXT,
            data             TEXT NOT NULL,
            created_at       INTEGER NOT NULL,
            updated_at       INTEGER NOT NULL
        ) STRICT;
CREATE INDEX model_files_model_id_idx ON model_files (model_id);
CREATE INDEX model_files_version_id_idx ON model_files (version_id);
CREATE TABLE archived_model_files (
            file_id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            version_id INTEGER NOT NULL
        ) STRICT;