import unittest
from unittest.mock import patch, mock_open
import os
import sqlite3
import time 
import sys

# Add the parent directory to sys.path to allow direct import of main
# This ensures that 'import main' works correctly when running tests,
# especially if tests are run from a different directory or with a test runner.
if os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main

class TestMemoryFeature(unittest.TestCase):

    def setUp(self):
        # Ensure a clean state before each test
        # Store the original state of MEMORY_FEATURE_ENABLED
        self.original_memory_feature_enabled = main.MEMORY_FEATURE_ENABLED
        # Default to False for most tests, can be overridden in specific tests
        main.MEMORY_FEATURE_ENABLED = False 

        if os.path.exists(main.DB_PATH):
            os.remove(main.DB_PATH)
        
        # Reset global states that might be modified by main.py functions
        main._messages.clear() 
        
        # Initialize DB for tests that require it, but allow specific tests to re-init if needed
        main.init_db()

    def tearDown(self):
        # Clean up the database file after each test
        if os.path.exists(main.DB_PATH):
            os.remove(main.DB_PATH)
        
        # Restore the original MEMORY_FEATURE_ENABLED state
        main.MEMORY_FEATURE_ENABLED = self.original_memory_feature_enabled
        main._messages.clear()

    def test_01_init_db(self):
        # setUp already calls init_db, but we can call it again to be explicit
        # or test its idempotency if relevant. For now, just check results.
        self.assertTrue(os.path.exists(main.DB_PATH), "Database file should be created by init_db.")
        conn = None
        try:
            conn = sqlite3.connect(main.DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories';")
            self.assertIsNotNone(cursor.fetchone(), "The 'memories' table should exist after init_db.")

            # Verify that thread_ts is the primary key
            cursor.execute("PRAGMA table_info('memories')")
            columns_info = cursor.fetchall()
            # Expected schema: (cid, name, type, notnull, dflt_value, pk)
            found_thread_ts_pk = False
            expected_pk_columns = {'thread_ts': 1} # Column name -> pk status (1=is PK, 0=not PK)
            
            for col in columns_info:
                col_name = col[1]
                is_pk = col[5]
                if col_name == 'thread_ts':
                    self.assertEqual(is_pk, 1, "thread_ts should be the primary key.")
                    found_thread_ts_pk = True
                else:
                    self.assertEqual(is_pk, 0, f"{col_name} should not be part of the primary key.")
            self.assertTrue(found_thread_ts_pk, "thread_ts primary key info not found.")

        finally:
            if conn:
                conn.close()

    def test_02_add_and_get_memories(self):
        # init_db is called in setUp
        thread_A = "thread_A"
        thread_B = "thread_B"
        summary3_A = "Summary 3 from thread A." # Added earliest
        summary1_A = "Summary 1 from thread A." # Added middle
        summary2_B = "Summary 2 from thread B." # Added newest
        
        # Mock time.time() to control timestamps for predictable order
        # summary3_A (ts=100.0, oldest), summary1_A (ts=200.0, middle), summary2_B (ts=300.0, newest)
        with patch('time.time', side_effect=[100.0, 200.0, 300.0]): 
            main.add_memory(thread_A, summary3_A) # ts=100.0
            main.add_memory(thread_A, summary1_A) # ts=200.0
            main.add_memory(thread_B, summary2_B) # ts=300.0

        # Test retrieving all 3 (global)
        # get_recent_memories now retrieves globally and takes only 'limit'
        memories = main.get_recent_memories(limit=5) 
        self.assertEqual(len(memories), 3, "Should retrieve 3 global memories.")
        # get_recent_memories sorts by timestamp DESC then reverses, so oldest of the retrieved batch first
        self.assertEqual(memories[0], summary3_A) 
        self.assertEqual(memories[1], summary1_A)
        self.assertEqual(memories[2], summary2_B)

        # Test limit (should get the newest 2 globally)
        memories_limited = main.get_recent_memories(limit=2)
        self.assertEqual(len(memories_limited), 2, "Should retrieve 2 global memories with limit=2.")
        # The two newest are summary1_A (ts=200) and summary2_B (ts=300).
        # After reversing, summary1_A comes first.
        self.assertEqual(memories_limited[0], summary1_A) 
        self.assertEqual(memories_limited[1], summary2_B)

        # Test retrieval from an empty database (after setup, but before any adds in this test)
        # To do this properly, we'd need a separate test or ensure the DB is cleared.
        # For now, this part of the test is less about "non-existent thread" and more about "empty global state"
        # Let's create a new, clean DB for this specific check.
        if os.path.exists(main.DB_PATH):
            os.remove(main.DB_PATH)
        main.init_db() # Initialize a fresh DB
        no_memories = main.get_recent_memories()
        self.assertEqual(len(no_memories), 0, "Should retrieve 0 memories from an empty database.")
        # Re-initialize DB for other tests if necessary, though tearDown/setUp should handle it.
        # main.init_db() # Already done by setUp for next test.

        # Test overwrite behavior for a single thread_ts
        # setUp ensures a clean DB for each test method.
        overwrite_thread_ts = "overwrite_test_thread"
        summary_initial = "Initial summary for overwrite test."
        summary_updated = "Updated summary, should overwrite initial."

        with patch('time.time', return_value=100.0):
            main.add_memory(overwrite_thread_ts, summary_initial)
        
        conn = sqlite3.connect(main.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT summary, timestamp FROM memories WHERE thread_ts = ?", (overwrite_thread_ts,))
        row = cursor.fetchone()
        self.assertIsNotNone(row, "Memory should have been added.")
        self.assertEqual(row[0], summary_initial)
        self.assertEqual(row[1], 100.0)
        conn.close()

        with patch('time.time', return_value=200.0):
            main.add_memory(overwrite_thread_ts, summary_updated)

        conn = sqlite3.connect(main.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT summary, timestamp FROM memories WHERE thread_ts = ?", (overwrite_thread_ts,))
        row_updated = cursor.fetchone()
        self.assertIsNotNone(row_updated, "Memory should exist after update.")
        self.assertEqual(row_updated[0], summary_updated, "Summary should be updated.")
        self.assertEqual(row_updated[1], 200.0, "Timestamp should be updated.")
        
        cursor.execute("SELECT COUNT(*) FROM memories WHERE thread_ts = ?", (overwrite_thread_ts,))
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1, "Should only be one memory entry per thread_ts due to UPSERT.")
        conn.close()

        # Adjusting the existing global retrieval test to ensure it fetches unique threads
        # by their last update timestamp.
        # Clear DB for this specific part of the test to ensure predictable results
        if os.path.exists(main.DB_PATH):
            os.remove(main.DB_PATH)
        main.init_db()

        thread1 = "t1"
        thread2 = "t2"
        summary_t1_initial = "s1_t1"
        summary_t2_initial = "s1_t2"
        summary_t1_updated = "s2_t1" # This will be the latest for t1

        with patch('time.time', side_effect=[10.0, 20.0, 30.0]):
            main.add_memory(thread1, summary_t1_initial) # t1 @ ts=10
            main.add_memory(thread2, summary_t2_initial) # t2 @ ts=20
            main.add_memory(thread1, summary_t1_updated) # t1 @ ts=30 (t1 is now newest overall)
        
        # get_recent_memories fetches based on last update time (timestamp DESC)
        # and then reverses the list for the prompt.
        # So, newest (t1 updated) comes last in the list from get_recent_memories.
        # Oldest of the limited set comes first.
        
        # limit=3 (all unique threads)
        # Order of operations:
        # 1. DB: (t1, 30, s2_t1), (t2, 20, s1_t2)
        # 2. get_recent_memories SQL: Fetches in DESC order of timestamp: (t1, 30, s2_t1), (t2, 20, s1_t2)
        # 3. Python list: [s2_t1, s1_t2]
        # 4. Python list.reverse(): [s1_t2, s2_t1]
        memories_all = main.get_recent_memories(limit=3)
        self.assertEqual(len(memories_all), 2) # Only 2 unique threads
        self.assertEqual(memories_all, [summary_t2_initial, summary_t1_updated])

        # limit=1 (should pick the entry with the latest timestamp, which is t1's updated summary)
        # 1. DB: (t1, 30, s2_t1), (t2, 20, s1_t2)
        # 2. get_recent_memories SQL: Fetches (t1, 30, s2_t1)
        # 3. Python list: [s2_t1]
        # 4. Python list.reverse(): [s2_t1]
        memories_limit_1 = main.get_recent_memories(limit=1)
        self.assertEqual(len(memories_limit_1), 1)
        self.assertEqual(memories_limit_1, [summary_t1_updated])


    @patch('main.get_recent_memories') # Mock this function as it's tested separately
    def test_03_construct_initial_system_prompt(self, mock_get_recent_memories):
        base_prompt = "You are an assistant."
        recipe_base_prompt = "あなたはレシピ提案のエキスパートです。提供された食材の画像に基づいて、ユーザーが作れる料理のレシピ案を3つ考えてください。材料と分量だけを明確に、markdown形式で提示してください。"
        
        # Scenario 1: Memory feature OFF (default from setUp)
        # mock_get_recent_memories should not be called
        prompt_mem_off = main._construct_initial_system_prompt("thread_s1", base_prompt, False)
        self.assertEqual(prompt_mem_off, base_prompt, "Prompt should be base_prompt when memory is OFF.")
        mock_get_recent_memories.assert_not_called()

        # Scenario 2: Memory feature ON, but NO memories returned
        main.MEMORY_FEATURE_ENABLED = True
        mock_get_recent_memories.return_value = [] # No memories
        prompt_mem_on_no_mems = main._construct_initial_system_prompt("thread_s2", base_prompt, False)
        self.assertEqual(prompt_mem_on_no_mems, base_prompt, "Prompt should be base_prompt when memory is ON but no memories exist.")
        mock_get_recent_memories.assert_called_once_with() # Called with no args (or default limit)
        mock_get_recent_memories.reset_mock() # Reset for subsequent scenarios

        # Scenario 3: Memory feature ON, WITH memories
        main.MEMORY_FEATURE_ENABLED = True
        mem_list = ["Past summary 1", "Past summary 2"]
        mock_get_recent_memories.return_value = mem_list
        
        expected_memory_str = "\n\n## Reference from Past Conversations (Summaries) - Use these lightly for context if relevant:\n- Past summary 1\n- Past summary 2" # Updated header
        expected_prompt_with_mems = base_prompt + expected_memory_str
        
        prompt_with_mems = main._construct_initial_system_prompt("thread_s3", base_prompt, False)
        self.assertEqual(prompt_with_mems, expected_prompt_with_mems, "Prompt should include memories when memory is ON and memories exist.")
        mock_get_recent_memories.assert_called_once_with() # Called with no args (or default limit)
        mock_get_recent_memories.reset_mock()

        # Scenario 4: Recipe request, Memory feature ON, WITH memories
        main.MEMORY_FEATURE_ENABLED = True
        recipe_mem_list = ["Recipe context 1", "Recipe context 2"]
        mock_get_recent_memories.return_value = recipe_mem_list

        expected_recipe_memory_str = "\n\n## Reference from Past Conversations (Summaries) - Use these lightly for context if relevant:\n- Recipe context 1\n- Recipe context 2" # Updated header
        expected_recipe_prompt_with_mems = recipe_base_prompt + expected_recipe_memory_str

        # Note: base_prompt is passed but _construct_initial_system_prompt should ignore it if is_recipe is True
        prompt_recipe_with_mems = main._construct_initial_system_prompt("thread_s4", base_prompt, True) 
        self.assertEqual(prompt_recipe_with_mems, expected_recipe_prompt_with_mems, "Recipe prompt should include memories when memory is ON and memories exist.")
        mock_get_recent_memories.assert_called_once_with() # Called with no args (or default limit)
        mock_get_recent_memories.reset_mock()

        # Scenario 5: Recipe request, Memory feature OFF
        main.MEMORY_FEATURE_ENABLED = False # Explicitly turn off for this sub-test
        # mock_get_recent_memories should not be called
        prompt_recipe_mem_off = main._construct_initial_system_prompt("thread_s5", base_prompt, True)
        self.assertEqual(prompt_recipe_mem_off, recipe_base_prompt, "Recipe prompt should be recipe_base_prompt when memory is OFF.")
        mock_get_recent_memories.assert_not_called()
        
        # Restore MEMORY_FEATURE_ENABLED to what it was at the start of this test method if needed,
        # though setUp/tearDown should handle overall test isolation.
        # Here, we've been toggling it, so tearDown will restore the original value.

if __name__ == '__main__':
    # This allows running the tests directly from this file: python test_main.py
    # The sys.path modification at the top helps ensure 'main' module is found.
    unittest.main()
