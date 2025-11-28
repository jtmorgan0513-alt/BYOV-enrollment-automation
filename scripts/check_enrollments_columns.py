import sqlite3

conn = sqlite3.connect('data/byov.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(enrollments)")
cols = cur.fetchall()
print('enrollments columns:')
for c in cols:
    print(c)
conn.close()