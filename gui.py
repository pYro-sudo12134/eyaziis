import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from database import Database, ConnectionFactory
from text_processor import TextProcessor
from morphology_analyzer import get_morphology_analyzer
from suggestion_manager import get_suggestion_manager

class WidgetFactory:
    @staticmethod
    def create_button(parent, text, command, **kwargs):
        return ttk.Button(parent, text=text, command=command, **kwargs)
    
    @staticmethod
    def create_label(parent, text="", **kwargs):
        return ttk.Label(parent, text=text, **kwargs)
    
    @staticmethod
    def create_entry(parent, textvariable=None, **kwargs):
        return ttk.Entry(parent, textvariable=textvariable, **kwargs)
    
    @staticmethod
    def create_combobox(parent, textvariable, values, **kwargs):
        combo = ttk.Combobox(parent, textvariable=textvariable, **kwargs)
        combo['values'] = values
        return combo
    
    @staticmethod
    def create_frame(parent, **kwargs):
        return ttk.Frame(parent, **kwargs)
    
    @staticmethod
    def create_scrolled_text(parent, **kwargs):
        return scrolledtext.ScrolledText(parent, **kwargs)
    
    @staticmethod
    def create_treeview(parent, columns, **kwargs):
        return ttk.Treeview(parent, columns=columns, **kwargs)
    
    @staticmethod
    def create_scrollbar(parent, orient='vertical', command=None):
        return ttk.Scrollbar(parent, orient=orient, command=command)

