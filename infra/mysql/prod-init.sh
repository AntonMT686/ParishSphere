#!/bin/bash
# First start of the production MySQL container (empty data directory only): the master database and
# the account ParishSphere uses to create parish databases and their per-parish users.
set -euo pipefail
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "
CREATE DATABASE IF NOT EXISTS ps_master CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'ps_admin'@'%' IDENTIFIED BY '${PS_DB_ADMIN_PASSWORD}';
GRANT ALL PRIVILEGES ON *.* TO 'ps_admin'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;"
