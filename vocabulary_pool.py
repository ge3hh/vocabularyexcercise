import csv
import sqlite3
from datetime import datetime
from tkinter import simpledialog, messagebox, filedialog, font

# this "learned_words" is for test only.
#learned_words = ['abandon', 'ability', 'able', 'abnormal']

vocabulary_all = {}

def calculate_vocabulary_all ():
    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM vocabulary_hs")
    vocabulary_count= cursor.fetchone()[0]
    # print(f"the number of records in this table is: {vocabulary_count}")

    """
    # verify vocabulary_all
    print(vocabulary_all)
    print(len(vocabulary_all))
    print('the data is growing up!')
    """

    cursor.close()
    conn.close()


def import_new_words (filename):
    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS vocabulary_hs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        english TEXT NOT NULL UNIQUE,
        chinese TEXT,
        practice_times INTEGER NOT NULL DEFAULT 0,
        last_practice_date TEXT
        )
    ''')

    with open(filename, 'r', newline='') as csvfile:
        csv_reader = csv.DictReader(csvfile)

        to_db = [(row['english'], row['chinese'], row['practice_times'], row['last_practice_date']) for row in csv_reader]

    cursor.executemany("INSERT OR IGNORE INTO vocabulary_hs (english, chinese, practice_times, last_practice_date) VALUES (?, ?, ?, ?);", to_db)

    conn.commit()

    """
    # verify the result of this function
    cursor.execute("SELECT * FROM vocabulary_hs")
    print(cursor.fetchall())
    print('the data is growing up!')
    """

    conn.close()


def update_practice_data (learned_words):
    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for word in learned_words:
        cursor.execute('''
        UPDATE vocabulary_hs
        SET practice_times = practice_times + 1,
            last_practice_date = ?
        WHERE english = ?
        ''', (current_time,word))

    conn.commit()
    print(current_time)

    """
    # verify the result of this function
    cursor.execute("SELECT * FROM vocabulary_hs")
    print(cursor.fetchall())
    print('we updated the data!')
    """

    conn.close()

# clear up the current database in need.
def clear_up_db ():
    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM vocabulary_hs")

    #Reset the AUTOINCREMENT counter - id will restart from 1"
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='vocabulary_hs'")

    conn.commit()

    """
    # verify the result of this function
    cursor.execute("SELECT * FROM vocabulary_hs")
    print(cursor.fetchall())
    print('the database is clean now!')
    """

    cursor.close()
    conn.close()

def export_vocabulary_db ():
    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * from vocabulary_hs")

    vocabulary_list = cursor.fetchall()
    vocabulary = {
        id: {'english': english,'chinese': chinese, 'practice_times': practice_times, 'last_practice_date': last_practice_date} for
        id, english, chinese, practice_times, last_practice_date in vocabulary_list
    }

    print(vocabulary)

    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("csv files", "*.csv"), ("All files", "*.*")]
    )
    if file_path:
        try:
            # 写入不认识的单词到文件
            with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow(['id', 'english', 'chinese', 'practice_times', 'last_practice_date'])

                for id, details in vocabulary.items():
                    csv_writer.writerow([id, details['english'], details['chinese'], details['practice_times'], details['last_practice_date']])

            messagebox.showinfo("完成", "词汇库已保存到文件。")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件时发生错误：{e}")

    cursor.close()
    conn.close()


