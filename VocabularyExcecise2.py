import os
import tkinter as tk
from tkinter import filedialog, font, messagebox, simpledialog

from vocabulary_pool import (
    DEFAULT_LIBRARY_NAME,
    LIBRARY_TABLES,
    clear_up_db,
    ensure_all_libraries,
    export_vocabulary_db,
    get_library_word_count,
    get_recent_first_test_records,
    get_statistics,
    get_words_for_test,
    get_wrong_words,
    import_new_words,
    record_practice_result,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMPORT_FILE = os.path.join(BASE_DIR, "learning.csv")
BUILTIN_LIBRARY_FILES = {
    "高中词库": os.path.join(BASE_DIR, "learning.csv"),
    "大学四级词库": os.path.join(BASE_DIR, "cet4.csv"),
    "大学六级词库": os.path.join(BASE_DIR, "cet6.csv"),
}

unknown_words = []
learned_words = []
current_test_words = []
current_test_index = 0
statistics_window = None
statistics_labels = {}
statistics_records_text = None


def get_selected_table_name():
    return LIBRARY_TABLES[current_library_name.get()]


def reset_session_state():
    global current_test_words, current_test_index

    unknown_words.clear()
    learned_words.clear()
    current_test_words = []
    current_test_index = 0
    show_word_label.config(text="")
    progress_label.config(text="准备开始新一轮测试")


def refresh_library_summary(*_args):
    stats = get_statistics(get_selected_table_name())
    library_summary_label.config(
        text=(
            f"当前词库：{stats['library_name']} | 总词数：{stats['total_words']} | "
            f"待复习：{stats['due_words']} | 错题本：{stats['wrong_notebook_count']}"
        )
    )

    refresh_statistics_window()


def choose_csv_file():
    initial_dir = BASE_DIR
    initial_file = os.path.basename(DEFAULT_IMPORT_FILE) if os.path.exists(DEFAULT_IMPORT_FILE) else ""

    return filedialog.askopenfilename(
        title="选择词库 CSV 文件",
        initialdir=initial_dir,
        initialfile=initial_file,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )


def import_words_for_current_library():
    file_path = choose_csv_file()
    if not file_path:
        return

    try:
        imported_count = import_new_words(file_path, get_selected_table_name())
        refresh_library_summary()
        messagebox.showinfo("导入完成", f"已向{current_library_name.get()}导入 {imported_count} 个单词。")
    except Exception as exc:
        messagebox.showerror("导入失败", f"导入词库时发生错误：{exc}")


def import_builtin_library():
    file_path = BUILTIN_LIBRARY_FILES.get(current_library_name.get())

    if not file_path or not os.path.exists(file_path):
        messagebox.showerror("导入失败", "当前词库没有对应的内置 CSV 文件。")
        return

    try:
        imported_count = import_new_words(file_path, get_selected_table_name())
        refresh_library_summary()
        messagebox.showinfo("导入完成", f"已从内置词库导入 {imported_count} 个单词到{current_library_name.get()}。")
    except Exception as exc:
        messagebox.showerror("导入失败", f"导入内置词库时发生错误：{exc}")


def export_current_library():
    file_path = filedialog.asksaveasfilename(
        title="导出当前词库",
        defaultextension=".csv",
        initialfile=f"{current_library_name.get()}.csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    if not file_path:
        return

    try:
        exported_count = export_vocabulary_db(get_selected_table_name(), file_path)
        messagebox.showinfo("导出完成", f"已导出 {exported_count} 条记录。")
    except Exception as exc:
        messagebox.showerror("导出失败", f"导出词库时发生错误：{exc}")


def clear_current_library():
    should_clear = messagebox.askyesno(
        "确认清空",
        f"确定清空 {current_library_name.get()} 的全部词汇和对应错题记录吗？",
    )
    if not should_clear:
        return

    clear_up_db(get_selected_table_name())
    reset_session_state()
    refresh_library_summary()
    messagebox.showinfo("清空完成", f"{current_library_name.get()} 已清空。")


def ask_test_count():
    global current_test_words, current_test_index

    table_name = get_selected_table_name()
    vocabulary_count = get_library_word_count(table_name)

    if vocabulary_count == 0:
        messagebox.showwarning("词库为空", "当前词库没有单词，请先导入 CSV。")
        return

    reset_session_state()

    test_quantity = simpledialog.askinteger(
        "单词测试",
        "请选择您想要测试的单词数量：",
        minvalue=1,
        maxvalue=vocabulary_count,
    )

    if test_quantity is None:
        progress_label.config(text="已取消本次测试")
        return

    current_test_words = get_words_for_test(table_name, test_quantity)
    current_test_index = 0

    if not current_test_words:
        messagebox.showinfo("没有可测试的单词", "当前词库没有可用单词。")
        return

    show_next_word()


def show_next_word():
    if current_test_index < len(current_test_words):
        word = current_test_words[current_test_index]
        show_word_label.config(text=word["english"])
        progress_label.config(
            text=(
                f"第 {current_test_index + 1}/{len(current_test_words)} 个 | "
                f"词义：{word['chinese'] or '未填写释义'}"
            )
        )
    else:
        end_test()


def button_response(is_known):
    global current_test_index

    if current_test_index >= len(current_test_words):
        return

    word = current_test_words[current_test_index]
    learned_words.append(word["english"])
    record_practice_result(get_selected_table_name(), word["english"], is_known)

    if not is_known:
        unknown_words.append(f"{word['english']} - {word['chinese'] or '未填写释义'}")

    current_test_index += 1
    refresh_library_summary()
    show_next_word()


def end_test():
    show_word_label.config(text="测试完成")
    progress_label.config(text=f"本轮共完成 {len(learned_words)} 个单词")

    if unknown_words:
        should_save = messagebox.askyesno(
            "测试结束",
            f"本轮有 {len(unknown_words)} 个错题，是否导出错题清单？",
        )
        if should_save:
            save_unknown_words_to_file()

        messagebox.showinfo("测试结束", "您本轮答错的单词如下：\n" + "\n".join(unknown_words))
    else:
        messagebox.showinfo("测试结束", "本轮测试全部答对，没有新增错题。")


def save_unknown_words_to_file():
    file_path = filedialog.asksaveasfilename(
        title="保存错题清单",
        defaultextension=".txt",
        initialfile="wrong_words.txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as output_file:
            output_file.write("\n".join(unknown_words))
        messagebox.showinfo("保存完成", "错题清单已保存到文件。")
    except Exception as exc:
        messagebox.showerror("保存失败", f"保存文件时发生错误：{exc}")


def show_wrong_notebook():
    wrong_words = get_wrong_words(get_selected_table_name())
    if not wrong_words:
        messagebox.showinfo("错题本", "当前词库还没有错题记录。")
        return

    lines = []
    for index, word in enumerate(wrong_words, start=1):
        lines.append(
            f"{index}. {word['english']} - {word['chinese'] or '未填写释义'} | "
            f"错误次数：{word['wrong_count']} | 最近错误：{word['last_wrong_date']}"
        )

    messagebox.showinfo("错题本", "\n".join(lines))


def get_statistics_lines():
    stats = get_statistics(get_selected_table_name())
    return [
        ("词库", stats["library_name"]),
        ("总词数", stats["total_words"]),
        ("已测试词数", stats["tested_words"]),
        ("待复习词数", stats["due_words"]),
        ("已掌握", stats["mastered_words"]),
        ("学习中", stats["learning_words"]),
        ("复习中", stats["review_words"]),
        ("累计练习次数", stats["total_practice"]),
        ("累计答错次数", stats["total_wrong"]),
        ("错题本条目", stats["wrong_notebook_count"]),
        ("本轮已练习", len(learned_words)),
        ("本轮错题", len(unknown_words)),
    ]


def refresh_statistics_window():
    if statistics_window is None or not statistics_window.winfo_exists():
        return

    for key, value in get_statistics_lines():
        statistics_labels[key].config(text=str(value))

    if statistics_records_text is not None and statistics_records_text.winfo_exists():
        statistics_records_text.config(state=tk.NORMAL)
        statistics_records_text.delete("1.0", tk.END)
        records = get_recent_first_test_records(get_selected_table_name())
        if records:
            for index, record in enumerate(records, start=1):
                statistics_records_text.insert(
                    tk.END,
                    f"{index}. {record['english']} - {record['chinese'] or '未填写释义'} | 首测：{record['first_test_date']}\n",
                )
        else:
            statistics_records_text.insert(tk.END, "当前词库还没有首次测试记录。")
        statistics_records_text.config(state=tk.DISABLED)


def close_statistics_window():
    global statistics_window, statistics_labels, statistics_records_text

    if statistics_window is not None and statistics_window.winfo_exists():
        statistics_window.destroy()

    statistics_window = None
    statistics_labels = {}
    statistics_records_text = None


def show_statistics_panel():
    global statistics_window, statistics_labels, statistics_records_text

    if statistics_window is not None and statistics_window.winfo_exists():
        statistics_window.lift()
        refresh_statistics_window()
        return

    statistics_window = tk.Toplevel(root)
    statistics_window.title("统计面板")
    statistics_window.geometry("560x520")
    statistics_window.resizable(False, False)
    statistics_window.protocol("WM_DELETE_WINDOW", close_statistics_window)

    container = tk.Frame(statistics_window, padx=18, pady=18)
    container.pack(fill="both", expand=True)

    tk.Label(container, text="学习统计", font=("Arial", 18, "bold")).pack(anchor="w", pady=(0, 16))

    statistics_labels = {}
    for key, value in get_statistics_lines():
        row = tk.Frame(container)
        row.pack(fill="x", pady=4)

        tk.Label(row, text=f"{key}：", font=label_font, width=12, anchor="w").pack(side=tk.LEFT)
        value_label = tk.Label(row, text=str(value), font=label_font, anchor="w")
        value_label.pack(side=tk.LEFT, fill="x", expand=True)
        statistics_labels[key] = value_label

    tk.Label(container, text="最近首次测试记录", font=("Arial", 14, "bold")).pack(anchor="w", pady=(18, 8))

    records_frame = tk.Frame(container, bd=1, relief=tk.SOLID)
    records_frame.pack(fill="both", expand=True)

    statistics_records_text = tk.Text(records_frame, height=10, font=("Consolas", 10), wrap="word")
    statistics_records_text.pack(side=tk.LEFT, fill="both", expand=True)

    records_scrollbar = tk.Scrollbar(records_frame, orient=tk.VERTICAL, command=statistics_records_text.yview)
    records_scrollbar.pack(side=tk.RIGHT, fill="y")
    statistics_records_text.config(yscrollcommand=records_scrollbar.set, state=tk.DISABLED)

    tk.Button(container, text="刷新", command=refresh_statistics_window, width=10, font=label_font).pack(anchor="e", pady=(16, 0))
    refresh_statistics_window()


def show_learned_words():
    if learned_words:
        messagebox.showinfo("本轮记录", "\n".join(learned_words))
    else:
        messagebox.showinfo("本轮记录", "当前还没有开始测试。")


ensure_all_libraries()

root = tk.Tk()
root.title("词汇学习器")
root.geometry("900x520")

button_font = font.Font(family="Arial", size=16, weight="bold")
label_font = font.Font(family="Arial", size=12)

current_library_name = tk.StringVar(value=DEFAULT_LIBRARY_NAME)

vocabulary_management_bar = tk.Menu(root)
root.config(menu=vocabulary_management_bar)

file_menu = tk.Menu(vocabulary_management_bar, tearoff=False)
vocabulary_management_bar.add_cascade(label="词库管理", menu=file_menu)
file_menu.add_command(label="导入当前词库内置 CSV", command=import_builtin_library)
file_menu.add_command(label="导入到当前词库", command=import_words_for_current_library)
file_menu.add_command(label="导出当前词库", command=export_current_library)
file_menu.add_command(label="清空当前词库", command=clear_current_library)

top_frame = tk.Frame(root)
top_frame.pack(fill="x", padx=16, pady=(16, 8))

tk.Label(top_frame, text="选择词库：", font=label_font).pack(side=tk.LEFT)
library_selector = tk.OptionMenu(top_frame, current_library_name, *LIBRARY_TABLES.keys(), command=refresh_library_summary)
library_selector.config(font=label_font)
library_selector.pack(side=tk.LEFT, padx=(8, 16))

library_summary_label = tk.Label(top_frame, text="", font=label_font, anchor="w")
library_summary_label.pack(side=tk.LEFT, fill="x", expand=True)

action_frame = tk.Frame(root)
action_frame.pack(fill="x", padx=16, pady=8)

start_button = tk.Button(action_frame, text="开始测试", command=ask_test_count, width=12, height=2, font=button_font)
start_button.pack(side=tk.LEFT, padx=6)

show_learned_button = tk.Button(action_frame, text="本轮记录", command=show_learned_words, width=12, height=2, font=button_font)
show_learned_button.pack(side=tk.LEFT, padx=6)

wrong_notebook_button = tk.Button(action_frame, text="错题本", command=show_wrong_notebook, width=12, height=2, font=button_font)
wrong_notebook_button.pack(side=tk.LEFT, padx=6)

statistics_button = tk.Button(action_frame, text="统计面板", command=show_statistics_panel, width=12, height=2, font=button_font)
statistics_button.pack(side=tk.LEFT, padx=6)

question_label = tk.Label(root, text="看看这个单词", font=button_font, width=30, height=2)
question_label.pack(pady=(20, 8))

show_word_label = tk.Label(root, text="", font=("Arial", 36, "bold"), bg="#d9d9d9", width=22, height=2)
show_word_label.pack(fill="x", padx=16, pady=8)

progress_label = tk.Label(root, text="准备开始新一轮测试", font=label_font)
progress_label.pack(pady=8)

answer_frame = tk.Frame(root)
answer_frame.pack(fill="x", padx=16, pady=20)

known_button = tk.Button(
    answer_frame,
    text="认识",
    command=lambda: button_response(True),
    width=12,
    height=2,
    activebackground="green",
    font=button_font,
)
known_button.pack(side=tk.LEFT, fill="x", expand=True, padx=6)

unknown_button = tk.Button(
    answer_frame,
    text="不认识",
    command=lambda: button_response(False),
    width=12,
    height=2,
    activebackground="orange",
    font=button_font,
)
unknown_button.pack(side=tk.RIGHT, fill="x", expand=True, padx=6)

refresh_library_summary()
root.mainloop()