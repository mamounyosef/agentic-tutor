-- ==============================================================================
-- AGENTIC TUTOR - TUTOR DATABASE SCHEMA
-- ==============================================================================
-- This schema is for the Tutor Workflow (Students)
-- Separate from the Constructor Workflow - completely isolated
--
-- IMPORTANT: Run this script on your local MySQL server to create the database
--
-- Usage:
--   mysql -u root -p < backend/db/tutor/schema.sql
--
-- Or from MySQL command line:
--   source /path/to/backend/db/tutor/schema.sql;
-- ==============================================================================

-- Create the database
CREATE DATABASE IF NOT EXISTS agentic_tutor_tutor
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE agentic_tutor_tutor;

-- ==============================================================================
-- STUDENTS TABLE (Separate from creators)
-- ==============================================================================

CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    age INT,
    gender ENUM('male', 'female', 'other', 'prefer_not_to_say'),
    education_level ENUM('high_school', 'undergraduate', 'graduate', 'postgraduate', 'other'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    settings JSON DEFAULT NULL COMMENT '{"language": "en", "theme": "dark"}',
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Student accounts - separate authentication from creators';

-- ==============================================================================
-- ENROLLMENTS TABLE (Students in Courses)
-- ==============================================================================

CREATE TABLE enrollments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    course_id INT NOT NULL COMMENT 'References constructor DB courses',
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('active', 'completed', 'dropped') DEFAULT 'active',
    completion_percentage DECIMAL(5,2) DEFAULT 0.00,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_student_courses (student_id, status),
    INDEX idx_course (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Student enrollments in courses';

-- ==============================================================================
-- MASTERY TABLE (Per-Topic Mastery Scores)
-- ==============================================================================

CREATE TABLE mastery (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    topic_id INT NOT NULL COMMENT 'References constructor DB topics',
    score DECIMAL(4,3) DEFAULT 0.000 COMMENT 'Mastery score from 0.000 to 1.000',
    attempts_count INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    streak_count INT DEFAULT 0 COMMENT 'Consecutive correct answers',

    UNIQUE KEY unique_mastery (student_id, topic_id),
    INDEX idx_student_mastery (student_id, score),
    INDEX idx_topic (topic_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Per-topic mastery tracking for students';

-- ==============================================================================
-- QUIZ ATTEMPTS TABLE (Answer History)
-- ==============================================================================

CREATE TABLE quiz_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    question_id INT NOT NULL COMMENT 'References constructor DB quiz_questions',
    user_answer TEXT,
    is_correct BOOLEAN,
    feedback_json JSON DEFAULT NULL COMMENT 'AI-generated feedback',
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    time_spent_seconds INT DEFAULT NULL,

    INDEX idx_student_attempts (student_id, attempted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Quiz attempt history';

-- ==============================================================================
-- TUTOR SESSIONS TABLE (Learning Sessions)
-- ==============================================================================

CREATE TABLE tutor_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP NULL,
    topics_covered JSON DEFAULT NULL COMMENT 'Array of topic IDs discussed',
    initial_mastery JSON DEFAULT NULL COMMENT 'Snapshot at session start',
    final_mastery JSON DEFAULT NULL COMMENT 'Snapshot at session end',
    session_goal VARCHAR(255),

    INDEX idx_student_sessions (student_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tutoring session records';

-- ==============================================================================
-- TUTOR INTERACTIONS TABLE (Individual Messages/Actions)
-- ==============================================================================

CREATE TABLE tutor_interactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    interaction_type ENUM('question', 'explanation', 'hint', 'quiz', 'feedback', 'review', 'gap_analysis') NOT NULL,
    content JSON NOT NULL COMMENT 'Message content, question details, etc.',
    ai_action VARCHAR(100) COMMENT 'What the AI agent did',
    mastery_snapshot JSON DEFAULT NULL COMMENT 'Mastery state after this interaction',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES tutor_sessions(id) ON DELETE CASCADE,
    INDEX idx_session_interactions (session_id, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual interactions within tutoring sessions';

-- ==============================================================================
-- STUDENT PROFILES TABLE (Learning Patterns)
-- ==============================================================================

CREATE TABLE student_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL UNIQUE,
    learning_style VARCHAR(50) COMMENT 'visual, auditory, reading, kinesthetic',
    preferred_difficulty VARCHAR(20) COMMENT 'easy, medium, hard, adaptive',
    session_length_preference INT DEFAULT 30 COMMENT 'Preferred session length in minutes',
    total_sessions INT DEFAULT 0,
    total_study_time INT DEFAULT 0 COMMENT 'Total study time in seconds',
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Student learning preferences and patterns';

-- ==============================================================================
-- SAMPLE DATA (For Testing)
-- ==============================================================================

INSERT INTO students (email, password_hash, full_name, age, gender, education_level) VALUES
('student@example.com', '$2b$12$placeholder_hash_replace_with_real_hash', 'Demo Student', 20, 'female', 'undergraduate');

-- ==============================================================================
-- VALIDATION QUERIES (To verify schema creation)
-- ==============================================================================

-- Check if all tables were created
SELECT
    'students' as table_name, COUNT(*) as row_count FROM students
UNION ALL
SELECT
    'enrollments', COUNT(*) FROM enrollments
UNION ALL
SELECT
    'mastery', COUNT(*) FROM mastery
UNION ALL
SELECT
    'quiz_attempts', COUNT(*) FROM quiz_attempts
UNION ALL
SELECT
    'tutor_sessions', COUNT(*) FROM tutor_sessions
UNION ALL
SELECT
    'tutor_interactions', COUNT(*) FROM tutor_interactions
UNION ALL
SELECT
    'student_profiles', COUNT(*) FROM student_profiles;
