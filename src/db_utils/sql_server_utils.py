#  Copyright (c).
#  All rights reserved.
#  This file is part of Nifi Flow Unit Testing Framework,
#  and is released under the "Apache license 2.0 Agreement". Please see the LICENSE file
#  that should have been included as part of this package.

"""
Connects to a SQL database using pyodbc
"""

import pyodbc


def create_connection(db_name, db_user, db_password, db_host):
    conn = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};'
                          'Server=' + db_host + ';'
                          'Database=' + db_name + ';'
                          'UID=' + db_user + ';'
                          'PWD=' + db_password + ';'
                          'TrustServerCertificate=yes;')
    return conn


def execute_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        print("Query executed successfully")
    except Exception as e:
        print(f"The error '{e}' occurred")

def execute_select_query(connection, query):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        print("Query executed successfully")
    except Exception as e:
        print(f"The error '{e}' occurred")
    return cursor

# Testing
# create_users_table = """
# if not exists (select * from sysobjects where name='users' and xtype='U')
# CREATE TABLE users (
#   id INTEGER PRIMARY KEY,
#   name TEXT NOT NULL,
#   age INTEGER,
#   gender TEXT,
#   nationality TEXT
# );
# """
#
# conn = create_connection("master", "SA", "Pass@word", "127.0.0.1")
# execute_query(conn, create_users_table)
