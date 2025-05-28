import sqlite3
import datetime

DB_PATH = "memory.db" # Assuming the script is run from the repo root

def view_memories():
    print(f"Attempting to read memories from: {DB_PATH}\n")
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()

        # Fetch all memories, newest first
        cur.execute("SELECT thread_ts, timestamp, summary FROM memories ORDER BY timestamp DESC")
        rows = cur.fetchall()

        if not rows:
            print("No memories found.")
            return

        print("======================================================================")
        print(f"{'Timestamp (UTC)':<25} {'Thread TS':<25} {'Summary'}")
        print("======================================================================")

        for row in rows:
            thread_ts, timestamp_val, summary = row
            
            # Convert Unix timestamp to human-readable UTC datetime string
            try:
                # Ensure timestamp_val is float or int for fromtimestamp
                dt_object = datetime.datetime.fromtimestamp(float(timestamp_val), tz=datetime.timezone.utc)
                formatted_timestamp = dt_object.strftime('%Y-%m-%d %H:%M:%S %Z')
            except (TypeError, ValueError) as e:
                formatted_timestamp = f"Invalid timestamp ({timestamp_val}): {e}"

            # For display, limit summary length and replace newlines
            display_summary = summary.replace('\n', ' ').replace('\r', '')
            if len(display_summary) > 100:
                display_summary = display_summary[:97] + "..."
            
            print(f"{formatted_timestamp:<25} {thread_ts:<25} {display_summary}")
        
        print("======================================================================")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        print("Please ensure 'memory.db' exists and is a valid SQLite database.")
        print("You might need to run the main application first to create and populate it.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'con' in locals() and con:
            con.close()

if __name__ == "__main__":
    view_memories()
