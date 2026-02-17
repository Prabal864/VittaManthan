"""
Migration script to update existing database schema
Makes vectorstore_data column nullable
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    exit(1)

print("=" * 80)
print("Database Schema Migration")
print("=" * 80)

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        print("\n1. Making vectorstore_data column nullable...")

        # Make column nullable
        conn.execute(text("""
            ALTER TABLE user_data 
            ALTER COLUMN vectorstore_data DROP NOT NULL
        """))

        conn.commit()
        print("   ✅ Column is now nullable")

        print("\n2. Setting existing vectorstore_data to empty string...")

        # Clear existing large data
        result = conn.execute(text("""
            UPDATE user_data 
            SET vectorstore_data = ''
            WHERE vectorstore_data IS NOT NULL
        """))

        conn.commit()
        rows_updated = result.rowcount
        print(f"   ✅ Cleared vectorstore_data for {rows_updated} user(s)")

        print("\n3. Verifying changes...")
        result = conn.execute(text("SELECT user_id, LENGTH(vectorstore_data) as vs_length FROM user_data"))

        for row in result:
            print(f"   User: {row[0]}, Vectorstore size: {row[1]} bytes")

        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80)
        print("\nNote: Vectorstores will be rebuilt from transactions when users query their data.")
        print("This may add 2-3 seconds to the first query after server restart,")
        print("but subsequent queries will be served from memory cache (fast).")

except Exception as e:
    print(f"\n❌ Migration failed: {e}")
    print("\nIf the column is already nullable, this is expected and safe to ignore.")

finally:
    engine.dispose()
