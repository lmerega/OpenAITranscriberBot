CREATE TABLE IF NOT EXISTS users (
  chat_id BIGINT NOT NULL,
  language VARCHAR(5) NOT NULL DEFAULT 'en',
  total_minutes DECIMAL(15,4) DEFAULT '0.0000',
  monthly_month CHAR(7) DEFAULT NULL,
  username VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (chat_id),
  UNIQUE KEY uq_users_chat_id (chat_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS monthly_usage (
  chat_id BIGINT NOT NULL,
  year_month CHAR(7) NOT NULL,
  minutes DECIMAL(15,4) NOT NULL DEFAULT '0.0000',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (chat_id, year_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS interactions (
  ID INT NOT NULL AUTO_INCREMENT,
  ChatID BIGINT NOT NULL,
  username_snapshot VARCHAR(255) DEFAULT NULL,
  content_type VARCHAR(32) DEFAULT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'success',
  Date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  duration_seconds DECIMAL(10,2) DEFAULT NULL,
  PRIMARY KEY (ID),
  KEY idx_interactions_chatid_date (ChatID, Date),
  KEY idx_interactions_date (Date),
  KEY idx_interactions_status_date (status, Date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
