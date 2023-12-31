#  Copyright (c).
#  All rights reserved.
#  This file is part of Nifi Flow Unit Testing Framework,
#  and is released under the "Apache license 2.0 Agreement". Please see the LICENSE file
#  that should have been included as part of this package.

import psycopg2
from psycopg2 import OperationalError, Error


def create_connection(db_name, db_user, db_password, db_host, db_port):
    connection = None
    try:
        connection = psycopg2.connect(
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
        )
        print("Connection to PostgreSQL DB successful")
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    return connection


def execute_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        print("Query executed successfully")
    except Error as e:
        print(f"The error '{e}' occurred")


def execute_select_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        print("Query executed successfully")
    except Error as e:
        print(f"The error '{e}' occurred")
    return cursor

# Testing
# connection = create_connection("postgres", "postgres", "postgres", "127.0.0.1", "5432")
#
# create_users_table = """
# CREATE TABLE IF NOT EXISTS users (
#   id INTEGER PRIMARY KEY,
#   name TEXT NOT NULL,
#   age INTEGER,
#   gender TEXT,
#   nationality TEXT
# );
# """
#
# execute_query(connection, create_users_table)
