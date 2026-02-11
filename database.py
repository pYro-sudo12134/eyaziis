import psycopg2
from abc import ABC, abstractmethod

class DatabaseConnection(ABC):
    @abstractmethod
    def get_connection(self):
        pass
    
    @abstractmethod
    def close(self):
        pass

class PostgreSQLConnection(DatabaseConnection):
    def __init__(self, host='localhost', dbname='postgres', 
                 user='postgres', password='postgres', port=5432):
        self.host = host
        self.dbname = dbname
        self.user = user
        self.password = password
        self.port = port
        self.connection = None
        self.connected = False
    
    def get_connection(self):
        if not self.connected:
            self.connect()
        return self.connection
    
    def connect(self):
        try:
            print("Подключение к PostgreSQL")
            
            self.connection = psycopg2.connect(
                host=self.host,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                port=self.port
            )
            
            self.connected = True
            print("Подключение установлено!")
            
            cursor = self.connection.cursor()
            cursor.execute("SET search_path TO public;")
            self.connection.commit()
            cursor.close()
            print("Схема установлена: public")
            
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            self.connected = False
            raise
    
    def close(self):
        if self.connection:
            self.connection.close()
            print("Соединение закрыто")
            self.connected = False

class ConnectionFactory:
    @staticmethod
    def create_postgresql_connection(**kwargs):
        return PostgreSQLConnection(**kwargs)
    
    @staticmethod
    def create_connection(db_type='postgresql', **kwargs):
        if db_type.lower() == 'postgresql':
            return PostgreSQLConnection(**kwargs)
        else:
            raise ValueError(f"Неподдерживаемый тип БД: {db_type}")

class Database:
    def __init__(self, connection: DatabaseConnection = None):
        if connection is None:
            connection = ConnectionFactory.create_postgresql_connection()
        
        self.db_connection = connection
        self.connection = self.db_connection.get_connection()
        self.connected = self.db_connection.connected
        
        if self.connected:
            self.create_tables()
    
    def create_tables(self):
        if not self.connected:
            print("Нет подключения к БД")
            return
            
        queries = [
            """
            CREATE TABLE IF NOT EXISTS public.word_forms (
                id SERIAL PRIMARY KEY,
                word_form VARCHAR(255) NOT NULL UNIQUE,
                frequency INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public.morphology (
                id SERIAL PRIMARY KEY,
                word_form_id INTEGER NOT NULL,
                part_of_speech VARCHAR(50),
                gender VARCHAR(20),
                number VARCHAR(20),
                case_form VARCHAR(20),
                custom_note TEXT,
                FOREIGN KEY (word_form_id) 
                REFERENCES public.word_forms(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_word_form ON public.word_forms(word_form)",
            "CREATE INDEX IF NOT EXISTS idx_word_form_id ON public.morphology(word_form_id)"
        ]
        
        try:
            cursor = self.connection.cursor()
            for query in queries:
                cursor.execute(query)
            self.connection.commit()
            cursor.close()
            print("Таблицы созданы в схеме public")
        except Exception as e:
            print(f"Ошибка создания таблиц: {e}")
    
    def insert_or_update_word_forms(self, word_counter):
        if not self.connected:
            print("Нет подключения к БД")
            return False
            
        query = """
            INSERT INTO public.word_forms (word_form, frequency)
            VALUES (%s, %s)
            ON CONFLICT (word_form) 
            DO UPDATE SET frequency = public.word_forms.frequency + EXCLUDED.frequency
        """
        
        try:
            cursor = self.connection.cursor()
            for word, freq in word_counter.items():
                cursor.execute(query, (word, freq))
            self.connection.commit()
            cursor.close()
            print(f"Добавлено {len(word_counter)} словоформ")
            return True
        except Exception as e:
            print(f"Ошибка: {e}")
            return False
    
    def get_all_word_forms(self, limit=1000):
        if not self.connected:
            return []
            
        query = """
            SELECT wf.id, wf.word_form, wf.frequency, 
                   m.part_of_speech, m.gender, m.number, m.case_form, m.custom_note
            FROM public.word_forms wf
            LEFT JOIN public.morphology m ON wf.id = m.word_form_id
            ORDER BY wf.word_form
            LIMIT %s
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (limit,))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка: {e}")
            return []
    
    def search_word_forms(self, search_term):
        if not self.connected:
            return []
            
        query = """
            SELECT wf.id, wf.word_form, wf.frequency, 
                   m.part_of_speech, m.gender, m.number, m.case_form, m.custom_note
            FROM public.word_forms wf
            LEFT JOIN public.morphology m ON wf.id = m.word_form_id
            WHERE wf.word_form ILIKE %s
            ORDER BY wf.word_form
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (f'%{search_term}%',))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            print(f"Ошибка: {e}")
            return []
    
    def update_morphology(self, word_form_id, part_of_speech, gender, number, case_form, custom_note):
        if not self.connected:
            return False
            
        delete_query = "DELETE FROM public.morphology WHERE word_form_id = %s"
        insert_query = """
            INSERT INTO public.morphology 
            (word_form_id, part_of_speech, gender, number, case_form, custom_note)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(delete_query, (word_form_id,))
            cursor.execute(insert_query, 
                          (word_form_id, part_of_speech, gender, number, case_form, custom_note))
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Ошибка: {e}")
            return False
    
    def export_to_json(self):
        import json
        data = self.get_all_word_forms(limit=10000)
        result = []
        
        for row in data:
            result.append({
                'id': row[0],
                'word_form': row[1],
                'frequency': row[2],
                'morphology': {
                    'part_of_speech': row[3],
                    'gender': row[4],
                    'number': row[5],
                    'case': row[6],
                    'custom_note': row[7]
                }
            })
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    def close(self):
        if self.db_connection:
            self.db_connection.close()
            self.connected = False