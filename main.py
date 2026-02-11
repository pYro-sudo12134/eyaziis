"""
Лабораторная работа 1. Разработка автоматизированной системы формирования словаря
Вариант 1: Русский язык, форматы TXT/RTF, Задание 1
"""

import sys
import tkinter as tk
from gui import DictionaryApp

def main():
    try:
        root = tk.Tk()
        app = DictionaryApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)

if __name__ == "__main__":
    main()