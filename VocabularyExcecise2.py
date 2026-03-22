import tkinter as tk
from operator import index
from tkinter import simpledialog, messagebox, filedialog, font
from tkinter.font import Font
import csv
import random
from vocabulary_pool import *

# 初始空的词汇库
vocabulary = {}

# 记录用户选择“不认识”的单词以及学过的单词
unknown_words = []
learned_words = []

# 用户选择的测试数量
test_quantity = 0

filename = 'C:\\learning\\learning.csv'
table_name = 'vocabulary_hs'

vocabulary_all = {}

def load_vocabulary_from_db (table_name, test_quantity):
    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()

    cursor.execute ("SELECT * FROM {} ORDER BY RANDOM() LIMIT ?".format(table_name),(test_quantity,))

    vocabulary = cursor.fetchall()


    # verify the vocabulary{}
    for word in vocabulary:
        print(word)


    cursor.close()
    conn.close()

    return vocabulary

"""
# 函数：从CSV文件加载词汇库
def load_vocabulary_from_csv(file_path):
    try:
        with open(file_path, mode='r', encoding='utf-8', errors='ignore') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                vocabulary[row['english']] = row['chinese']
    except FileNotFoundError:
        messagebox.showerror("错误", "找不到文件，请检查文件路径。")
    except Exception as e:
        messagebox.showerror("错误", f"读取文件时发生错误：{e}")
"""

