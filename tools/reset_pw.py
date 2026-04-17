import bcrypt, psycopg2

pw = b"test1234"
h = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
print("Hash:", h)

conn = psycopg2.connect(host="127.0.0.1", user="taris_user", password="taris_pg_s1nt4r1s", dbname="taris_db")
cur = conn.cursor()
cur.execute("UPDATE web_accounts SET pw_hash=%s WHERE username='stas' RETURNING username", (h,))
rows = cur.fetchall()
conn.commit()
print("Updated:", rows)
conn.close()
print("OK - password is now: test1234")
