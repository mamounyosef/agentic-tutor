-- ==============================================================================
-- AGENTIC TUTOR - CONSTRUCTOR DATABASE SCHEMA
-- ==============================================================================
-- This schema is for the Constructor Workflow (Course Creators)
-- Separate from the Tutor Workflow - completely isolated
--
-- IMPORTANT: Run this script on your local MySQL server to create the database
--
-- Usage:
--   mysql -u root -p < backend/db/constructor/schema.sql
--
-- Or from MySQL command line:
--   source /path/to/backend/db/constructor/schema.sql;
-- ==============================================================================

-- Create the database
CREATE DATABASE IF NOT EXISTS agentic_tutor_constructor
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE agentic_tutor_constructor;

-- ==============================================================================
-- CREATORS TABLE (Course Creators - separate from students)
-- ==============================================================================

CREATE TABLE creators (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    settings JSON DEFAULT NULL COMMENT '{"language": "en", "notifications": true}',
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Course creators - separate authentication from students';

-- ==============================================================================
-- COURSES TABLE
-- ==============================================================================

CREATE TABLE courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    creator_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    difficulty ENUM('beginner', 'intermediate', 'advanced') DEFAULT 'beginner',
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    course_metadata JSON DEFAULT NULL COMMENT '{"allow_question_generation": true, "session_length": 30}',

    FOREIGN KEY (creator_id) REFERENCES creators(id) ON DELETE CASCADE,
    FULLTEXT idx_search (title, description),
    INDEX idx_creator (creator_id),
    INDEX idx_published (is_published)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Course definitions created by course creators';

-- ==============================================================================
-- MODULES TABLE (Course Modules - e.g., "Week 1", "Foundations")
-- ==============================================================================

CREATE TABLE modules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    order_index INT NOT NULL,
    prerequisites JSON DEFAULT NULL COMMENT 'Array of module IDs that must be completed first',

    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE KEY unique_order (course_id, order_index),
    INDEX idx_course (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Course modules (major divisions like weeks/sections)';

-- ==============================================================================
-- UNITS TABLE (Learning Units within Modules - content containers)
-- ==============================================================================

CREATE TABLE units (
    id INT AUTO_INCREMENT PRIMARY KEY,
    module_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    order_index INT NOT NULL,
    prerequisites JSON DEFAULT NULL COMMENT 'Array of unit IDs that must be completed first',

    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE,
    UNIQUE KEY unique_order (module_id, order_index),
    INDEX idx_module (module_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Learning units within modules - contain actual content';

-- ==============================================================================
-- TOPICS TABLE (Learning Topics within Units)
-- ==============================================================================

CREATE TABLE topics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    unit_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    content_summary TEXT COMMENT 'Brief summary for RAG retrieval',
    order_index INT NOT NULL,

    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
    UNIQUE KEY unique_order (unit_id, order_index),
    INDEX idx_unit (unit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Learning topics within units';

-- ==============================================================================
-- MATERIALS TABLE (Course Content Files)
-- ==============================================================================

CREATE TABLE materials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    unit_id INT NOT NULL,
    course_id INT NOT NULL,
    material_type ENUM('pdf', 'ppt', 'pptx', 'video', 'text', 'docx', 'other') NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    original_filename VARCHAR(255),
    course_metadata JSON DEFAULT NULL COMMENT '{"page_count": 0, "duration_seconds": 0, "size_bytes": 0}',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_status ENUM('pending', 'processing', 'completed', 'error') DEFAULT 'pending',
    chunks_count INT DEFAULT 0,

    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    INDEX idx_unit (unit_id),
    INDEX idx_course (course_id),
    INDEX idx_type (material_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Course materials (PDFs, slides, videos, etc.)';

-- ==============================================================================
-- QUIZZES TABLE (Quiz Containers - groups of questions)
-- ==============================================================================

CREATE TABLE quizzes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    unit_id INT NOT NULL,
    course_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT COMMENT 'What this quiz covers (e.g., "Units 1-2: Python Basics")',
    order_index INT NOT NULL COMMENT 'Order within the unit (1, 2, 3...)',
    time_limit_seconds INT DEFAULT NULL COMMENT 'NULL = no time limit',
    passing_score DECIMAL(5,2) DEFAULT 70.00 COMMENT 'Percentage needed to pass (0-100)',
    max_attempts INT DEFAULT 3 COMMENT 'Maximum number of attempts allowed',
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE KEY unique_order (unit_id, order_index),
    INDEX idx_unit (unit_id),
    INDEX idx_course (course_id),
    INDEX idx_published (is_published)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Quiz definitions - containers for quiz questions';

-- ==============================================================================
-- QUIZ QUESTIONS TABLE
-- ==============================================================================

CREATE TABLE quiz_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id INT NOT NULL COMMENT 'Links to the quiz this question belongs to',
    unit_id INT NOT NULL COMMENT 'Denormalized for easier queries',
    course_id INT NOT NULL COMMENT 'Denormalized for easier queries',
    question_text TEXT NOT NULL,
    question_type ENUM('multiple_choice', 'true_false', 'short_answer', 'essay') NOT NULL,
    options JSON DEFAULT NULL COMMENT 'For multiple choice: [{"text": "Option A", "is_correct": false}]',
    correct_answer TEXT,
    rubric TEXT COMMENT 'Grading criteria for open-ended questions',
    difficulty ENUM('easy', 'medium', 'hard') DEFAULT 'medium',
    points_value DECIMAL(5,2) DEFAULT 1.00 COMMENT 'Points this question is worth',
    order_index INT DEFAULT 0 COMMENT 'Order within the quiz',
    course_metadata JSON DEFAULT NULL COMMENT '{"tags": [], "concepts_tested": []}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    INDEX idx_quiz (quiz_id),
    INDEX idx_unit (unit_id),
    INDEX idx_course (course_id),
    INDEX idx_difficulty (difficulty)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual quiz questions linked to quizzes';

-- ==============================================================================
-- CONSTRUCTOR SESSIONS TABLE (Builder Sessions)
-- ==============================================================================

CREATE TABLE constructor_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    creator_id INT NOT NULL,
    course_id INT NULL COMMENT 'NULL until course is created',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    status ENUM('in_progress', 'completed', 'abandoned') DEFAULT 'in_progress',
    messages_json JSON DEFAULT NULL COMMENT 'Full conversation history',
    phase VARCHAR(50) DEFAULT 'welcome',
    files_uploaded INT DEFAULT 0,
    files_processed INT DEFAULT 0,
    topics_created INT DEFAULT 0,
    questions_created INT DEFAULT 0,

    FOREIGN KEY (creator_id) REFERENCES creators(id) ON DELETE CASCADE,
    INDEX idx_creator (creator_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Course construction sessions';

-- ==============================================================================
-- SAMPLE DATA (For Testing)
-- ==============================================================================

INSERT INTO creators (email, password_hash, full_name) VALUES
('creator@example.com', '$2b$12$placeholder_hash_replace_with_real_hash', 'Demo Creator');

-- ==============================================================================
-- VALIDATION QUERIES (To verify schema creation)
-- ==============================================================================

-- Check if all tables were created
SELECT
    'creators' as table_name, COUNT(*) as row_count FROM creators
UNION ALL
SELECT
    'courses', COUNT(*) FROM courses
UNION ALL
SELECT
    'modules', COUNT(*) FROM modules
UNION ALL
SELECT
    'units', COUNT(*) FROM units
UNION ALL
SELECT
    'topics', COUNT(*) FROM topics
UNION ALL
SELECT
    'materials', COUNT(*) FROM materials
UNION ALL
SELECT
    'quizzes', COUNT(*) FROM quizzes
UNION ALL
SELECT
    'quiz_questions', COUNT(*) FROM quiz_questions
UNION ALL
SELECT
    'constructor_sessions', COUNT(*) FROM constructor_sessions;