# 函数：询问用户测试数量并开始测试
def ask_test_count():
    global test_quantity

    conn = sqlite3.connect('vocabulary_hs.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vocabulary_hs")
    vocabulary_count = cursor.fetchone()[0]

    test_quantity_max = vocabulary_count

    test_quantity = simpledialog.askinteger("单词测试", "请选择您想要测试的单词数量:", minvalue=1,
                                            maxvalue=test_quantity_max)
    if test_quantity is None:  # 如果检测到取消操作，直接关闭对话框
        pass
    elif 1 <= test_quantity <= test_quantity_max:

        cursor.execute("SELECT * FROM {} ORDER BY RANDOM() LIMIT ?".format(table_name), (test_quantity,))

        vocabulary_list = cursor.fetchall()
        vocabulary = {
            english: {'chinese': chinese, 'practice_times': practice_times, 'last_practice_date': last_practice_date}
            for id, english, chinese, practice_times, last_practice_date in vocabulary_list}
        try:
            print(test_quantity)
            print(vocabulary_list)
            print(list(vocabulary.keys()))
        except IndexError:
            print("error is here")
        test_words = random.sample(list(vocabulary.keys()), test_quantity)

        test_index = 0

        show_next_word(test_words, test_index)
    else:
        messagebox.showerror("错误", "请输入一个有效的数量（1 到 {} 之间）！".format(test_quantity_max))
        ask_test_count()  # 如果输入无效，重新询问

    cursor.close()
    conn.close()

# 函数：显示下一个单词并询问用户是否认识
def show_next_word(test_words, index):
    if index < test_quantity:
        learned_words.append(test_words[index])  # 添加到学过的单词列表
        show_word_label.config(text=test_words[index])
        known_button.config(command=lambda: button_response(test_words, index,True))
        unknown_button.config(command=lambda: button_response(test_words, index,False))
        update_practice_data(learned_words)
    else:
        end_test()  # 测试结束


def button_response(test_words,index, is_known):
    if is_known:
        # 用户选择“认识”
        show_next_word(test_words, index + 1)
    else:
        # 用户选择“不认识”
        unknown_words.append(test_words[index])
        if index + 1 < test_quantity:
            show_next_word(test_words, index + 1)
        else:
            end_test()

# 等待用户点击按钮
    root.wait_window(root)


# 函数：测试结束后的操作
def end_test():
    messagebox.showinfo("测试结束", f"所有单词测试已完成，保存不认识的单词清单")
    # 显示不认识的单词
    unknown_words_str = '\n'.join(unknown_words) \

    if unknown_words:
        # 保存不认识的单词到文件
        save_unknown_words_to_file()
    else: "没有不认识的单词。"
    messagebox.showinfo("测试结束", f"您不认识的单词有:\n{unknown_words_str}")
#    root.destroy()  # 关闭自定义对话框

# 函数：保存不认识的单词到文件
def save_unknown_words_to_file():
    # 弹出保存文件对话框
    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if file_path:
        try:
            # 写入不认识的单词到文件
            with open(file_path, 'w', encoding='utf-8') as file:
                for word in unknown_words:
                    file.write(word + '\n')
            messagebox.showinfo("完成", "不认识的单词已保存到文件。")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件时发生错误：{e}")


# 函数：显示所有不认识的单词
def show_unknown_words():
    if unknown_words:
        unknown_words_str = '\n'.join(unknown_words)
        messagebox.showinfo("不认识的单词", f"您不认识的单词有:\n{unknown_words_str}")
    else:
        messagebox.showinfo("不认识的单词", "您认识本次测试中的所有单词。")


# 函数：显示所有学过的单词
def show_learned_words():
    if learned_words:
        learned_words_str = '\n'.join(learned_words)
        messagebox.showinfo("学过的单词", f"您学过的单词有:\n{learned_words_str}")
    else:
        messagebox.showinfo("学过的单词", "您还没有学过任何单词。")


# 函数：清空学过的单词列表
def clear_learned_words():
    global learned_words
    learned_words.clear()
    messagebox.showinfo("清空单词", "已清空所有学过的单词。")


# 创建主窗口
root = tk.Tk()
root.title("词汇学习器")


# 设置字体
button_font = font.Font(family="Arial", size=20, weight="bold")

# 创建词汇库管理菜单
vocabulary_management_bar = tk.Menu(root)
root.config(menu=vocabulary_management_bar)

file_menu = tk.Menu(vocabulary_management_bar, tearoff=False)
vocabulary_management_bar.add_cascade(label="词汇库管理", menu=file_menu)

file_menu.add_command(label="增加新词汇", command=lambda: import_new_words (filename) )
file_menu.add_command(label="导出词汇库", command=lambda: export_vocabulary_db () )
file_menu.add_command(label="清除库中所有词汇", command=lambda: clear_up_db () )
file_menu.add_command(label="创建新词汇库", command=lambda: import_new_words (filename) )

"""
# 创建按钮加载词汇库
load_vocabulary_button = tk.Button(root, text="加载词汇库", command=lambda: load_vocabulary_from_csv('C:\\learning\\learning.csv'),
                   width=20,  # 设置按钮宽度为20个字符宽
                   height=2,  # 设置按钮高度为2行高
                   font=button_font)  # 设置按钮上文字的字体
load_vocabulary_button.pack(pady=10)
"""

# 创建按钮询问测试数量
start_button = tk.Button(root, text="开始测试", command=ask_test_count,
                    width=20,  # 设置按钮宽度为20个字符宽
                    height=2,  # 设置按钮高度为2行高
                    font=button_font)  # 设置按钮上文字的字体
start_button.pack(pady=10)

# 创建按钮显示所有学过的单词
show_learned_button = tk.Button(root, text="查看学过的单词", command=show_learned_words,
                    width=20,  # 设置按钮宽度为20个字符宽
                    height=2,  # 设置按钮高度为2行高
                    font=button_font)  # 设置按钮上文字的字体
show_learned_button.pack(pady=10)

# 创建按钮清空所有学过的单词
clear_learned_button = tk.Button(root, text="清空学过的单词", command=clear_learned_words,
                    width=20,  # 设置按钮宽度为20个字符宽
                    height=2,  # 设置按钮高度为2行高
                    font=button_font)  # 设置按钮上文字的字体
clear_learned_button.pack(pady=10)

question_label = tk.Label(root, text="看看这个单词~", font=button_font,
                    width = 40,  # 设置按钮宽度为20个字符宽
                    height = 2)  # 设置按钮高度为2行高
question_label.pack(pady=10)

show_word_label = tk.Label(root, text="", font=("Arial", 40, "bold"), bg="grey",
                    width = 20,  # 设置按钮宽度为20个字符宽
                    height = 2)  # 设置按钮高度为2行高
show_word_label.pack(fill='x', pady=10)

known_button = tk.Button(root, text="认识", command=lambda: button_response(True),
                    width=8,  # 设置按钮宽度为20个字符宽
                    height=2,  # 设置按钮高度为2行高
                    activebackground='green',
                    font=button_font)  # 设置按钮上文字的字体
known_button.pack(side=tk.LEFT,fill='x', expand= True, padx=10, pady=10)

unknown_button = tk.Button(root, text="不认识", command=lambda: button_response(False),
                    width=8,  # 设置按钮宽度为20个字符宽
                    height=2,  # 设置按钮高度为2行高
                    activebackground='orange',
                    font=button_font)  # 设置按钮上文字的字体
unknown_button.pack(side=tk.RIGHT,fill='x', expand= True, padx=10, pady=10)


# 运行应用程序
root.mainloop()