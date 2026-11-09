import sys
sys.path.append('.')
import db

conn = db.getConnection()
cursor = conn.cursor()

# Get tables matching 'checkout'
cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE '%checkout%';")
tables = cursor.fetchall()
print("Checkout tables:", tables)

for (table,) in tables:
    cursor.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}';")
    columns = cursor.fetchall()
    print(f"\nColumns for {table}:")
    for col in columns:
        print(col)

# Let's also check 'account_user'
cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'account_user';")
columns = cursor.fetchall()
print(f"\nColumns for account_user:")
for col in columns:
    print(col)

conn.close()
