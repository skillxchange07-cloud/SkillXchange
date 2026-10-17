-- ============================================================================
-- SkillXchange — Supabase PostgreSQL Schema Initialization
-- Generated directly from SQLAlchemy models in app/models.py
-- Dialect: PostgreSQL | Engine: SQLAlchemy ORM
-- Mode: Review-Only DDL (Schema Definition Only, Zero Data Inserts)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Table #1: users
-- ----------------------------------------------------------------------------
CREATE TABLE users (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	email VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	phone VARCHAR(20), 
	availability VARCHAR(255), 
	preferred_mode VARCHAR(50), 
	zoom_link VARCHAR(255), 
	meet_link VARCHAR(255), 
	role VARCHAR(20), 
	is_active BOOLEAN NOT NULL DEFAULT TRUE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

-- ----------------------------------------------------------------------------
-- Table #2: badges
-- ----------------------------------------------------------------------------
CREATE TABLE badges (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	badge_name VARCHAR(50) NOT NULL, 
	earned_date TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- Table #3: messages
-- ----------------------------------------------------------------------------
CREATE TABLE messages (
	id SERIAL NOT NULL, 
	sender_id INTEGER NOT NULL, 
	recipient_id INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	timestamp TIMESTAMP WITHOUT TIME ZONE, 
	is_read BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id), 
	FOREIGN KEY(recipient_id) REFERENCES users (id)
);

-- ----------------------------------------------------------------------------
-- Table #4: notifications
-- ----------------------------------------------------------------------------
CREATE TABLE notifications (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	message VARCHAR(255) NOT NULL, 
	read_status BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);
CREATE INDEX ix_notifications_read_status ON notifications (read_status);

-- ----------------------------------------------------------------------------
-- Table #5: skills
-- ----------------------------------------------------------------------------
CREATE TABLE skills (
	id SERIAL NOT NULL, 
	mentor_id INTEGER NOT NULL, 
	skill_name VARCHAR(100) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	description TEXT, 
	demo_video_path VARCHAR(255), 
	verification_status VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(mentor_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_skills_skill_name ON skills (skill_name);
CREATE INDEX ix_skills_category ON skills (category);
CREATE INDEX ix_skills_verification_status ON skills (verification_status);

-- ----------------------------------------------------------------------------
-- Table #6: wanted_skills
-- ----------------------------------------------------------------------------
CREATE TABLE wanted_skills (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	skill_name VARCHAR(100) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- Table #7: bookmarks
-- ----------------------------------------------------------------------------
CREATE TABLE bookmarks (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	skill_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(skill_id) REFERENCES skills (id)
);

-- ----------------------------------------------------------------------------
-- Table #8: contact_requests
-- ----------------------------------------------------------------------------
CREATE TABLE contact_requests (
	id SERIAL NOT NULL, 
	sender_id INTEGER NOT NULL, 
	mentor_id INTEGER NOT NULL, 
	skill_id INTEGER NOT NULL, 
	exchange_skill_id INTEGER, 
	status VARCHAR(30), 
	request_date TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id), 
	FOREIGN KEY(mentor_id) REFERENCES users (id), 
	FOREIGN KEY(skill_id) REFERENCES skills (id), 
	FOREIGN KEY(exchange_skill_id) REFERENCES skills (id)
);

CREATE INDEX ix_contact_requests_status ON contact_requests (status);

-- ----------------------------------------------------------------------------
-- Table #9: ratings
-- ----------------------------------------------------------------------------
CREATE TABLE ratings (
	id SERIAL NOT NULL, 
	skill_id INTEGER NOT NULL, 
	mentor_id INTEGER NOT NULL, 
	rater_id INTEGER NOT NULL, 
	rating_value INTEGER NOT NULL, 
	review TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(skill_id) REFERENCES skills (id), 
	FOREIGN KEY(mentor_id) REFERENCES users (id), 
	FOREIGN KEY(rater_id) REFERENCES users (id)
);

-- ----------------------------------------------------------------------------
-- Table #10: sessions
-- ----------------------------------------------------------------------------
CREATE TABLE sessions (
	id SERIAL NOT NULL, 
	mentor_id INTEGER NOT NULL, 
	learner_id INTEGER NOT NULL, 
	skill_id INTEGER NOT NULL, 
	meeting_link VARCHAR(255) NOT NULL, 
	meeting_type VARCHAR(50), 
	session_date TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	status VARCHAR(20), 
	PRIMARY KEY (id), 
	FOREIGN KEY(mentor_id) REFERENCES users (id), 
	FOREIGN KEY(learner_id) REFERENCES users (id), 
	FOREIGN KEY(skill_id) REFERENCES skills (id)
);

