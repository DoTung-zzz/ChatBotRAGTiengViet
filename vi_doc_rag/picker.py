"""Hộp thoại chọn file / thư mục trên máy (tkinter, có sẵn trong Python).

Nếu máy không có tkinter (vd. Linux chưa cài python3-tk) hoặc không có giao
diện đồ hoạ thì tự chuyển sang nhập đường dẫn bằng tay trong terminal.
"""
from __future__ import annotations

from typing import Optional

_FILETYPES = [
    ("Tài liệu được hỗ trợ", "*.pdf *.docx *.txt *.md"),
    ("PDF", "*.pdf"), ("Word", "*.docx"), ("Văn bản", "*.txt *.md"), ("Tất cả", "*.*"),
]


def _console_fallback() -> Optional[str]:
    print("Không mở được hộp thoại chọn file (thiếu tkinter hoặc không có giao diện đồ hoạ).")
    path = input("Nhập đường dẫn file hoặc thư mục (để trống để thoát): ").strip().strip('"')
    return path or None


def pick_path() -> Optional[str]:
    """Hiện cửa sổ nhỏ có 2 nút 'Chọn file' / 'Chọn thư mục'. Trả về đường dẫn hoặc None."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
    except Exception:  # noqa: BLE001  (ImportError, TclError khi không có display...)
        return _console_fallback()

    result = {"path": None}
    root.title("Chọn tài liệu để thử")
    root.geometry("360x130")
    root.attributes("-topmost", True)

    def choose_file():
        p = filedialog.askopenfilename(parent=root, title="Chọn 1 tài liệu", filetypes=_FILETYPES)
        if p:
            result["path"] = p
            root.destroy()

    def choose_dir():
        p = filedialog.askdirectory(parent=root, title="Chọn thư mục chứa tài liệu")
        if p:
            result["path"] = p
            root.destroy()

    tk.Label(root, text="Bạn muốn xử lý gì?", font=("Segoe UI", 11)).pack(pady=12)
    frame = tk.Frame(root)
    frame.pack()
    tk.Button(frame, text="Chọn 1 file", width=14, command=choose_file).pack(side="left", padx=8)
    tk.Button(frame, text="Chọn cả thư mục", width=14, command=choose_dir).pack(side="left", padx=8)
    root.mainloop()
    return result["path"]