class UIFactory:
    @staticmethod
    def create_top_panel(parent, app):
        frame = WidgetFactory.create_frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=10)
        
        buttons = [
            ("Загрузить файл", app.load_file),
            ("Загрузить с авторазбором", app.load_file_with_morphology),
            ("Обновить список", app.load_word_forms),
            ("Показать предложения", app.show_suggestions_dialog),
            ("Экспорт в JSON", app.export_to_json),
            ("Справка", app.show_help)
        ]
        
        for text, command in buttons:
            WidgetFactory.create_button(
                frame, text=text, command=command
            ).pack(side=tk.LEFT, padx=5)
        
        return frame
    
    @staticmethod
    def create_search_panel(parent, app):
        frame = WidgetFactory.create_frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        WidgetFactory.create_label(frame, text="Поиск:").pack(side=tk.LEFT)
        
        app.search_var = tk.StringVar()
        app.search_entry = WidgetFactory.create_entry(
            frame, textvariable=app.search_var, width=30
        )
        app.search_entry.pack(side=tk.LEFT, padx=5)
        app.search_entry.bind('<KeyRelease>', app.on_search)
        
        WidgetFactory.create_button(
            frame, text="Очистить", command=app.clear_search
        ).pack(side=tk.LEFT)
        
        return frame
    
    @staticmethod
    def create_main_container(parent):
        container = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        return container
    
    @staticmethod
    def create_word_list_panel(parent, app):
        frame = WidgetFactory.create_frame(parent)
        
        columns = ('ID', 'Словоформа & лексема', 'Частота', 'Часть речи', 'Род', 'Число', 'Падеж')
        app.tree = WidgetFactory.create_treeview(
            frame, columns=columns, show='headings', height=25
        )
        
        col_widths = [50, 150, 80, 100, 80, 80, 80]
        for col, width in zip(columns, col_widths):
            app.tree.heading(col, text=col)
            app.tree.column(col, width=width, anchor=tk.CENTER)
        
        scrollbar = WidgetFactory.create_scrollbar(
            frame, command=app.tree.yview
        )
        app.tree.configure(yscrollcommand=scrollbar.set)
        
        app.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        app.tree.bind('<<TreeviewSelect>>', app.on_word_select)
        
        app.tree_menu = tk.Menu(app.root, tearoff=0)
        app.tree_menu.add_command(label="Автоматический разбор", 
                                 command=app.auto_analyze_selected)
        app.tree_menu.add_separator()
        app.tree_menu.add_command(label="Копировать слово", 
                                 command=app.copy_selected_word)
        
        app.tree.bind("<Button-3>", app.show_tree_context_menu)
        
        return frame
    
    @staticmethod
    def create_morphology_panel(parent, app):
        frame = WidgetFactory.create_frame(parent)
        
        WidgetFactory.create_label(
            frame, text="Морфологическая информация", 
            font=('Arial', 12, 'bold')
        ).pack(pady=10)
        
        input_frame = WidgetFactory.create_frame(frame)
        input_frame.pack(fill=tk.X, padx=20, pady=10)
        
        morphology_fields = [
            ("Часть речи:", "pos_var", 
             ['', 'существительное', 'прилагательное', 'глагол', 
              'наречие', 'местоимение', 'предлог', 'союз']),
            ("Род:", "gender_var", ['', 'мужской', 'женский', 'средний']),
            ("Число:", "number_var", ['', 'единственное', 'множественное']),
            ("Падеж:", "case_var", 
             ['', 'именительный', 'родительный', 'дательный', 
              'винительный', 'творительный', 'предложный'])
        ]
        
        for i, (label_text, var_name, values) in enumerate(morphology_fields):
            WidgetFactory.create_label(
                input_frame, text=label_text
            ).grid(row=i, column=0, sticky=tk.W, pady=5)
            
            var = tk.StringVar()
            setattr(app, var_name, var)
            
            WidgetFactory.create_combobox(
                input_frame, textvariable=var, values=values, width=20
            ).grid(row=i, column=1, pady=5, padx=(10, 0))
        
        auto_frame = WidgetFactory.create_frame(input_frame)
        auto_frame.grid(row=len(morphology_fields), column=0, columnspan=2, pady=10)
        
        WidgetFactory.create_button(
            auto_frame, text="Авторазбор", command=app.auto_analyze
        ).pack(side=tk.LEFT, padx=5)
        
        app.auto_status_var = tk.StringVar()
        WidgetFactory.create_label(
            auto_frame, textvariable=app.auto_status_var, 
            foreground="green", font=('Arial', 9)
        ).pack(side=tk.LEFT, padx=10)
        
        WidgetFactory.create_label(
            frame, text="Произвольная заметка:"
        ).pack(anchor=tk.W, padx=20, pady=(20, 5))
        
        app.note_text = WidgetFactory.create_scrolled_text(
            frame, height=10, width=40
        )
        app.note_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        
        button_frame = WidgetFactory.create_frame(frame)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        
        WidgetFactory.create_button(
            button_frame, text="Сохранить", command=app.save_morphology
        ).pack(side=tk.LEFT, padx=5)
        
        WidgetFactory.create_button(
            button_frame, text="Очистить", command=app.clear_form
        ).pack(side=tk.LEFT, padx=5)
        
        return frame
    
    @staticmethod
    def create_status_bar(parent, app):
        app.status_var = tk.StringVar()
        app.status_var.set("Готов к работе")
        status_label = WidgetFactory.create_label(
            parent, textvariable=app.status_var
        )
        status_label.configure(relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(side=tk.BOTTOM, fill=tk.X)
        return status_label

class DictionaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Автоматизированная система формирования словаря")
        self.root.geometry("1200x700")
        
        self.db = Database()
        self.text_processor = TextProcessor(auto_analyze=True, confidence_threshold=0.3)
        self.suggestion_manager = get_suggestion_manager()
        
        self.create_widgets()
        self.load_word_forms()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        UIFactory.create_top_panel(self.root, self)
        UIFactory.create_search_panel(self.root, self)
        
        main_container = UIFactory.create_main_container(self.root)
        
        left_panel = UIFactory.create_word_list_panel(main_container, self)
        main_container.add(left_panel, weight=1)
        
        right_panel = UIFactory.create_morphology_panel(main_container, self)
        main_container.add(right_panel, weight=1)
        
        UIFactory.create_status_bar(self.root, self)
        
        self.current_word_id = None
    
    def load_file(self):
        self._load_file_internal(use_morphology=False)
    
    def load_file_with_morphology(self):
        self._load_file_internal(use_morphology=True)
    
    def _load_file_internal(self, use_morphology: bool = False):
        file_path = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=[("Текстовые файлы", "*.txt *.rtf"), 
                      ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        self.status_var.set(f"Обработка файла: {file_path}")
        self.root.update_idletasks()
        
        try:
            if use_morphology:
                word_counter, morphology_results = self.text_processor.process_file(
                    file_path, return_morphology=True
                )
                
                self.db.insert_or_update_word_forms(word_counter)
                
                suggestions_added = 0
                for word, morph_data in morphology_results.items():
                    suggestion = self.text_processor.get_suggested_morphology(word)
                    if suggestion:
                        if self.suggestion_manager.add_suggestion(word, suggestion):
                            suggestions_added += 1
                
                self.status_var.set(
                    f"Файл обработан. Добавлено {len(word_counter)} словоформ, "
                    f"{suggestions_added} предложений по морфологии"
                )
                
                if suggestions_added > 0:
                    messagebox.showinfo(
                        "Предложения по морфологии",
                        f"Создано {suggestions_added} предложений по морфологии.\n"
                        f"Нажмите 'Показать предложения' для просмотра."
                    )
                
            else:
                word_counter = self.text_processor.process_file(file_path)
                self.db.insert_or_update_word_forms(word_counter)
                self.status_var.set(f"Файл обработан. Добавлено {len(word_counter)} словоформ")
            
            self.load_word_forms()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать файл:\n{str(e)}")
            self.status_var.set("Ошибка обработки файла")
    
    def load_word_forms(self, search_term=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        if search_term:
            data = self.db.search_word_forms(search_term)
        else:
            data = self.db.get_all_word_forms()
        
        for row in data:
            self.tree.insert('', tk.END, values=row)
        
        self.status_var.set(f"Загружено {len(data)} записей")
    
    def on_search(self, event=None):
        search_term = self.search_var.get().strip()
        if search_term:
            self.load_word_forms(search_term)
        else:
            self.load_word_forms()
    
    def clear_search(self):
        self.search_var.set("")
        self.load_word_forms()
    
    def show_tree_context_menu(self, event):
        try:
            item = self.tree.identify_row(event.y)
            if item:
                self.tree.selection_set(item)
                self.tree_menu.post(event.x_root, event.y_root)
        except:
            pass
    
    def auto_analyze_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите слово из списка")
            return
        
        item = self.tree.item(selection[0])
        values = item['values']
        
        if values:
            self.current_word_id = values[0]
            self.on_word_select(None)
            self.auto_analyze()
    
    def copy_selected_word(self):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            if item['values'] and len(item['values']) > 1:
                word = item['values'][1]
                self.root.clipboard_clear()
                self.root.clipboard_append(word)
                self.status_var.set(f"Слово '{word}' скопировано")
    
    def on_word_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        
        item = self.tree.item(selection[0])
        values = item['values']
        
        if values:
            self.current_word_id = values[0]
            
            self.pos_var.set(values[3] if values[3] else '')
            self.gender_var.set(values[4] if values[4] else '')
            self.number_var.set(values[5] if values[5] else '')
            self.case_var.set(values[6] if values[6] else '')
            
            self.note_text.delete(1.0, tk.END)
            if values[7]:
                self.note_text.insert(1.0, values[7])
    
    def auto_analyze(self):
        if not self.current_word_id:
            messagebox.showwarning("Предупреждение", 
                                 "Сначала выберите слово из списка")
            return
        
        selection = self.tree.selection()
        if not selection:
            return
        
        item = self.tree.item(selection[0])
        values = item['values']
        
        if not values or len(values) < 2:
            return
        
        word = values[1]
        
        try:
            analyzer = get_morphology_analyzer()
            result = analyzer.analyze_word(word)
            
            if result['confidence'] < 0.1:
                self.auto_status_var.set("Низкая достоверность разбора")
                if not messagebox.askyesno("Подтверждение", 
                                          "Достоверность разбора низкая. Всё равно применить?"):
                    return
            
            if result['part_of_speech']:
                self.pos_var.set(result['part_of_speech'])
            if result['gender']:
                self.gender_var.set(result['gender'])
            if result['number']:
                self.number_var.set(result['number'])
            if result['case_form']:
                self.case_var.set(result['case_form'])
            
            current_note = self.note_text.get(1.0, tk.END).strip()
            note_lines = []
            
            if current_note:
                note_lines.append(current_note)
            
            note_lines.append(f"--- Авторазбор: {word} ---")
            note_lines.append(f"Нормальная форма: {result['normal_form']}")
            note_lines.append(f"Достоверность: {result['confidence']:.2f}")
            note_lines.append(f"Теги: {result['tag']}")
            
            self.note_text.delete(1.0, tk.END)
            self.note_text.insert(1.0, "\n".join(note_lines))
            
            self.auto_status_var.set(f"✓ Авторазбор: {result['normal_form']}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось выполнить авторазбор:\n{str(e)}")
            self.auto_status_var.set("Ошибка авторазбора")
    
    def save_morphology(self):
        if not self.current_word_id:
            messagebox.showwarning("Предупреждение", "Сначала выберите слово из списка")
            return
        
        part_of_speech = self.pos_var.get().strip()
        gender = self.gender_var.get().strip()
        number = self.number_var.get().strip()
        case_form = self.case_var.get().strip()
        custom_note = self.note_text.get(1.0, tk.END).strip()
        
        success = self.db.update_morphology(
            self.current_word_id,
            part_of_speech if part_of_speech else None,
            gender if gender else None,
            number if number else None,
            case_form if case_form else None,
            custom_note if custom_note else None
        )
        
        if success:
            messagebox.showinfo("Успех", "Морфологическая информация сохранена")
            self.load_word_forms()
            self.auto_status_var.set("")
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить информацию")
    
    def clear_form(self):
        self.pos_var.set('')
        self.gender_var.set('')
        self.number_var.set('')
        self.case_var.set('')
        self.note_text.delete(1.0, tk.END)
        self.current_word_id = None
        self.auto_status_var.set("")
    
    def show_suggestions_dialog(self):
        if not hasattr(self, '_suggestions_window') or not self._suggestions_window.winfo_exists():
            self._create_suggestions_dialog()
        else:
            self._suggestions_window.lift()
    
    def _create_suggestions_dialog(self):
        self._suggestions_window = tk.Toplevel(self.root)
        self._suggestions_window.title("Предложения по морфологии")
        self._suggestions_window.geometry("800x600")
        
        list_frame = ttk.Frame(self._suggestions_window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ('Слово', 'Часть речи', 'Род', 'Число', 'Падеж', 'Достоверность', 'Действия')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=20)
        
        col_widths = [120, 120, 80, 80, 80, 100, 100]
        for col, width in zip(columns, col_widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._load_suggestions_to_tree(tree)
        
        button_frame = ttk.Frame(self._suggestions_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(
            button_frame, text="Применить выбранное",
            command=lambda: self._apply_selected_suggestion(tree)
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Отклонить выбранное",
            command=lambda: self._reject_selected_suggestion(tree)
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Обновить",
            command=lambda: self._load_suggestions_to_tree(tree)
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Очистить все",
            command=self._clear_all_suggestions
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Закрыть",
            command=self._suggestions_window.destroy
        ).pack(side=tk.RIGHT, padx=5)
    
    def _load_suggestions_to_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)
        
        all_suggestions = {}
        for word in self.suggestion_manager.suggestions:
            for suggestion_data in self.suggestion_manager.suggestions[word]:
                if word not in all_suggestions:
                    all_suggestions[word] = []
                all_suggestions[word].append(suggestion_data)
        
        for word, suggestions_list in all_suggestions.items():
            for suggestion_data in suggestions_list:
                suggestion = suggestion_data['suggestion']
                tree.insert('', tk.END, values=(
                    word,
                    suggestion.get('part_of_speech', ''),
                    suggestion.get('gender', ''),
                    suggestion.get('number', ''),
                    suggestion.get('case_form', ''),
                    f"{suggestion.get('confidence', 0):.2f}",
                    suggestion_data['hash']
                ))
    
    def _apply_selected_suggestion(self, tree):
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите предложение")
            return
        
        item = tree.item(selection[0])
        values = item['values']
        
        word = values[0]
        suggestion_hash = values[6]
        
        if self.suggestion_manager.accept_suggestion(word, suggestion_hash):
            results = self.db.search_word_forms(word)
            if results:
                word_id = results[0][0]
                
                suggestion = self.suggestion_manager.get_accepted(word)
                if suggestion:
                    success = self.db.update_morphology(
                        word_id,
                        suggestion.get('part_of_speech'),
                        suggestion.get('gender'),
                        suggestion.get('number'),
                        suggestion.get('case_form'),
                        f"Авторазбор: {suggestion.get('tag', '')}"
                    )
                    
                    if success:
                        messagebox.showinfo("Успех", 
                                          f"Морфология для слова '{word}' применена")
                        self.load_word_forms()
                        self._load_suggestions_to_tree(tree)
                    else:
                        messagebox.showerror("Ошибка", 
                                           "Не удалось применить морфологию")
            else:
                messagebox.showwarning("Предупреждение", 
                                     f"Слово '{word}' не найдено в базе данных")
    
    def _reject_selected_suggestion(self, tree):
        selection = tree.selection()
        if not selection:
            return
        
        item = tree.item(selection[0])
        values = item['values']
        
        word = values[0]
        suggestion_hash = values[6]
        
        if self.suggestion_manager.reject_suggestion(word, suggestion_hash):
            self._load_suggestions_to_tree(tree)
    
    def _clear_all_suggestions(self):
        if messagebox.askyesno("Подтверждение", 
                              "Очистить все предложения по морфологии?"):
            self.suggestion_manager.clear_all()
            if hasattr(self, '_suggestions_window'):
                for widget in self._suggestions_window.winfo_children():
                    if isinstance(widget, ttk.Treeview):
                        for item in widget.get_children():
                            widget.delete(item)
    
    def export_to_json(self):
        json_data = self.db.export_to_json()
        
        file_path = filedialog.asksaveasfilename(
            title="Сохранить как JSON",
            defaultextension=".json",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_data)
                messagebox.showinfo("Успех", f"Словарь экспортирован в:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{str(e)}")
    
    def show_help(self):
        help_text = """
        АВТОМАТИЗИРОВАННАЯ СИСТЕМА ФОРМИРОВАНИЯ СЛОВАРЯ
        
        ИНСТРУКЦИЯ:
        
        1. Загрузка файла:
           - "Загрузить файл" - обычная загрузка текст
           - "Загрузить с авторазбором" - с автоматическим морфологическим анализом
        
        2. Просмотр словаря:
           - Все словоформы отображаются в таблице слева
           - Сортировка по алфавиту
           - Показана частота встречаемости
        
        3. Автоматический морфологический разбор:
           - Выберите слово из таблицы
           - Нажмите кнопку "Авторазбор" справа
           - Или используйте правую кнопку мыши в таблице
        
        4. Просмотр предложений:
           - Нажмите "Показать предложения"
           - Просмотрите все автоматические разборы
           - Примите или отклоните предложения
        
        5. Ручное редактирование:
           - Заполните форму справа (часть речи, род и т.д.)
           - Нажмите "Сохранить"
        
        6. Поиск:
           - Введите слово в поле поиска
           - Результаты обновятся автоматически
        
        7. Экспорт:
           - Нажмите "Экспорт в JSON"
           - Сохраните полный словарь в JSON формате
        
        Словоформа — это конкретная грамматическая форма слова.
        Лексема — это основная единица языка, представляющая собой слово в совокупности всех его форм (словоформ) и лексических значений.
           
        ВАЖНО: Система работает с русским языком.
               Для работы требуется подключение к PostgreSQL.
        """
        
        messagebox.showinfo("Справка", help_text)
    
    def on_closing(self):
        if messagebox.askokcancel("Выход", "Вы уверены, что хотите выйти?"):
            self.db.close()
            self.root.destroy()

def main():
    root = tk.Tk()
    app = DictionaryApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()