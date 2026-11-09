-- Development bootstrap: master DB + an admin account allowed to create parish databases.
CREATE DATABASE IF NOT EXISTS ps_master CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'ps_admin'@'%' IDENTIFIED BY 'ps_admin';
GRANT ALL PRIVILEGES ON *.* TO 'ps_admin'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
