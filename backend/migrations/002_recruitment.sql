-- 联合招募：方案目标人数、报告样本口径、招募批次与名额。
-- 启动仍以 metadata.create_all 为准；本文件供既有库人工迁移。
ALTER TABLE plans ADD COLUMN target_control INTEGER NOT NULL DEFAULT 0;
ALTER TABLE plans ADD COLUMN target_intervention INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reports ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'campus';
CREATE TABLE IF NOT EXISTS recruit_batches (id SERIAL PRIMARY KEY,kind VARCHAR(20) NOT NULL,status VARCHAR(20) NOT NULL,idempotency_key VARCHAR(80) UNIQUE NOT NULL,summary JSON NOT NULL,created_at VARCHAR(40) NOT NULL,locked_at VARCHAR(40) NOT NULL);
CREATE TABLE IF NOT EXISTS assignments (id SERIAL PRIMARY KEY,batch_id INTEGER NOT NULL REFERENCES recruit_batches(id),plan_id INTEGER NOT NULL REFERENCES plans(id),student_id INTEGER NOT NULL REFERENCES students(id),"group" VARCHAR(20) NOT NULL,status VARCHAR(20) NOT NULL,created_at VARCHAR(40) NOT NULL,updated_at VARCHAR(40) NOT NULL);
-- 每人同期只占一个名额：仅待分配/已锁定占用
CREATE UNIQUE INDEX IF NOT EXISTS uq_assignment_active_student ON assignments(student_id) WHERE status IN ('pending','locked');
